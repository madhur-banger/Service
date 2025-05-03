from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import uuid
import logging
from app.db.base import get_db
from app.db.crud import (
    create_subscription, get_subscription, get_subscriptions,
    update_subscription, delete_subscription
)
from app.db.models import WebhookDelivery, Subscription
from app.schemas.subscription import (
    SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate
)

router = APIRouter()

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set log level to INFO


@router.post("/", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription_api(subscription: SubscriptionCreate, db: Session = Depends(get_db)):
    # Create subscription in database
    new_subscription = create_subscription(
        db=db,
        name=subscription.name,
        target_url=str(subscription.target_url),
        secret_key=subscription.secret_key
    )
    
    return new_subscription


@router.get("/", response_model=List[SubscriptionResponse])
def read_subscriptions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    subscriptions = get_subscriptions(db, skip=skip, limit=limit)
    return subscriptions


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
def read_subscription(subscription_id: uuid.UUID, db: Session = Depends(get_db)):
    logger.info(f"Fetching subscription {subscription_id} from DB")
    db_subscription = get_subscription(db, subscription_id=subscription_id)
    if db_subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    return db_subscription


@router.put("/{subscription_id}", response_model=SubscriptionResponse)
def update_subscription_api(
    subscription_id: uuid.UUID,
    subscription: SubscriptionUpdate,
    db: Session = Depends(get_db)
):
    try:
        logger.info(f"Updating subscription with ID: {subscription_id}")
        
        # First get the existing subscription
        db_subscription = db.query(Subscription).get(subscription_id)
        if not db_subscription:
            logger.warning(f"Subscription {subscription_id} not found")
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        # Get update data
        update_data = subscription.dict(exclude_unset=True)
        
        # Handle HttpUrl conversion if present
        if "target_url" in update_data and update_data["target_url"] is not None:
            update_data["target_url"] = str(update_data["target_url"])
        
        # Update fields
        for field, value in update_data.items():
            setattr(db_subscription, field, value)
        
        # Commit changes
        db.add(db_subscription)
        db.commit()
        db.refresh(db_subscription)
        
        logger.info(f"Subscription {subscription_id} updated successfully")
        return db_subscription
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating subscription {subscription_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription_api(subscription_id: uuid.UUID, db: Session = Depends(get_db)):
    # First delete all related deliveries
    db.query(WebhookDelivery).filter(
        WebhookDelivery.subscription_id == subscription_id
    ).delete()
    
    # Then delete the subscription
    success = delete_subscription(db, subscription_id=subscription_id)
    if not success:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    return None