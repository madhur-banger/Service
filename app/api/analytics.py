from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
from typing import List
from app.db.models import WebhookDelivery, DeliveryAttempt 
from app.db.base import get_db
from app.db.crud import (
    get_webhook_delivery, get_delivery_attempts,
    get_recent_delivery_attempts, get_subscription
)
from app.schemas.webhook import DeliveryResponse, DeliveryDetailResponse, DeliveryAttemptResponse

router = APIRouter()

@router.get("/deliveries/{delivery_id}", response_model=DeliveryDetailResponse)
def get_delivery_status(delivery_id: uuid.UUID, db: Session = Depends(get_db)):
    # Get delivery
    delivery = get_webhook_delivery(db, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    
    # Get all attempts for this delivery
    attempts = get_delivery_attempts(db, delivery_id)
    
    # Combine into response
    return {
        **delivery.__dict__,
        "attempts": attempts
    }

@router.get("/subscriptions/{subscription_id}/deliveries", response_model=List[DeliveryResponse])
def get_recent_deliveries(subscription_id: uuid.UUID, limit: int = 20, db: Session = Depends(get_db)):
    # Verify subscription exists
    subscription = get_subscription(db, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Query WebhookDelivery directly
    deliveries = db.query(WebhookDelivery) \
        .filter(WebhookDelivery.subscription_id == subscription_id) \
        .order_by(WebhookDelivery.created_at.desc()) \
        .limit(limit) \
        .all()
    
    return deliveries

@router.get("/subscriptions/{subscription_id}/attempts", response_model=List[DeliveryAttemptResponse])
def get_recent_attempts(subscription_id: uuid.UUID, limit: int = 20, db: Session = Depends(get_db)):
    # Verify subscription exists
    subscription = get_subscription(db, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Get recent attempts
    attempts = get_recent_delivery_attempts(db, subscription_id, limit)
    
    return attempts