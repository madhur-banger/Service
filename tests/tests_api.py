import pytest
import uuid
import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_subscription():
    # Test creating a subscription
    response = client.post(
        "/api/subscriptions",
        json={
            "name": "Test Subscription",
            "target_url": "https://example.com/webhook",
            "secret_key": "test_secret"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Subscription"
    assert data["target_url"] == "https://example.com/webhook"
    assert data["secret_key"] == "test_secret"
    
    # Store subscription_id for later tests
    subscription_id = data["id"]
    return subscription_id

def test_get_subscriptions():
    response = client.get("/api/subscriptions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_get_subscription(subscription_id):
    response = client.get(f"/api/subscriptions/{subscription_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == subscription_id

def test_ingest_webhook(subscription_id):
    response = client.post(
        f"/api/webhooks/ingest/{subscription_id}",
        json={"message": "Test webhook payload"}
    )
    assert response.status_code == 202
    data = response.json()
    assert "delivery_id" in data
    
    delivery_id = data["delivery_id"]
    return delivery_id

def test_delivery_status(delivery_id):
    # Wait a bit for processing
    import time
    time.sleep(2)
    
    response = client.get(f"/api/analytics/deliveries/{delivery_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == delivery_id
    assert "attempts" in data

def test_update_subscription(subscription_id):
    response = client.put(
        f"/api/subscriptions/{subscription_id}",
        json={"name": "Updated Subscription"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Subscription"

def test_delete_subscription(subscription_id):
    response = client.delete(f"/api/subscriptions/{subscription_id}")
    assert response.status_code == 204

def run_tests():
    subscription_id = test_create_subscription()
    test_get_subscriptions()
    test_get_subscription(subscription_id)
    delivery_id = test_ingest_webhook(subscription_id)
    test_delivery_status(delivery_id)
    test_update_subscription(subscription_id)
    test_delete_subscription(subscription_id)
    print("All tests passed!")

if __name__ == "__main__":
    run_tests()