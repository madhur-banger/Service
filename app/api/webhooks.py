from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
import uuid
from typing import Dict, Any, List

from app.db.base import get_db
from app.db.crud import (
    create_webhook_delivery, 
    get_subscription,
    get_subscriptions_for_event_type,
    update_subscription_event_types
)
from app.tasks.delivery import process_webhook

router = APIRouter()

@router.post("/ingest/{subscription_id}", status_code=status.HTTP_202_ACCEPTED)
async def ingest_webhook(
    subscription_id: uuid.UUID,
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    event_type: str = Query(None, description="Type of event being delivered (e.g., order.created)"),
    db: Session = Depends(get_db)
):
    # Verify subscription exists
    subscription = get_subscription(db, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if not subscription.is_active:
        raise HTTPException(status_code=400, detail="Subscription is not active")
    
    # If event_type is specified, check if subscription is interested in this event
    if event_type and subscription.event_types and len(subscription.event_types) > 0:
        if event_type not in subscription.event_types:
            # The subscription doesn't want this event type, so we don't deliver it
            return {"status": "skipped", "message": f"Subscription is not interested in {event_type} events"}
    
    # Create webhook delivery record
    delivery = create_webhook_delivery(db, subscription_id, payload, event_type)
    
    # Queue webhook processing task
    background_tasks.add_task(process_webhook.delay, str(delivery.id))
    
    return {"status": "accepted", "delivery_id": str(delivery.id)}

@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_webhook_to_all(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    event_type: str = Query(None, description="Type of event being delivered (e.g., order.created)"),
    db: Session = Depends(get_db)
):
    try:
        # Find all subscriptions matching this event type
        subscriptions = get_subscriptions_for_event_type(db, event_type)
        
        if not subscriptions:
            return {"status": "accepted", "message": "No matching subscriptions"}
        
        delivery_ids = []
        
        # Create webhook delivery for each matching subscription
        for subscription in subscriptions:
            # Double-check if subscription wants this event type
            if subscription.event_types and len(subscription.event_types) > 0:
                if event_type not in subscription.event_types:
                    continue  # Skip this subscription
                    
            delivery = create_webhook_delivery(db, subscription.id, payload, event_type)
            delivery_ids.append(str(delivery.id))
            
            # Queue webhook processing task
            background_tasks.add_task(process_webhook.delay, str(delivery.id))
        
        return {"status": "accepted", "delivery_count": len(delivery_ids), "delivery_ids": delivery_ids}
    except Exception as e:
        print(f"Error in ingest_webhook_to_all: {str(e)}")
        raise
    
@router.put("/subscriptions/{subscription_id}/event-types")
async def update_subscription_events(
    subscription_id: uuid.UUID,
    event_types: List[str],
    db: Session = Depends(get_db)
):
    subscription = get_subscription(db, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    updated_subscription = update_subscription_event_types(db, subscription_id, event_types)
    
    return {
        "id": str(updated_subscription.id),
        "name": updated_subscription.name,
        "event_types": updated_subscription.event_types
    }