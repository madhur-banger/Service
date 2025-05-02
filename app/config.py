import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_SwdbrNq1QIi4@ep-withered-mouse-a40or4mx-pooler.us-east-1.aws.neon.tech/webhook-url?sslmode=require")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    MAX_RETRY_ATTEMPTS: int = int(os.getenv("MAX_RETRY_ATTEMPTS", "5"))
    LOG_RETENTION_HOURS: int = int(os.getenv("LOG_RETENTION_HOURS", "72"))

    model_config = ConfigDict(
        env_file=".env",
        from_attributes=True,
    )

settings = Settings()
