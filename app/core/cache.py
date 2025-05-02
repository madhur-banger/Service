import json
from redis import Redis
from app.config import settings
import pickle
from typing import Any, Optional

# Connect to Redis
redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=False)

def set_cache(key: str, value: Any, ttl: int = 900):
    """
    Set a value in Redis cache.
    Default TTL is 15 minutes (900 seconds).
    """
    serialized = pickle.dumps(value)
    redis_client.set(key, serialized, ex=ttl)

def get_cache(key: str) -> Optional[Any]:
    """
    Get a value from Redis cache.
    Returns None if the key doesn't exist.
    """
    value = redis_client.get(key)
    if value:
        return pickle.loads(value)
    return None

def delete_cache(key: str):
    """
    Delete a key from Redis cache.
    """
    redis_client.delete(key)

def cache_subscription(subscription_id: str, subscription_data: dict, ttl: int = 900):
    """
    Cache subscription data.
    """
    key = f"subscription:{subscription_id}"
    set_cache(key, subscription_data, ttl)

def get_cached_subscription(subscription_id: str):
    """
    Get subscription data from cache.
    """
    key = f"subscription:{subscription_id}"
    return get_cache(key)

def invalidate_subscription_cache(subscription_id: str):
    """
    Invalidate subscription cache.
    """
    key = f"subscription:{subscription_id}"
    delete_cache(key)