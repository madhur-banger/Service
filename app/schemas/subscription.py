from pydantic import BaseModel, HttpUrl
from typing import Optional
from uuid import UUID
from datetime import datetime

class SubscriptionBase(BaseModel):
    name: str
    target_url: HttpUrl
    secret_key: Optional[str] = None

     # Method to convert HttpUrl to a string for database storage
    def to_dict(self):
        return {
            "name": self.name,
            "target_url": str(self.target_url),  # Convert HttpUrl to string
            "secret_key": self.secret_key
        }

class SubscriptionCreate(SubscriptionBase):
    pass

class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    target_url: Optional[HttpUrl] = None
    secret_key: Optional[str] = None
    is_active: Optional[bool] = None


    # Method to convert HttpUrl to string for database storage
    def to_dict(self):
        data = {k: v for k, v in self.dict(exclude_unset=True).items()}
        if 'target_url' in data:
            data['target_url'] = str(data['target_url'])  # Convert HttpUrl to string
        return data

class SubscriptionResponse(SubscriptionBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool

    class Config:
        from_attributes = True