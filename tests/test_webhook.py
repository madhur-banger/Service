import pytest
import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.db.models import Subscription, WebhookDelivery, DeliveryStatus

client = TestClient(app)

@pytest.fixture
def mock_db():
    """Create a mock database with test data"""
    subscription_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    
    # Create mock subscription
    subscription = MagicMock()
    subscription.id = subscription_id
    subscription.name = "Test Webhook"
    subscription.target_url = "https://play.svix.com/in/e_0E1oeecxqKdQyakQ6UOd11stHDz/"
    subscription.is_active = True
    subscription.event_types = ["order.created", "customer.updated"]
    
    # Create mock delivery
    delivery = MagicMock()
    delivery.id = delivery_id
    delivery.subscription_id = subscription_id
    delivery.payload = {"order_id": "12345", "status": "completed"}
    delivery.status = DeliveryStatus.PENDING
    delivery.event_type = "order.created"
    
    # Mock get_subscription function
    def mock_get_subscription(db, subscription_id):
        if subscription_id == subscription.id:
            return subscription
        return None
    
    # Mock create_webhook_delivery function
    def mock_create_webhook_delivery(db, sub_id, payload, event_type=None):
        if sub_id == subscription_id:
            delivery.payload = payload
            delivery.event_type = event_type
            return delivery
        return None
    
    # Mock get_subscriptions_for_event_type
    def mock_get_subscriptions_for_event_type(db, event_type=None):
        if event_type is None or event_type in subscription.event_types:
            return [subscription]
        return []
    
    # Mock update_subscription_event_types
    def mock_update_subscription_event_types(db, sub_id, event_types):
        if sub_id == subscription_id:
            subscription.event_types = event_types
            return subscription
        return None
    
    # Apply mocks
    with patch("app.api.webhooks.get_subscription", mock_get_subscription), \
         patch("app.api.webhooks.create_webhook_delivery", mock_create_webhook_delivery), \
         patch("app.api.webhooks.get_subscriptions_for_event_type", mock_get_subscriptions_for_event_type), \
         patch("app.api.webhooks.update_subscription_event_types", mock_update_subscription_event_types), \
         patch("app.api.webhooks.process_webhook.delay") as mock_process:
         
        mock_data = {
            "subscription": subscription,
            "delivery": delivery,
            "process_webhook_mock": mock_process
        }
        
        yield mock_data

def test_ingest_webhook(mock_db):
    subscription_id = mock_db["subscription"].id
    payload = {"order_id": "12345", "total": 99.99}
    
    response = client.post(
        f"/api/webhooks/ingest/{subscription_id}",
        json=payload,
        params={"event_type": "order.created"}
    )
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "delivery_id" in data
    
    # Verify background task was added
    mock_db["process_webhook_mock"].assert_called_once_with(str(mock_db["delivery"].id))

def test_ingest_webhook_inactive_subscription(mock_db):
    subscription_id = mock_db["subscription"].id
    mock_db["subscription"].is_active = False
    
    response = client.post(
        f"/api/webhooks/ingest/{subscription_id}",
        json={"test": "data"},
        params={"event_type": "order.created"}
    )
    
    assert response.status_code == 400
    assert "not active" in response.json()["detail"]
    
    # Set back to active for other tests
    mock_db["subscription"].is_active = True

def test_ingest_webhook_to_all(mock_db):
    payload = {"customer_id": "C789", "action": "signup"}
    
    response = client.post(
        "/api/webhooks/ingest",
        json=payload,
        params={"event_type": "customer.updated"}
    )
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["delivery_count"] == 1
    assert len(data["delivery_ids"]) == 1
    
    # Verify background task was added
    mock_db["process_webhook_mock"].assert_called_once_with(str(mock_db["delivery"].id))

def test_update_subscription_event_types(mock_db):
    subscription_id = mock_db["subscription"].id
    new_event_types = ["product.created", "invoice.paid"]
    
    response = client.put(
        f"/api/webhooks/subscriptions/{subscription_id}/event-types",
        json=new_event_types
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(subscription_id)
    assert data["event_types"] == new_event_types