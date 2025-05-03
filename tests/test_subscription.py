import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
from unittest.mock import patch, MagicMock
import json

from app.main import app
from app.db.base import Base, get_db
from app.db.models import Subscription
from app.core.cache import cache_subscription, get_cached_subscription, invalidate_subscription_cache

# Set up test database
SQLALCHEMY_DATABASE_URL = "postgresql://neondb_owner:npg_SwdbrNq1QIi4@ep-withered-mouse-a40or4mx-pooler.us-east-1.aws.neon.tech/webhook-url?sslmode=require"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Set up database fixtures
@pytest.fixture(scope="function")
def test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_db):
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


# Override dependency
@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides = {}


# Mock Redis cache for testing
@pytest.fixture(scope="function")
def mock_redis():
    with patch("app.core.cache.redis_client") as mock_redis:
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None
        yield mock_redis


# Test data
@pytest.fixture
def sample_subscription_data():
    return {
        "name": "Test Subscription",
        "target_url": "https://webhook.site/16faa3ea-8b85-4198-8eb8-6887399825d3",
        "secret_key": "test_secret"
    }


@pytest.fixture
def create_test_subscription(db_session, sample_subscription_data):
    subscription = Subscription(
        name=sample_subscription_data["name"],
        target_url=sample_subscription_data["target_url"],
        secret_key=sample_subscription_data["secret_key"],
        is_active=True
    )
    db_session.add(subscription)
    db_session.commit()
    db_session.refresh(subscription)
    return subscription


class TestSubscriptionAPI:
    """Tests for the subscription management API endpoints"""

    def test_create_subscription(self, client, sample_subscription_data, mock_redis):
        """Test creation of a new subscription"""
        # Set up mock for the cache
        mock_redis.set.return_value = True
        
        # Send create request
        response = client.post("/api/subscriptions/", json=sample_subscription_data)
        
        # Check response
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_subscription_data["name"]
        assert data["target_url"] == sample_subscription_data["target_url"]
        assert data["secret_key"] == sample_subscription_data["secret_key"]
        assert data["is_active"] is True
        assert "id" in data
        
        # Verify that cache was called
        mock_redis.set.assert_called()

    def test_get_subscription(self, client, create_test_subscription, mock_redis):
        """Test getting a subscription by ID"""
        # Set up mock for the cache hit scenario
        subscription_id = str(create_test_subscription.id)
        
        # First test cache miss (database hit)
        mock_redis.get.return_value = None
        
        response = client.get(f"/api/subscriptions/{subscription_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == create_test_subscription.name
        assert data["target_url"] == create_test_subscription.target_url
        
        # Verify cache was checked but not found
        mock_redis.get.assert_called()
        mock_redis.set.assert_called()  # Should cache after DB hit
        
        # Reset mocks
        mock_redis.reset_mock()
        
        # Now test cache hit
        cached_subscription = {
            "id": create_test_subscription.id,
            "name": create_test_subscription.name,
            "target_url": create_test_subscription.target_url,
            "secret_key": create_test_subscription.secret_key,
            "is_active": create_test_subscription.is_active,
            "created_at": create_test_subscription.created_at.isoformat() if create_test_subscription.created_at else None,
            "updated_at": create_test_subscription.updated_at.isoformat() if create_test_subscription.updated_at else None
        }
        
        # Mock pickle.loads to return our cached subscription
        with patch("app.core.cache.pickle.loads", return_value=cached_subscription):
            mock_redis.get.return_value = "mock_pickled_data"  # Just needs to be truthy
            
            response = client.get(f"/api/subscriptions/{subscription_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == create_test_subscription.name
            
            # Verify cache was checked and found
            mock_redis.get.assert_called()
            # Should not try to cache again if already found
            mock_redis.set.assert_not_called()

    def test_update_subscription(self, client, create_test_subscription, mock_redis):
        """Test updating a subscription"""
        subscription_id = str(create_test_subscription.id)
        update_data = {
            "name": "Updated Subscription",
            "is_active": False
        }
        
        # Set up mock for cache
        mock_redis.pipeline.return_value = mock_redis
        mock_redis.execute.return_value = None
        
        # Update subscription
        response = client.put(f"/api/subscriptions/{subscription_id}", json=update_data)
        
        # Check response
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["is_active"] == update_data["is_active"]
        assert data["target_url"] == create_test_subscription.target_url  # Unchanged field
        
        # Verify that cache was updated
        mock_redis.set.assert_called()

    def test_delete_subscription(self, client, create_test_subscription, mock_redis):
        """Test deleting a subscription"""
        subscription_id = str(create_test_subscription.id)
        
        # Set up mock for cache
        mock_redis.keys.return_value = [f"subscription:{subscription_id}"]
        mock_redis.delete.return_value = 1
        
        # Delete subscription
        response = client.delete(f"/api/subscriptions/{subscription_id}")
        
        # Check response
        assert response.status_code == 204
        
        # Verify that cache was invalidated
        mock_redis.keys.assert_called_with(f"subscription:{subscription_id}*")
        mock_redis.delete.assert_called()
        
        # Verify subscription was actually deleted
        response = client.get(f"/api/subscriptions/{subscription_id}")
        assert response.status_code == 404

    def test_list_subscriptions(self, client, create_test_subscription):
        """Test listing all subscriptions"""
        response = client.get("/api/subscriptions/")
        
        # Check response
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == str(create_test_subscription.id)
        assert data[0]["name"] == create_test_subscription.name

    def test_nonexistent_subscription(self, client):
        """Test behavior with non-existent subscription ID"""
        fake_id = str(uuid.uuid4())
        
        # Try to get non-existent subscription
        response = client.get(f"/api/subscriptions/{fake_id}")
        assert response.status_code == 404
        
        # Try to update non-existent subscription
        response = client.put(
            f"/api/subscriptions/{fake_id}", 
            json={"name": "This Should Fail"}
        )
        assert response.status_code == 404
        
        # Try to delete non-existent subscription
        response = client.delete(f"/api/subscriptions/{fake_id}")
        assert response.status_code == 404