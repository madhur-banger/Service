from pydantic import BaseModel, HttpUrl
from typing import Optional
from uuid import UUID
from datetime import datetime

class SubscriptionBase(BaseModel):
    name: str
    target_url: HttpUrl
    secret_key: Optional[str] = None

class SubscriptionCreate(SubscriptionBase):
    pass

class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    target_url: Optional[HttpUrl] = None
    secret_key: Optional[str] = None
    is_active: Optional[bool] = None

class SubscriptionResponse(SubscriptionBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool

    class Config:
        from_attributes = True