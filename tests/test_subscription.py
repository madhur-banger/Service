import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.db.models import Subscription
from app.db.crud import create_subscription, get_subscription

client = TestClient(app)

@pytest.fixture
def db_session(monkeypatch):
    """Create a test database session"""
    # This would typically connect to a test database
    # For simplicity, we'll mock the DB session
    from app.db.base import get_db
    
    # Mock database session
    class MockSession:
        def __init__(self):
            self.subscriptions = {}
            
        def add(self, obj):
            if isinstance(obj, Subscription):
                if not obj.id:
                    obj.id = uuid.uuid4()
                self.subscriptions[obj.id] = obj
                
        def commit(self):
            pass
            
        def refresh(self, obj):
            pass
            
        def query(self, model):
            class MockQuery:
                def __init__(self, items):
                    self.items = items
                    
                def filter(self, condition):
                    return self
                    
                def first(self):
                    for item_id, item in self.items.items():
                        return item
                    return None
                    
                def all(self):
                    return list(self.items.values())
                    
                def offset(self, skip):
                    return self
                    
                def limit(self, limit):
                    return self
                    
            return MockQuery(self.subscriptions)
            
        def delete(self, obj):
            if obj.id in self.subscriptions:
                del self.subscriptions[obj.id]
                
        def close(self):
            pass
            
    mock_session = MockSession()
    
    def override_get_db():
        try:
            yield mock_session
        finally:
            mock_session.close()
            
    monkeypatch.setattr("app.db.base.get_db", override_get_db)
    monkeypatch.setattr("app.api.subscriptions.get_db", override_get_db)
    
    return mock_session

def test_create_subscription(db_session):
    response = client.post(
        "/api/subscriptions/",
        json={
            "name": "Test Webhook",
            "target_url": "https://play.svix.com/in/e_0E1oeecxqKdQyakQ6UOd11stHDz/",
            "secret_key": "test_secret",
            "event_types": ["order.created", "customer.updated"]
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Webhook"
    assert data["target_url"] == "https://play.svix.com/in/e_0E1oeecxqKdQyakQ6UOd11stHDz/"
    assert "id" in data
    
def test_get_subscriptions(db_session):
    # Create test subscription first
    subscription = Subscription(
        name="Test Sub",
        target_url="https://play.svix.com/in/e_0E1oeecxqKdQyakQ6UOd11stHDz/",
        secret_key="secret123",
        event_types=["order.created"]
    )
    db_session.add(subscription)
    db_session.commit()
    
    response = client.get("/api/subscriptions/")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    
def test_get_subscription_by_id(db_session):
    # Create test subscription first
    subscription = Subscription(
        name="Test Individual",
        target_url="https://play.svix.com/in/e_0E1oeecxqKdQyakQ6UOd11stHDz/",
        secret_key="individual_secret",
        event_types=["user.login"]
    )
    db_session.add(subscription)
    db_session.commit()
    
    subscription_id = subscription.id
    
    response = client.get(f"/api/subscriptions/{subscription_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Individual"
    assert data["id"] == str(subscription_id)
    
def test_update_subscription(db_session):
    # Create a subscription to update
    subscription = Subscription(
        name="Original Name",
        target_url="https://play.svix.com/in/e_0E1oeecxqKdQyakQ6UOd11stHDz/",
        secret_key="original_secret",
        event_types=[]
    )
    db_session.add(subscription)
    db_session.commit()
    
    subscription_id = subscription.id
    
    # Update the subscription
    response = client.put(
        f"/api/subscriptions/{subscription_id}",
        json={
            "name": "Updated Name",
            "target_url": "https://play.svix.com/in/e_0E1oeecxqKdQyakQ6UOd11stHDz/"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["target_url"] == "https://play.svix.com/in/e_0E1oeecxqKdQyakQ6UOd11stHDz/"
    
def test_delete_subscription(db_session):
    # Create a subscription to delete
    subscription = Subscription(
        name="To Be Deleted",
        target_url="https://play.svix.com/in/e_0E1oeecxqKdQyakQ6UOd11stHDz/",
        secret_key="delete_secret"
    )
    db_session.add(subscription)
    db_session.commit()
    
    subscription_id = subscription.id
    
    response = client.delete(f"/api/subscriptions/{subscription_id}")
    assert response.status_code == 404
    
    # Verify it's deleted
    get_response = client.get(f"/api/subscriptions/{subscription_id}")
    assert get_response.status_code == 404