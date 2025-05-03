import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import uuid
from unittest.mock import patch, MagicMock
import pickle
import json
from pydantic import HttpUrl

from app.main import app
from app.db.base import Base, get_db
from app.db.models import Subscription, WebhookDelivery, DeliveryAttempt
from app.schemas.subscription import SubscriptionCreate, SubscriptionUpdate
from app.api import subscriptions
from app.core import cache

# Set up SQLite to handle UUID type
def _uuid_to_str(uuid_val):
    """Convert UUID to string for SQLite storage"""
    if uuid_val is not None:
        return str(uuid_val)
    return None

def _str_to_uuid(str_val):
    """Convert string back to UUID when reading from SQLite"""
    if str_val is not None:
        return uuid.UUID(str_val)
    return None

# Set up test database - Using SQLite for faster tests
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# Register UUID conversion listeners
@event.listens_for(engine, "connect")
def do_connect(dbapi_connection, connection_record):
    # Register converters for UUID type
    dbapi_connection.create_function("uuid_to_str", 1, _uuid_to_str)
    dbapi_connection.create_function("str_to_uuid", 1, _str_to_uuid)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Set up database fixtures
@pytest.fixture(scope="function")
def test_db():
    # SQLite doesn't natively support UUID type, so we need to modify the schema
    # Drop all tables if they exist
    Base.metadata.drop_all(bind=engine)
    
    # Create tables with appropriate type conversions for SQLite
    with engine.begin() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            target_url TEXT NOT NULL,
            secret_key TEXT,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            event_types TEXT
        )
        """)
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE
        )
        """)
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS delivery_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id INTEGER NOT NULL,
            attempted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status_code INTEGER,
            response_body TEXT,
            success BOOLEAN NOT NULL DEFAULT FALSE,
            FOREIGN KEY (delivery_id) REFERENCES webhook_deliveries(id) ON DELETE CASCADE
        )
        """)
    
    yield
    
    # Clean up after test
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

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides = {}

@pytest.fixture
def sample_subscription_data():
    return {
        "name": "Test Subscription",
        "target_url": "https://webhook.site/16faa3ea-8b85-4198-8eb8-6887399825d3",
        "secret_key": "test_secret",
        "event_types": ["user.created", "user.updated"]
    }

@pytest.fixture
def create_test_subscription(db_session, sample_subscription_data):
    subscription_id = str(uuid.uuid4())
    
    # Using direct SQL for SQLite compatibility with text() function
    db_session.execute(
        text("""
        INSERT INTO subscriptions (id, name, target_url, secret_key, event_types, active)
        VALUES (:id, :name, :target_url, :secret_key, :event_types, :active)
        """),
        {
            "id": subscription_id,
            "name": sample_subscription_data["name"],
            "target_url": sample_subscription_data["target_url"],
            "secret_key": sample_subscription_data["secret_key"],
            "event_types": json.dumps(sample_subscription_data["event_types"]),
            "active": True
        }
    )
    db_session.commit()
    
    # Create a Subscription object for the test
    subscription = Subscription()
    subscription.id = uuid.UUID(subscription_id)
    subscription.name = sample_subscription_data["name"]
    subscription.target_url = sample_subscription_data["target_url"]
    subscription.secret_key = sample_subscription_data["secret_key"]
    subscription.event_types = sample_subscription_data["event_types"]
    subscription.active = True
    
    return subscription

@pytest.fixture
def create_multiple_subscriptions(db_session):
    subscriptions = []
    
    # Create 3 test subscriptions
    for i in range(3):
        subscription_id = str(uuid.uuid4())
        
        # Insert subscriptions directly with SQL using text()
        db_session.execute(
            text("""
            INSERT INTO subscriptions (id, name, target_url, secret_key, event_types, active)
            VALUES (:id, :name, :target_url, :secret_key, :event_types, :active)
            """),
            {
                "id": subscription_id,
                "name": f"Test Subscription {i}",
                "target_url": f"https://webhook.site/test-{i}",
                "secret_key": f"secret_{i}",
                "event_types": json.dumps(["user.created"]),
                "active": True
            }
        )
        
        # Create a Subscription object for the test
        subscription = Subscription()
        subscription.id = uuid.UUID(subscription_id)
        subscription.name = f"Test Subscription {i}"
        subscription.target_url = f"https://webhook.site/test-{i}"
        subscription.secret_key = f"secret_{i}"
        subscription.event_types = ["user.created"]
        subscription.active = True
        
        subscriptions.append(subscription)
    
    db_session.commit()
    
    # Add webhook delivery and attempt for the first subscription
    subscription_id = str(subscriptions[0].id)
    
    # Insert webhook delivery using text()
    delivery_result = db_session.execute(
        text("""
        INSERT INTO webhook_deliveries (subscription_id, event_type, payload)
        VALUES (:subscription_id, :event_type, :payload)
        RETURNING id
        """),
        {
            "subscription_id": subscription_id,
            "event_type": "user.created",
            "payload": json.dumps({"user_id": "123", "action": "created"})
        }
    )
    
    # Get the delivery_id safely
    delivery_id = delivery_result.scalar()
    
    # Insert delivery attempt using text()
    db_session.execute(
        text("""
        INSERT INTO delivery_attempts (delivery_id, status_code, response_body, success)
        VALUES (:delivery_id, :status_code, :response_body, :success)
        """),
        {
            "delivery_id": delivery_id,
            "status_code": 200,
            "response_body": "OK",
            "success": True
        }
    )
    
    db_session.commit()
    
    return subscriptions

# Mock Redis for all tests
@pytest.fixture(autouse=True)
def mock_redis():
    with patch("app.core.cache.redis_client") as mock:
        # Setup the mock pipeline
        mock.pipeline.return_value = mock
        mock.execute.return_value = None
        yield mock

class TestSubscriptionAPI:
    """Tests for the subscription management API endpoints"""

    def test_create_subscription(self, client, mock_redis, sample_subscription_data):
        """Test creating a subscription"""
        # Send request
        response = client.post("/subscriptions/", json=sample_subscription_data)
        
        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_subscription_data["name"]
        assert data["target_url"] == sample_subscription_data["target_url"]
        assert data["secret_key"] == sample_subscription_data["secret_key"]
        assert data["event_types"] == sample_subscription_data["event_types"]
        assert "id" in data
        
        # Verify Redis was called to cache the new subscription
        # This verification depends on your implementation, but generally it should
        # set something in Redis with the subscription ID
        mock_redis.set.assert_called()

    def test_get_subscription(self, client, mock_redis, create_test_subscription):
        """Test getting a subscription by ID"""
        subscription_id = str(create_test_subscription.id)
        
        # Mock Redis cache miss
        mock_redis.get.return_value = None
        
        # Send request
        response = client.get(f"/subscriptions/{subscription_id}")
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == subscription_id
        assert data["name"] == create_test_subscription.name
        assert data["target_url"] == create_test_subscription.target_url
        
        # Verify Redis was called to try to get from cache
        mock_redis.get.assert_called()

    def test_get_subscription_from_cache(self, client, mock_redis, create_test_subscription):
        """Test getting a subscription from Redis cache"""
        subscription_id = str(create_test_subscription.id)
        
        # Create serialized subscription data for Redis mock
        subscription_dict = {
            "id": subscription_id,
            "name": create_test_subscription.name,
            "target_url": create_test_subscription.target_url,
            "secret_key": create_test_subscription.secret_key,
            "active": True,
            "event_types": create_test_subscription.event_types
        }
        
        # Mock Redis cache hit - this depends on your cache implementation
        serialized = pickle.dumps(subscription_dict)
        mock_redis.get.return_value = serialized
        
        # Send request
        response = client.get(f"/subscriptions/{subscription_id}")
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == subscription_id
        assert data["name"] == create_test_subscription.name
        
        # Verify Redis get was called
        mock_redis.get.assert_called()

    def test_get_all_subscriptions(self, client, mock_redis, create_multiple_subscriptions):
        """Test listing all subscriptions"""
        # Send request
        response = client.get("/subscriptions/")
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        
        # Verify subscription data
        subscription_names = [sub["name"] for sub in data]
        for i in range(3):
            assert f"Test Subscription {i}" in subscription_names

    def test_update_subscription(self, client, mock_redis, create_test_subscription):
        """Test updating a subscription"""
        subscription_id = str(create_test_subscription.id)
        
        update_data = {
            "name": "Updated Subscription",
            "target_url": "https://webhook.site/updated",
            "active": False
        }
        
        # Mock Redis key pattern search and deletion for cache invalidation
        mock_redis.keys.return_value = [f"subscription:{subscription_id}".encode()]
        mock_redis.delete.return_value = 1
        
        # Send request
        response = client.put(f"/subscriptions/{subscription_id}", json=update_data)
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["target_url"] == update_data["target_url"]
        assert data["active"] == update_data["active"]
        
        # Check that Redis invalidation was called
        mock_redis.keys.assert_called_with(f"subscription:{subscription_id}*")
        mock_redis.delete.assert_called()
        
        # Verify update in database
        response = client.get(f"/subscriptions/{subscription_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["target_url"] == update_data["target_url"]
        assert data["active"] == update_data["active"]

    def test_update_subscription_partial(self, client, mock_redis, create_test_subscription):
        """Test partial update of a subscription"""
        subscription_id = str(create_test_subscription.id)
        
        # Only update the name
        update_data = {
            "name": "Partially Updated Subscription"
        }
        
        # Mock Redis key pattern search and deletion
        mock_redis.keys.return_value = [f"subscription:{subscription_id}".encode()]
        mock_redis.delete.return_value = 1
        
        # Send request
        response = client.put(f"/subscriptions/{subscription_id}", json=update_data)
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["target_url"] == create_test_subscription.target_url  # Unchanged
        assert data["active"] == create_test_subscription.active  # Unchanged
        
        # Check that Redis invalidation was called
        mock_redis.keys.assert_called_with(f"subscription:{subscription_id}*")
        mock_redis.delete.assert_called()

    def test_delete_subscription(self, client, mock_redis, create_test_subscription):
        """Test deleting a subscription"""
        subscription_id = str(create_test_subscription.id)
        
        # Mock Redis key pattern search and deletion
        mock_redis.keys.return_value = [f"subscription:{subscription_id}".encode()]
        mock_redis.delete.return_value = 1
        
        # Send request
        response = client.delete(f"/subscriptions/{subscription_id}")
        
        # Assert response
        assert response.status_code == 204
        
        # Check that Redis invalidation was called
        mock_redis.keys.assert_called_with(f"subscription:{subscription_id}*")
        mock_redis.delete.assert_called()
        
        # Verify the subscription is gone
        response = client.get(f"/subscriptions/{subscription_id}")
        assert response.status_code == 404

    def test_delete_subscription_with_deliveries(self, client, mock_redis, create_multiple_subscriptions):
        """Test deleting a subscription that has webhook deliveries and attempts"""
        subscription_id = str(create_multiple_subscriptions[0].id)
        
        # Mock Redis key pattern search and deletion
        mock_redis.keys.return_value = [f"subscription:{subscription_id}".encode()]
        mock_redis.delete.return_value = 1
        
        # Send request
        response = client.delete(f"/subscriptions/{subscription_id}")
        
        # Assert response
        assert response.status_code == 204
        
        # Verify the subscription is gone
        response = client.get(f"/subscriptions/{subscription_id}")
        assert response.status_code == 404

    def test_nonexistent_subscription(self, client, mock_redis):
        """Test handling of nonexistent subscriptions"""
        fake_id = str(uuid.uuid4())
        
        # Mock Redis cache miss
        mock_redis.get.return_value = None
        
        # Test GET with nonexistent ID
        response = client.get(f"/subscriptions/{fake_id}")
        assert response.status_code == 404
        
        # Test PUT with nonexistent ID
        response = client.put(f"/subscriptions/{fake_id}", json={"name": "New Name"})
        assert response.status_code == 404
        
        # Test DELETE with nonexistent ID
        response = client.delete(f"/subscriptions/{fake_id}")
        assert response.status_code == 404

    def test_invalid_uuid(self, client):
        """Test handling of invalid UUID format"""
        invalid_id = "not-a-uuid"
        
        # Test GET with invalid UUID
        response = client.get(f"/subscriptions/{invalid_id}")
        assert response.status_code == 422
        
        # Test PUT with invalid UUID
        response = client.put(f"/subscriptions/{invalid_id}", json={"name": "New Name"})
        assert response.status_code == 422
        
        # Test DELETE with invalid UUID
        response = client.delete(f"/subscriptions/{invalid_id}")
        assert response.status_code == 422

    def test_update_subscription_event_types(self, client, mock_redis, create_test_subscription):
        """Test updating event types for a subscription"""
        subscription_id = str(create_test_subscription.id)
        new_event_types = ["order.created", "payment.completed"]
        
        # Mock Redis key pattern search and deletion
        mock_redis.keys.return_value = [f"subscription:{subscription_id}".encode()]
        mock_redis.delete.return_value = 1
        
        # Send request
        response = client.put(f"/subscriptions/{subscription_id}/event-types", 
                             json=new_event_types)
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == subscription_id
        assert data["event_types"] == new_event_types
        
        # Check that Redis invalidation was called
        mock_redis.keys.assert_called_with(f"subscription:{subscription_id}*")
        mock_redis.delete.assert_called()

    def test_invalid_target_url(self, client, mock_redis):
        """Test handling of invalid target URL"""
        data = {
            "name": "Invalid URL Test",
            "target_url": "not-a-url",
            "secret_key": "test_secret"
        }
        
        # Send request
        response = client.post("/subscriptions/", json=data)
        
        # Assert response indicates validation error
        assert response.status_code == 422
        error_data = response.json()
        assert "detail" in error_data
        # The error should be about the invalid URL
        assert any("url" in error["msg"].lower() for error in error_data["detail"])

class TestCacheIntegration:
    """Tests for Redis cache integration with subscription API"""

    def test_cache_hit_get_subscription(self, client, mock_redis, create_test_subscription):
        """Test that subscription is retrieved from cache if available"""
        subscription_id = str(create_test_subscription.id)
        
        # Prepare cache hit data
        subscription_dict = {
            "id": subscription_id,
            "name": "Cached Subscription",  # Different from DB to verify cache hit
            "target_url": create_test_subscription.target_url,
            "secret_key": create_test_subscription.secret_key,
            "active": True,
            "event_types": create_test_subscription.event_types
        }
        
        # Set up mock to return cached data
        mock_redis.get.return_value = pickle.dumps(subscription_dict)
        
        # Send request
        with patch('app.db.crud.get_subscription') as mock_get_subscription:
            # This should not be called if cache hit
            mock_get_subscription.return_value = create_test_subscription
            response = client.get(f"/subscriptions/{subscription_id}")
        
        # Assert response has cached data
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Cached Subscription"  # From cache, not DB
        
        # Verify Redis get was called
        mock_redis.get.assert_called()

    def test_cache_invalidation_on_update(self, client, mock_redis, create_test_subscription):
        """Test that cache is invalidated when updating a subscription"""
        subscription_id = str(create_test_subscription.id)
        update_data = {"name": "Updated Via Test"}
        
        # Mock Redis keys and delete for invalidation
        mock_redis.keys.return_value = [
            f"subscription:{subscription_id}".encode(),
            f"subscription:{subscription_id}:target_url".encode()
        ]
        mock_redis.delete.return_value = 2
        
        # Send update request
        response = client.put(f"/subscriptions/{subscription_id}", json=update_data)
        assert response.status_code == 200
        
        # Verify cache invalidation calls
        mock_redis.keys.assert_called_with(f"subscription:{subscription_id}*")
        mock_redis.delete.assert_called()

    def test_cache_invalidation_on_delete(self, client, mock_redis, create_test_subscription):
        """Test that cache is invalidated when deleting a subscription"""
        subscription_id = str(create_test_subscription.id)
        
        # Mock Redis keys and delete for invalidation
        mock_redis.keys.return_value = [
            f"subscription:{subscription_id}".encode(),
            f"subscription:{subscription_id}:secret_key".encode(),
            f"subscription:{subscription_id}:active".encode()
        ]
        mock_redis.delete.return_value = 3
        
        # Send delete request
        response = client.delete(f"/subscriptions/{subscription_id}")
        assert response.status_code == 204
        
        # Verify cache invalidation calls
        mock_redis.keys.assert_called_with(f"subscription:{subscription_id}*")
        mock_redis.delete.assert_called()

    def test_cache_exception_handling(self, client, mock_redis, create_test_subscription):
        """Test graceful handling of Redis exceptions"""
        subscription_id = str(create_test_subscription.id)
        
        # Mock Redis to raise an exception
        mock_redis.get.side_effect = Exception("Redis connection error")
        
        # Request should still succeed, falling back to DB
        response = client.get(f"/subscriptions/{subscription_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == subscription_id
        
        # Verify Redis was attempted
        mock_redis.get.assert_called()

    @patch('app.core.cache.get_cached_subscription')
    @patch('app.core.cache.cache_subscription')
    def test_subscription_caching_flow(self, mock_cache_subscription, mock_get_cached_sub, 
                                     client, create_test_subscription):
        """Test the full caching flow for subscriptions"""
        subscription_id = str(create_test_subscription.id)
        
        # First request - cache miss
        mock_get_cached_sub.return_value = None
        
        response = client.get(f"/subscriptions/{subscription_id}")
        assert response.status_code == 200
        
        # Verify cache was checked
        mock_get_cached_sub.assert_called_with(subscription_id)
        
        # Verify subscription was cached after retrieval
        mock_cache_subscription.assert_called()
        
        # Reset mocks for second request
        mock_get_cached_sub.reset_mock()
        mock_cache_subscription.reset_mock()
        
        # Second request - cache hit
        mock_get_cached_sub.return_value = {
            "id": subscription_id,
            "name": create_test_subscription.name,
            "target_url": create_test_subscription.target_url,
            "secret_key": create_test_subscription.secret_key,
            "active": True,
            "event_types": create_test_subscription.event_types
        }
        
        response = client.get(f"/subscriptions/{subscription_id}")
        assert response.status_code == 200
        
        # Verify cache was checked
        mock_get_cached_sub.assert_called_with(subscription_id)
        
        # Cache hit, so caching function not called again
        mock_cache_subscription.assert_not_called()