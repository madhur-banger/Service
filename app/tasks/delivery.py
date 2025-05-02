import json
import httpx
import hmac
import hashlib
from datetime import datetime, timedelta
from app.tasks.worker import celery_app
from app.db.base import SessionLocal
from app.db.crud import (
    get_subscription, get_webhook_delivery, 
    update_delivery_status, create_delivery_attempt
)
from app.db.models import DeliveryStatus, AttemptStatus
from app.config import settings
import time

def calculate_backoff_delay(attempt_number: int) -> int:
    """Calculate delay in seconds using exponential backoff."""
    # Base delays: 10s, 30s, 1m, 5m, 15m
    base_delays = [10, 30, 60, 300, 900]
    
    if attempt_number <= len(base_delays):
        return base_delays[attempt_number - 1]
    
    # For any attempts beyond our predefined list, use the last value
    return base_delays[-1]

def generate_signature(payload: dict, secret: str) -> str:
    """Generate HMAC signature for webhook payload."""
    payload_str = json.dumps(payload, sort_keys=True)
    return hmac.new(
        secret.encode(),
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()

@celery_app.task(name="app.tasks.delivery.process_webhook")
def process_webhook(delivery_id: str):
    """Process webhook delivery."""
    db = SessionLocal()
    try:
        # Get delivery and subscription info
        delivery = get_webhook_delivery(db, delivery_id)
        if not delivery:
            return {"status": "error", "message": "Delivery not found"}
        
        # Update delivery status to processing
        delivery = update_delivery_status(db, delivery_id, DeliveryStatus.PROCESSING)
        
        # Get subscription details
        subscription = get_subscription(db, delivery.subscription_id)
        if not subscription:
            return {"status": "error", "message": "Subscription not found"}
        
        # Prepare headers and sign payload if needed
        headers = {"Content-Type": "application/json"}
        if subscription.secret_key:
            signature = generate_signature(delivery.payload, subscription.secret_key)
            headers["X-Webhook-Signature"] = signature
        
        # Attempt delivery
        try:
            response = httpx.post(
                subscription.target_url,
                json=delivery.payload,
                headers=headers,
                timeout=10.0
            )
            
            # Create attempt record
            if 200 <= response.status_code < 300:
                # Success
                create_delivery_attempt(
                    db,
                    delivery_id,
                    delivery.attempts_count,
                    AttemptStatus.SUCCESS,
                    status_code=response.status_code,
                    response=response.text[:1000]  # Limit response size
                )
                update_delivery_status(db, delivery_id, DeliveryStatus.DELIVERED)
                return {"status": "success", "status_code": response.status_code}
            else:
                # Failed but got a response
                next_retry_time = None
                if delivery.attempts_count < settings.MAX_RETRY_ATTEMPTS:
                    delay = calculate_backoff_delay(delivery.attempts_count)
                    next_retry_time = datetime.now() + timedelta(seconds=delay)
                    retry_webhook_delivery.apply_async(
                        args=[str(delivery_id)],
                        countdown=delay
                    )
                
                create_delivery_attempt(
                    db,
                    delivery_id,
                    delivery.attempts_count,
                    AttemptStatus.FAILED,
                    status_code=response.status_code,
                    response=response.text[:1000],
                    next_retry_at=next_retry_time
                )
                
                if delivery.attempts_count >= settings.MAX_RETRY_ATTEMPTS:
                    update_delivery_status(db, delivery_id, DeliveryStatus.FAILED)
                
                return {"status": "error", "status_code": response.status_code}
                
        except Exception as e:
            # Network error, timeout, etc.
            next_retry_time = None
            if delivery.attempts_count < settings.MAX_RETRY_ATTEMPTS:
                delay = calculate_backoff_delay(delivery.attempts_count)
                next_retry_time = datetime.now() + timedelta(seconds=delay)
                retry_webhook_delivery.apply_async(
                    args=[str(delivery_id)],
                    countdown=delay
                )
            
            create_delivery_attempt(
                db,
                delivery_id,
                delivery.attempts_count,
                AttemptStatus.FAILED,
                error=str(e)[:1000],
                next_retry_at=next_retry_time
            )
            
            if delivery.attempts_count >= settings.MAX_RETRY_ATTEMPTS:
                update_delivery_status(db, delivery_id, DeliveryStatus.FAILED)
            
            return {"status": "error", "message": str(e)}
            
    finally:
        db.close()

@celery_app.task(name="app.tasks.delivery.retry_webhook_delivery")
def retry_webhook_delivery(delivery_id: str):
    """Retry a failed webhook delivery."""
    return process_webhook(delivery_id)