import pytest
import uuid
import pickle
from unittest.mock import patch, MagicMock, call
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from app.main import app
from app.db.models import Subscription
from app.core.cache import (
    set_cache, get_cache, delete_cache, 
    cache_subscription, get_cached_subscription, invalidate_subscription_cache,
    get_subscription_field, cache_all_subscriptions
)

client = TestClient(app)

# Mock subscription data
mock_subscription_id = str(uuid.uuid4())
mock_subscription_data = {
    "id": mock_subscription_id,
    "name": "Test Subscription",
    "target_url": "https://example.com/webhook",
    "secret_key": "test-secret-key",
    "active": True,
}

# Create a Subscription object for testing
mock_subscription = Subscription(
    id=uuid.UUID(mock_subscription_id),
    name="Test Subscription",
    target_url="https://example.com/webhook",
    secret_key="test-secret-key",
    active=True
)

@pytest.fixture
def mock_redis():
    """Mock Redis client for testing"""
    with patch('app.core.cache.redis_client') as mock:
        mock.ping.return_value = True
        yield mock

class TestRedisCache:
    """Tests for Redis cache functionality"""
    
    def test_set_cache(self, mock_redis):
        """Test setting a value in Redis cache"""
        set_cache("test-key", "test-value", ttl=600)
        
        # Verify Redis was called with the right parameters
        mock_redis.set.assert_called_once()
        args, kwargs = mock_redis.set.call_args
        assert args[0] == "test-key"
        # The second arg is serialized data
        assert kwargs.get('ex') == 600
    
    def test_get_cache_hit(self, mock_redis):
        """Test getting a value from Redis cache (hit)"""
        # Setup - mock Redis to return a value
        mock_redis.get.return_value = pickle.dumps("test-value")
        
        # Call the function
        result = get_cache("test-key")
        
        # Assertions
        assert result == "test-value"
        mock_redis.get.assert_called_once_with("test-key")
    
    def test_get_cache_miss(self, mock_redis):
        """Test getting a value from Redis cache (miss)"""
        # Setup - mock Redis to return None
        mock_redis.get.return_value = None
        
        # Call the function
        result = get_cache("test-key")
        
        # Assertions
        assert result is None
        mock_redis.get.assert_called_once_with("test-key")
    
    def test_get_cache_error(self, mock_redis):
        """Test graceful error handling when Redis fails"""
        # Setup - mock Redis to raise an exception
        mock_redis.get.side_effect = RedisError("Connection error")
        
        # Call the function - should not raise an exception
        result = get_cache("test-key")
        
        # Assertions
        assert result is None
        mock_redis.get.assert_called_once_with("test-key")
    
    def test_delete_cache(self, mock_redis):
        """Test deleting a value from Redis cache"""
        delete_cache("test-key")
        mock_redis.delete.assert_called_once_with("test-key")
    
    def test_cache_subscription(self, mock_redis):
        """Test caching a subscription"""
        # Call the function
        cache_subscription(mock_subscription_id, mock_subscription_data)
        
        # Verify Redis was called with the right parameters
        assert mock_redis.set.call_count >= 1
        # Check that the main subscription data was cached
        main_key = f"subscription:{mock_subscription_id}"
        # Also verify that important fields were cached separately
        url_key = f"subscription:{mock_subscription_id}:target_url"
        assert url_key in [call[0][0] for call in mock_redis.set.call_args_list]
        
        # Check TTL was set
        for call_args in mock_redis.set.call_args_list:
            assert call_args[1].get('ex') == 1800  # Default TTL
    
    def test_get_subscription_field(self, mock_redis):
        """Test getting specific subscription field"""
        # Setup
        mock_redis.get.return_value = b"https://example.com/webhook"
        
        # Call the function
        result = get_subscription_field(mock_subscription_id, "target_url")
        
        # Assertions
        assert result == "https://example.com/webhook"
        mock_redis.get.assert_called_once_with(f"subscription:{mock_subscription_id}:target_url")
    
    def test_invalidate_subscription_cache(self, mock_redis):
        """Test invalidating subscription cache"""
        # Setup - mock Redis to return keys
        mock_redis.keys.return_value = [
            f"subscription:{mock_subscription_id}",
            f"subscription:{mock_subscription_id}:target_url",
            f"subscription:{mock_subscription_id}:secret_key"
        ]
        
        # Call the function
        invalidate_subscription_cache(mock_subscription_id)
        
        # Assertions
        mock_redis.keys.assert_called_once_with(f"subscription:{mock_subscription_id}*")
        mock_redis.delete.assert_called_once()
        # Verify all keys were passed to delete
        assert len(mock_redis.delete.call_args[0]) == 3
    
    def test_cache_all_subscriptions(self, mock_redis):
        """Test caching multiple subscriptions with pipeline"""
        # Setup - create a list of subscriptions
        subscriptions = [mock_subscription] * 3
        
        # Setup - mock pipeline
        pipeline_mock = MagicMock()
        mock_redis.pipeline.return_value = pipeline_mock
        
        # Call the function
        cache_all_subscriptions(subscriptions)
        
        # Assertions
        mock_redis.pipeline.assert_called_once()
        # Verify execute was called
        pipeline_mock.execute.assert_called_once()
        
        # Verify set was called multiple times on the pipeline
        # One call per subscription + one for all_subscriptions
        assert pipeline_mock.set.call_count >= len(subscriptions) + 1

@pytest.mark.parametrize("redis_error", [
    RedisError("Connection timeout"),
    ConnectionError("Network error"),
    TimeoutError("Operation timed out")
])
def test_redis_error_handling(mock_redis, redis_error):
    """Test that Redis errors are handled gracefully"""
    # Setup - mock Redis to raise an exception for all operations
    mock_redis.get.side_effect = redis_error
    mock_redis.set.side_effect = redis_error
    mock_redis.delete.side_effect = redis_error
    mock_redis.keys.side_effect = redis_error
    mock_redis.pipeline.side_effect = redis_error
    
    # Test all operations - none should raise exceptions
    assert get_cache("test-key") is None
    assert set_cache("test-key", "test-value") is False
    assert delete_cache("test-key") == 0
    
    # Test subscription operations
    assert get_cached_subscription(mock_subscription_id) is None
    # This should not raise an exception
    cache_subscription(mock_subscription_id, mock_subscription_data)
    # This should not raise an exception
    invalidate_subscription_cache(mock_subscription_id)
    # This should not raise an exception
    cache_all_subscriptions([mock_subscription])

@pytest.mark.parametrize("field_name,expected_value", [
    ("target_url", "https://example.com/webhook"),
    ("secret_key", "test-secret-key"),
    ("active", "True")
])
def test_get_subscription_field_values(mock_redis, field_name, expected_value):
    """Test getting different subscription fields"""
    # Setup
    mock_redis.get.return_value = expected_value.encode() if not isinstance(expected_value, bytes) else expected_value
    
    # Call the function
    result = get_subscription_field(mock_subscription_id, field_name)
    
    # Assertions
    assert result == expected_value
    mock_redis.get.assert_called_once_with(f"subscription:{mock_subscription_id}:{field_name}")