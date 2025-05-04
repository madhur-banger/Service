from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"  # Default fallback
    MAX_RETRY_ATTEMPTS: int = 5
    LOG_RETENTION_HOURS: int = 72
    WEBHOOK_TIMEOUT: int = 10
    SECRET_KEY: str = "changeme"  # Add this if you plan to use signature verification

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

settings = Settings()
