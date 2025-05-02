from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
from enum import Enum

class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"

class AttemptStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class WebhookPayload(BaseModel):
    payload: Dict[str, Any]

class DeliveryResponse(BaseModel):
    id: UUID
    subscription_id: UUID
    status: DeliveryStatus
    created_at: datetime
    attempts_count: int

    class Config:
        from_attributes = True

class DeliveryAttemptResponse(BaseModel):
    id: UUID
    delivery_id: UUID
    attempt_number: int
    timestamp: datetime
    status_code: Optional[int] = None
    response: Optional[str] = None
    error: Optional[str] = None
    status: AttemptStatus
    next_retry_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DeliveryDetailResponse(DeliveryResponse):
    attempts: List[DeliveryAttemptResponse]

    class Config:
        from_attributes = True