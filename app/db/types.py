# app/db/types.py

import uuid
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type if available, otherwise uses CHAR(36) storing UUID as string.
    """
    impl = CHAR
    cache_ok = True  # Required for SQLAlchemy 1.4+ to allow caching

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return str(value)  # Always store UUID as string in SQLite
        return str(uuid.UUID(value))  # Convert from string

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(value)  # Always return UUID instance
