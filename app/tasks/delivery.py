import json
import httpx
import hmac
import hashlib
from datetime import datetime, timedelta
from app.tasks.worker import celery_app
from app.db.base import SessionLocal
from app.db.crud import (
    get_subscription, get_webhook_delivery, 
    update_delivery_status, create_delivery_attempt,
)
from app.db.models import DeliveryStatus, AttemptStatus, WebhookDelivery
from app.config import settings
import time
from sqlalchemy import select, update
from sqlalchemy.orm import Session

def calculate_backoff_delay(attempt_number: int) -> int:
    """Calculate delay in seconds using exponential backoff."""
    # Base delays: 10s, 30s, 1m, 5m, 15m
    base_delays = [10, 30, 60, 300, 900]
    return base_delays[min(attempt_number - 1, len(base_delays) - 1)]

def generate_signature(payload: dict, secret: str) -> str:
    """Generate HMAC signature for webhook payload."""
    payload_str = json.dumps(payload, sort_keys=True)
    return hmac.new(
        secret.encode(),
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()

@celery_app.task(bind=True, name="app.tasks.delivery.process_webhook", max_retries=5)
def process_webhook(self, delivery_id: str):
    """Process webhook delivery with proper attempt tracking and retries."""
    db = SessionLocal()
    try:
        # Start transaction with row locking
        delivery = db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not delivery:
            self.retry(countdown=60, max_retries=3)
            return {"status": "error", "message": "Delivery not found"}

        # Increment attempt count at start
        delivery.attempts_count += 1
        db.commit()
        db.refresh(delivery)

        # Get subscription details (with caching in production)
        subscription = get_subscription(db, delivery.subscription_id)
        if not subscription:
            return {"status": "error", "message": "Subscription not found"}

        # Prepare delivery attempt
        attempt_data = {
            "delivery_id": delivery_id,
            "attempt_number": delivery.attempts_count,
            "started_at": datetime.utcnow()
        }

        # Prepare headers
        headers = {"Content-Type": "application/json"}
        if subscription.secret_key:
            headers["X-Webhook-Signature"] = generate_signature(
                delivery.payload, 
                subscription.secret_key
            )

        # Execute delivery
        try:
            start_time = time.monotonic()
            response = httpx.post(
                subscription.target_url,
                json=delivery.payload,
                headers=headers,
                timeout=settings.WEBHOOK_TIMEOUT
            )
            duration = time.monotonic() - start_time

            attempt_data.update({
                "status": AttemptStatus.SUCCESS if response.is_success else AttemptStatus.FAILED,
                "status_code": response.status_code,
                "response": response.text[:1000],
                "duration": duration,
                "completed_at": datetime.utcnow()
            })

            if response.is_success:
                update_delivery_status(db, delivery_id, DeliveryStatus.DELIVERED)
                create_delivery_attempt(
                    db,
                    delivery_id=delivery_id,
                    attempt_number=attempt_data["attempt_number"],
                    status=attempt_data["status"],
                    status_code=attempt_data.get("status_code"),
                    response=attempt_data.get("response"),
                    next_retry_at=attempt_data.get("next_retry_at")
                )
                return {"status": "success", "status_code": response.status_code}

            # Handle failed delivery with retry
            if delivery.attempts_count < settings.MAX_RETRY_ATTEMPTS:
                delay = calculate_backoff_delay(delivery.attempts_count)
                attempt_data["next_retry_at"] = datetime.utcnow() + timedelta(seconds=delay)

                create_delivery_attempt(
                    db,
                    delivery_id=delivery_id,
                    attempt_number=attempt_data["attempt_number"],
                    status=attempt_data["status"],
                    status_code=attempt_data.get("status_code"),
                    response=attempt_data.get("response"),
                    next_retry_at=attempt_data.get("next_retry_at")
                )

                self.retry(countdown=delay)

            # Final creation if not retrying
            create_delivery_attempt(
                db,
                delivery_id=delivery_id,
                attempt_number=attempt_data["attempt_number"],
                status=attempt_data["status"],
                status_code=attempt_data.get("status_code"),
                response=attempt_data.get("response"),
                next_retry_at=attempt_data.get("next_retry_at")
            )
            return {"status": "error", "status_code": response.status_code}


        except Exception as e:
            # Handle delivery exceptions
            attempt_data.update({
                "status": AttemptStatus.FAILED,
                "error": str(e)[:1000],
                "completed_at": datetime.utcnow()
            })

            # Log the attempt before retrying
            create_delivery_attempt(
                db,
                delivery_id=delivery_id,
                attempt_number=attempt_data["attempt_number"],
                status=attempt_data["status"],
                error=attempt_data.get("error"),
                next_retry_at=attempt_data.get("next_retry_at")
            )

            if delivery.attempts_count < settings.MAX_RETRY_ATTEMPTS:
                delay = calculate_backoff_delay(delivery.attempts_count)
                attempt_data["next_retry_at"] = datetime.utcnow() + timedelta(seconds=delay)
                
                # Retry after the specified delay
                self.retry(countdown=delay)

            # Final creation if not retrying
            if delivery.attempts_count >= settings.MAX_RETRY_ATTEMPTS:
                update_delivery_status(db, delivery_id, DeliveryStatus.FAILED)

            return {"status": "error", "message": str(e)}

    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()

@celery_app.task(bind=True, name="app.tasks.delivery.retry_webhook_delivery", max_retries=5)
def retry_webhook_delivery(self, delivery_id: str):
    """Retry a failed webhook delivery."""
    return process_webhook(delivery_id)