import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
from unittest.mock import patch, MagicMock
import json
import httpx
from datetime import datetime, timedelta

from app.main import app
from app.db.base import Base, get_db
from app.db.models import Subscription, WebhookDelivery, DeliveryStatus, DeliveryAttempt, AttemptStatus
from app.tasks.delivery import process_webhook, calculate_backoff_delay, generate_signature

# Set up test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
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


# Test data
@pytest.fixture
def sample_subscription(db_session):
    subscription = Subscription(
        name="Test Webhook Subscription",
        target_url="https://webhook.site/16faa3ea-8b85-4198-8eb8-6887399825d3",
        secret_key="test_webhook_secret",
        is_active=True
    )
    db_session.add(subscription)
    db_session.commit()
    db_session.refresh(subscription)
    return subscription


@pytest.fixture
def sample_payload():
    return {
        "event": "user.created",
        "payload": {
            "user_id": "123456",
            "email": "test@example.com",
            "created_at": datetime.now().isoformat()
        }
    }


@pytest.fixture
def sample_delivery(db_session, sample_subscription, sample_payload):
    delivery = WebhookDelivery(
        subscription_id=sample_subscription.id,
        payload=sample_payload,
        status=DeliveryStatus.PENDING,
        expires_at=datetime.now() + timedelta(hours=72)
    )
    db_session.add(delivery)
    db_session.commit()
    db_session.refresh(delivery)
    return delivery


class TestWebhookIngestion:
    """Tests for webhook ingestion API"""

    def test_ingest_webhook(self, client, sample_subscription, sample_payload):
        """Test ingesting a webhook"""
        # Mock celery task
        with patch('app.tasks.delivery.process_webhook.delay') as mock_process:
            # Send webhook
            subscription_id = str(sample_subscription.id)
            response = client.post(f"/api/webhooks/ingest/{subscription_id}", json=sample_payload)
            
            # Check response
            assert response.status_code == 202
            data = response.json()
            assert "delivery_id" in data
            assert data["status"] == "accepted"
            
            # Verify task was queued
            mock_process.assert_called_once()
            
            # Verify delivery was created in DB
            db_session = next(get_db())
            delivery = db_session.query(WebhookDelivery).filter(
                WebhookDelivery.id == uuid.UUID(data["delivery_id"])
            ).first()
            
            assert delivery is not None
            assert delivery.status == DeliveryStatus.PENDING
            assert delivery.payload == sample_payload
            assert delivery.subscription_id == sample_subscription.id

    def test_ingest_webhook_inactive_subscription(self, client, sample_subscription, sample_payload, db_session):
        """Test ingesting a webhook with inactive subscription"""
        # Set subscription to inactive
        sample_subscription.is_active = False
        db_session.commit()
        db_session.refresh(sample_subscription)
        
        # Try to send webhook
        subscription_id = str(sample_subscription.id)
        response = client.post(f"/api/webhooks/ingest/{subscription_id}", json=sample_payload)
        
        # Check it was rejected
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "not active" in data["detail"]

    def test_ingest_webhook_nonexistent_subscription(self, client, sample_payload):
        """Test ingesting a webhook with non-existent subscription"""
        fake_id = str(uuid.uuid4())
        response = client.post(f"/api/webhooks/ingest/{fake_id}", json=sample_payload)
        
        # Check it was rejected
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"]


class TestWebhookDelivery:
    """Tests for webhook delivery functionality"""
    
    def test_webhook_delivery_success(self, db_session, sample_delivery):
        """Test successful webhook delivery"""
        delivery_id = str(sample_delivery.id)
        
        # Mock the httpx.post method to simulate successful response
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.status_code = 200
        mock_response.text = "Webhook received"
        
        with patch('httpx.post', return_value=mock_response) as mock_post:
            # Process the webhook
            result = process_webhook(delivery_id)
            
            # Check the result
            assert result["status"] == "success"
            assert result["status_code"] == 200
            
            # Verify HTTP call was made correctly
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert kwargs["json"] == sample_delivery.payload
            assert "X-Webhook-Signature" in kwargs["headers"]
            
            # Verify delivery was updated
            db_session.refresh(sample_delivery)
            assert sample_delivery.status == DeliveryStatus.DELIVERED
            assert sample_delivery.attempts_count == 1
            
            # Verify attempt was recorded
            attempts = db_session.query(DeliveryAttempt).filter(
                DeliveryAttempt.delivery_id == sample_delivery.id
            ).all()
            assert len(attempts) == 1
            assert attempts[0].status == AttemptStatus.SUCCESS
            assert attempts[0].status_code == 200
            assert attempts[0].response == "Webhook received"

    def test_webhook_delivery_failure_retry(self, db_session, sample_delivery):
        """Test webhook delivery failure with retry"""
        delivery_id = str(sample_delivery.id)
        
        # Mock the httpx.post method to simulate failure
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch('httpx.post', return_value=mock_response) as mock_post, \
             patch('app.tasks.delivery.process_webhook.retry') as mock_retry:
            
            # Process the webhook
            result = process_webhook(delivery_id)
            
            # Check the result
            assert result["status"] == "error"
            assert result["status_code"] == 500
            
            # Verify HTTP call was made
            mock_post.assert_called_once()
            
            # Verify retry was attempted
            mock_retry.assert_called_once()
            
            # Verify delivery status and attempts
            db_session.refresh(sample_delivery)
            assert sample_delivery.attempts_count == 1
            
            # Verify attempt was recorded
            attempts = db_session.query(DeliveryAttempt).filter(
                DeliveryAttempt.delivery_id == sample_delivery.id
            ).all()
            assert len(attempts) == 1
            assert attempts[0].status == AttemptStatus.FAILED
            assert attempts[0].status_code == 500
            assert attempts[0].next_retry_at is not None

    def test_webhook_delivery_http_exception(self, db_session, sample_delivery):
        """Test webhook delivery with HTTP exception"""
        delivery_id = str(sample_delivery.id)
        
        # Mock the httpx.post method to raise an exception
        with patch('httpx.post', side_effect=httpx.ConnectError("Connection refused")) as mock_post, \
             patch('app.tasks.delivery.process_webhook.retry') as mock_retry:
            
            # Process the webhook
            result = process_webhook(delivery_id)
            
            # Check the result
            assert result["status"] == "error"
            assert "Connection refused" in result["message"]
            
            # Verify HTTP call attempt was made
            mock_post.assert_called_once()
            
            # Verify retry was attempted
            mock_retry.assert_called_once()
            
            # Verify delivery status and attempts
            db_session.refresh(sample_delivery)
            assert sample_delivery.attempts_count == 1
            
            # Verify attempt was recorded
            attempts = db_session.query(DeliveryAttempt).filter(
                DeliveryAttempt.delivery_id == sample_delivery.id
            ).all()
            assert len(attempts) == 1
            assert attempts[0].status == AttemptStatus.FAILED
            assert "Connection refused" in attempts[0].error
            assert attempts[0].next_retry_at is not None

    def test_webhook_max_retries_exceeded(self, db_session, sample_delivery):
        """Test webhook delivery when max retries are exceeded"""
        delivery_id = str(sample_delivery.id)
        
        # Set the attempts to maximum
        sample_delivery.attempts_count = 4  # This will be incremented to 5 during processing
        db_session.commit()
        
        # Mock the httpx.post method to simulate failure
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch('httpx.post', return_value=mock_response) as mock_post, \
             patch('app.tasks.delivery.process_webhook.retry') as mock_retry:
            
            # Process the webhook one final time
            result = process_webhook(delivery_id)
            
            # Check the result
            assert result["status"] == "error"
            
            # Verify HTTP call was made
            mock_post.assert_called_once()
            
            # Verify retry was NOT attempted (exceeded max attempts)
            mock_retry.assert_not_called()
            
            # Verify delivery status is FAILED
            db_session.refresh(sample_delivery)
            assert sample_delivery.attempts_count == 5
            assert sample_delivery.status == DeliveryStatus.FAILED
            
            # Verify attempt was recorded
            attempts = db_session.query(DeliveryAttempt).filter(
                DeliveryAttempt.delivery_id == sample_delivery.id
            ).all()
            assert len(attempts) == 1
            assert attempts[0].status == AttemptStatus.FAILED


class TestWebhookUtilityFunctions:
    """Tests for utility functions in the webhook delivery system"""
    
    def test_calculate_backoff_delay(self):
        """Test exponential backoff calculation"""
        assert calculate_backoff_delay(1) == 10  # First retry: 10 seconds
        assert calculate_backoff_delay(2) == 30  # Second retry: 30 seconds
        assert calculate_backoff_delay(3) == 60  # Third retry: 1 minute
        assert calculate_backoff_delay(4) == 300  # Fourth retry: 5 minutes
        assert calculate_backoff_delay(5) == 900  # Fifth retry: 15 minutes
        assert calculate_backoff_delay(6) == 900  # Beyond fifth retry: still 15 minutes

    def test_generate_signature(self):
        """Test HMAC signature generation"""
        payload = {"test": "data", "user": 123}
        secret = "secret_key"
        
        # Generate signature
        signature = generate_signature(payload, secret)
        
        # Verify it's a valid hex string of the expected length
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA-256 produces 32 bytes = 64 hex chars
        
        # Verify deterministic output
        assert generate_signature(payload, secret) == signature
        
        # Verify different payloads produce different signatures
        different_payload = {"test": "different", "user": 123}
        different_signature = generate_signature(different_payload, secret)
        assert different_signature != signature
        
        # Verify different secrets produce different signatures
        different_secret = "different_secret"
        different_signature = generate_signature(payload, different_secret)
        assert different_signature != signature


class TestConcurrentWebhooks:
    """Tests for concurrent webhook processing"""
    
    @pytest.mark.asyncio
    async def test_concurrent_webhook_processing(self, client, sample_subscription, sample_payload):
        """Test processing multiple webhooks concurrently"""
        import asyncio
        
        # Mock celery task to avoid actual processing
        with patch('app.tasks.delivery.process_webhook.delay') as mock_process:
            
            # Create multiple concurrent requests
            subscription_id = str(sample_subscription.id)
            num_requests = 5
            
            async def send_webhook():
                # Create a modified payload to ensure unique deliveries
                modified_payload = sample_payload.copy()
                modified_payload["request_id"] = str(uuid.uuid4())
                
                async with httpx.AsyncClient(app=app, base_url="http://testserver") as ac:
                    response = await ac.post(
                        f"/api/webhooks/ingest/{subscription_id}", 
                        json=modified_payload
                    )
                    return response
            
            # Send multiple concurrent requests
            responses = await asyncio.gather(*[send_webhook() for _ in range(num_requests)])
            
            # Verify all requests were accepted
            for response in responses:
                assert response.status_code == 202
                
            # Verify the task was queued for each request
            assert mock_process.call_count == num_requests