import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.base import Base
import enum

class DeliveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"

class AttemptStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    target_url = Column(String, nullable=False)
    secret_key = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    event_types = Column(JSON, default=list)

class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"))
    payload = Column(JSON, nullable=False)
    status = Column(Enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))
    attempts_count = Column(Integer, default=0)

    event_type = Column(String, nullable=True)

class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_id = Column(UUID(as_uuid=True), ForeignKey("webhook_deliveries.id"))
    attempt_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    status_code = Column(Integer, nullable=True)
    response = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    status = Column(Enum(AttemptStatus), nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)