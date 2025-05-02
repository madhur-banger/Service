from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.db.base import get_db
from app.db.crud import (
    create_subscription, get_subscription, get_subscriptions,
    update_subscription, delete_subscription
)
from app.schemas.subscription import (
    SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate
)

router = APIRouter()

@router.post("/", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription_api(subscription: SubscriptionCreate, db: Session = Depends(get_db)):
    return create_subscription(
        db=db,
        name=subscription.name,
        target_url=str(subscription.target_url),
        secret_key=subscription.secret_key
    )

@router.get("/", response_model=List[SubscriptionResponse])
def read_subscriptions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    subscriptions = get_subscriptions(db, skip=skip, limit=limit)
    return subscriptions

@router.get("/{subscription_id}", response_model=SubscriptionResponse)
def read_subscription(subscription_id: uuid.UUID, db: Session = Depends(get_db)):
    db_subscription = get_subscription(db, subscription_id=subscription_id)
    if db_subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return db_subscription

@router.put("/{subscription_id}", response_model=SubscriptionResponse)
def update_subscription_api(subscription_id: uuid.UUID, subscription: SubscriptionUpdate, db: Session = Depends(get_db)):
    db_subscription = update_subscription(db, subscription_id=subscription_id, data=subscription.dict(exclude_unset=True))
    if db_subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return db_subscription

@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription_api(subscription_id: uuid.UUID, db: Session = Depends(get_db)):
    success = delete_subscription(db, subscription_id=subscription_id)
    if not success:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return None