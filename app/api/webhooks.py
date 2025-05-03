from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
import uuid
from typing import Dict, Any

from app.db.base import get_db
from app.db.crud import create_webhook_delivery, get_subscription
from app.tasks.delivery import process_webhook

router = APIRouter()

@router.post("/ingest/{subscription_id}", status_code=status.HTTP_202_ACCEPTED)
async def ingest_webhook(
    subscription_id: uuid.UUID,
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    # Verify subscription exists
    subscription = get_subscription(db, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if not subscription.is_active:
        raise HTTPException(status_code=400, detail="Subscription is not active")
    
    # Create webhook delivery record - IMPORTANT: commit immediately
    delivery = create_webhook_delivery(db, subscription_id, payload)
    db.commit()  # Explicit commit before task starts
    
    # Queue webhook processing task
    process_webhook.delay(str(delivery.id))
    
    return {"status": "accepted", "delivery_id": str(delivery.id)}