from sqlalchemy.orm import Session
from app.db.models import Subscription, WebhookDelivery, DeliveryAttempt, DeliveryStatus, AttemptStatus
import uuid
from datetime import datetime, timedelta
from app.config import settings
from typing import List, Optional
from sqlalchemy import or_, cast, String
from sqlalchemy.orm import Session

# Subscription CRUD operations
def create_subscription(db: Session, name: str, target_url: str, secret_key: Optional[str] = None, event_types: Optional[List[str]] = None):
    subscription = Subscription(
        name=name,
        target_url=target_url,
        secret_key=secret_key,
        event_types=event_types if event_types else []
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription

def get_subscription(db: Session, subscription_id: uuid.UUID):
    subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    return subscription

def get_subscriptions(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Subscription).offset(skip).limit(limit).all()

def get_subscriptions_for_event_type(db: Session, event_type: Optional[str] = None):
    """Get all active subscriptions that match the given event type or have no event type preferences"""
    query = db.query(Subscription).filter(Subscription.is_active == True)

    if event_type:
        # Use a text-based approach that works regardless of JSON structure
        query = query.filter(
            or_(
                Subscription.event_types.is_(None),  # No event types specified (accepts all)
                cast(Subscription.event_types, String) == '[]',  # Empty array as string
                cast(Subscription.event_types, String).like(f'%"{event_type}"%')  # String contains the event_type
            )
        )

    return query.all()

def update_subscription(db: Session, subscription_id: uuid.UUID, data: dict):
    subscription = get_subscription(db, subscription_id)
    if subscription:
        for key, value in data.items():
            setattr(subscription, key, value)
        subscription.updated_at = datetime.now()
        db.commit()
        db.refresh(subscription)
    
    return subscription

def update_subscription_event_types(db: Session, subscription_id: uuid.UUID, event_types: List[str]):
    """Update just the event types for a subscription"""
    subscription = get_subscription(db, subscription_id)
    if subscription:
        subscription.event_types = event_types
        subscription.updated_at = datetime.now()
        db.commit()
        db.refresh(subscription)
    
    return subscription

def delete_subscription(db: Session, subscription_id: uuid.UUID):
    subscription = get_subscription(db, subscription_id)
    if subscription:
        db.delete(subscription)
        db.commit()
        return True
    return False

# Webhook Delivery CRUD operations
def create_webhook_delivery(db: Session, subscription_id: uuid.UUID, payload: dict, event_type: str = None):
    # Calculate expiration time (72 hours from now)
    expires_at = datetime.now() + timedelta(hours=settings.LOG_RETENTION_HOURS)
    
    delivery = WebhookDelivery(
        subscription_id=subscription_id,
        payload=payload,
        status=DeliveryStatus.PENDING,
        event_type=event_type,
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

# Filter deliveries by event type
def get_deliveries_by_event_type(db: Session, event_type: str, skip: int = 0, limit: int = 100):
    """Get all webhook deliveries with a specific event type"""
    return db.query(WebhookDelivery)\
        .filter(WebhookDelivery.event_type == event_type)\
        .order_by(WebhookDelivery.created_at.desc())\
        .offset(skip)\
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