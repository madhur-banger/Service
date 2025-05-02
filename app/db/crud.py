from sqlalchemy.orm import Session
from app.db.models import Subscription, WebhookDelivery, DeliveryAttempt, DeliveryStatus, AttemptStatus
import uuid
from datetime import datetime, timedelta
from app.config import settings
from typing import List, Optional
from app.core.cache import (
    cache_subscription, get_cached_subscription, 
    invalidate_subscription_cache
)

# Subscription CRUD operations
def create_subscription(db: Session, name: str, target_url: str, secret_key: Optional[str] = None):
    subscription = Subscription(
        name=name,
        target_url=target_url,
        secret_key=secret_key
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription

# Update get_subscription function to use cache
def get_subscription(db: Session, subscription_id: uuid.UUID):
    # Try to get from cache first
    cached = get_cached_subscription(str(subscription_id))
    if cached:
        return cached
    
    # If not in cache, get from database
    subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    
    # If found, cache it
    if subscription:
        cache_subscription(str(subscription_id), subscription)
    
    return subscription


def get_subscriptions(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Subscription).offset(skip).limit(limit).all()

# Update update_subscription to invalidate cache
def update_subscription(db: Session, subscription_id: uuid.UUID, data: dict):
    subscription = get_subscription(db, subscription_id)
    if subscription:
        for key, value in data.items():
            setattr(subscription, key, value)
        subscription.updated_at = datetime.now()
        db.commit()
        db.refresh(subscription)
        
        # Invalidate cache
        invalidate_subscription_cache(str(subscription_id))
    
    return subscription

# Update delete_subscription to invalidate cache
def delete_subscription(db: Session, subscription_id: uuid.UUID):
    subscription = get_subscription(db, subscription_id)
    if subscription:
        db.delete(subscription)
        db.commit()
        
        # Invalidate cache
        invalidate_subscription_cache(str(subscription_id))
        
        return True
    return False

# Webhook Delivery CRUD operations
def create_webhook_delivery(db: Session, subscription_id: uuid.UUID, payload: dict):
    # Calculate expiration time (72 hours from now)
    expires_at = datetime.now() + timedelta(hours=settings.LOG_RETENTION_HOURS)
    
    delivery = WebhookDelivery(
        subscription_id=subscription_id,
        payload=payload,
        status=DeliveryStatus.PENDING,
        expires_at=expires_at
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery

def get_webhook_delivery(db: Session, delivery_id: uuid.UUID):
    return db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).first()

def update_delivery_status(db: Session, delivery_id: uuid.UUID, status: DeliveryStatus):
    delivery = get_webhook_delivery(db, delivery_id)
    if delivery:
        delivery.status = status
        if status == DeliveryStatus.PROCESSING:
            delivery.attempts_count += 1
        db.commit()
        db.refresh(delivery)
    return delivery

# Delivery Attempt CRUD operations
def create_delivery_attempt(db: Session, delivery_id: uuid.UUID, attempt_number: int, status: AttemptStatus, 
                           status_code: Optional[int] = None, response: Optional[str] = None, 
                           error: Optional[str] = None, next_retry_at: Optional[datetime] = None):
    attempt = DeliveryAttempt(
        delivery_id=delivery_id,
        attempt_number=attempt_number,
        status=status,
        status_code=status_code,
        response=response,
        error=error,
        next_retry_at=next_retry_at
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt

def get_delivery_attempts(db: Session, delivery_id: uuid.UUID):
    return db.query(DeliveryAttempt).filter(DeliveryAttempt.delivery_id == delivery_id).order_by(DeliveryAttempt.attempt_number).all()

def get_recent_delivery_attempts(db: Session, subscription_id: uuid.UUID, limit: int = 20):
    return db.query(DeliveryAttempt)\
        .join(WebhookDelivery, DeliveryAttempt.delivery_id == WebhookDelivery.id)\
        .filter(WebhookDelivery.subscription_id == subscription_id)\
        .order_by(DeliveryAttempt.timestamp.desc())\
        .limit(limit)\
        .all()

# Cleanup operations
def cleanup_old_logs(db: Session):
    cutoff_time = datetime.now() - timedelta(hours=settings.LOG_RETENTION_HOURS)
    
    # Get expired deliveries
    expired_deliveries = db.query(WebhookDelivery).filter(
        WebhookDelivery.expires_at < cutoff_time
    ).all()
    
    # Delete their attempts first
    for delivery in expired_deliveries:
        db.query(DeliveryAttempt).filter(
            DeliveryAttempt.delivery_id == delivery.id
        ).delete()
    
    # Then delete the deliveries
    db.query(WebhookDelivery).filter(
        WebhookDelivery.expires_at < cutoff_time
    ).delete()
    
    db.commit()