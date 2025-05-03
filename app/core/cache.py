import json
from redis import Redis
from redis.exceptions import RedisError
import pickle
from typing import Any, Optional, Dict, Union
import logging
from app.config import settings

# Set up logging
logger = logging.getLogger(__name__)

# Connect to Redis
redis_client = Redis.from_url(
    settings.REDIS_URL, 
    decode_responses=False,
    socket_timeout=1.0,  # Short timeout to fail fast
    socket_connect_timeout=1.0,
    retry_on_timeout=True,
    health_check_interval=30
)

# Verify connection on startup
try:
    redis_client.ping()
    logger.info("Successfully connected to Redis cache")
except RedisError as e:
    logger.error(f"Failed to connect to Redis: {str(e)}. Service will continue but caching will be degraded.")
    # We don't use a fallback here - if Redis is down, we'll just bypass the cache
    # and go directly to the database

def set_cache(key: str, value: Any, ttl: int = 900):
    """
    Set a value in Redis cache.
    Default TTL is 15 minutes (900 seconds).
    """
    try:
        serialized = pickle.dumps(value)
        redis_client.set(key, serialized, ex=ttl)
        logger.debug(f"Set key {key} in Redis cache with TTL {ttl}s")
        return True
    except RedisError as e:
        logger.warning(f"Redis cache set failed for key {key}: {str(e)}")
        return False

def get_cache(key: str) -> Optional[Any]:
    """
    Get a value from Redis cache.
    Returns None if the key doesn't exist or if Redis is unavailable.
    """
    try:
        value = redis_client.get(key)
        if value:
            logger.debug(f"Cache hit for key {key} in Redis")
            return pickle.loads(value)
        logger.debug(f"Cache miss for key {key} in Redis")
        return None
    except RedisError as e:
        logger.warning(f"Redis cache get failed for key {key}: {str(e)}")
        return None

def delete_cache(key: str):
    """
    Delete a key from Redis cache.
    """
    try:
        result = redis_client.delete(key)
        logger.debug(f"Deleted key {key} from Redis cache: {result} keys removed")
        return result
    except RedisError as e:
        logger.warning(f"Redis cache delete failed for key {key}: {str(e)}")
        return 0

def flush_cache():
    """
    Flush the entire cache - mainly for testing.
    """
    try:
        redis_client.flushdb()
        logger.info("Flushed Redis cache")
        return True
    except RedisError as e:
        logger.warning(f"Redis cache flush failed: {str(e)}")
        return False

def cache_subscription(subscription_id: str, subscription_data: Dict, ttl: int = 1800):
    """
    Cache subscription data with a default TTL of 30 minutes.
    This is particularly important for webhook processing where 
    subscription details are frequently accessed.
    """
    key = f"subscription:{subscription_id}"
    result = set_cache(key, subscription_data, ttl)
    if result:
        logger.info(f"Cached subscription data for ID {subscription_id}, TTL: {ttl}s")
    
    # For webhook processing optimization, cache important fields separately
    # with the same TTL for direct access
    try:
        if "target_url" in subscription_data:
            url_key = f"subscription:{subscription_id}:target_url"
            redis_client.set(url_key, subscription_data["target_url"], ex=ttl)
        
        if "secret_key" in subscription_data:
            secret_key = f"subscription:{subscription_id}:secret_key"
            redis_client.set(secret_key, subscription_data["secret_key"], ex=ttl)
            
        if "active" in subscription_data:
            active_key = f"subscription:{subscription_id}:active"
            redis_client.set(active_key, str(subscription_data["active"]), ex=ttl)
    except RedisError as e:
        logger.warning(f"Failed to cache subscription fields for {subscription_id}: {str(e)}")

def get_cached_subscription(subscription_id: str) -> Optional[Dict]:
    """
    Get subscription data from cache.
    """
    key = f"subscription:{subscription_id}"
    return get_cache(key)

def get_subscription_field(subscription_id: str, field: str) -> Optional[str]:
    """
    Get a specific subscription field from cache.
    This is optimized for webhook processing where you often
    only need specific fields like target_url or secret_key.
    """
    try:
        key = f"subscription:{subscription_id}:{field}"
        value = redis_client.get(key)
        if value:
            if isinstance(value, bytes):
                return value.decode('utf-8')
            return value
        return None
    except RedisError as e:
        logger.warning(f"Failed to get subscription field {field} for {subscription_id}: {str(e)}")
        return None

def invalidate_subscription_cache(subscription_id: str):
    """
    Invalidate subscription cache including all related fields.
    """
    try:
        # Get all keys matching this subscription pattern
        pattern = f"subscription:{subscription_id}*"
        keys = redis_client.keys(pattern)
        
        if keys:
            redis_client.delete(*keys)
            logger.info(f"Invalidated all cache entries for subscription ID {subscription_id}, {len(keys)} keys removed")
        else:
            logger.debug(f"No cache entries found for subscription ID {subscription_id}")
    except RedisError as e:
        logger.warning(f"Failed to invalidate cache for subscription {subscription_id}: {str(e)}")
        # Fallback to single key deletion
        key = f"subscription:{subscription_id}"
        delete_cache(key)

def cache_all_subscriptions(subscriptions: list, ttl: int = 1800):
    """
    Cache a list of subscriptions for batch operations.
    Uses Redis pipeline for better performance when caching multiple items.
    """
    try:
        pipeline = redis_client.pipeline()
        
        subscription_ids = []
        for subscription in subscriptions:
            subscription_id = str(subscription.id)
            subscription_ids.append(subscription_id)
            
            # Add subscription data to pipeline
            key = f"subscription:{subscription_id}"
            serialized = pickle.dumps(subscription.__dict__)
            pipeline.set(key, serialized, ex=ttl)
            
            # Cache important fields separately
            if hasattr(subscription, 'target_url'):
                pipeline.set(f"subscription:{subscription_id}:target_url", 
                           subscription.target_url, ex=ttl)
            
            if hasattr(subscription, 'secret_key'):
                pipeline.set(f"subscription:{subscription_id}:secret_key", 
                           subscription.secret_key, ex=ttl)
                
            if hasattr(subscription, 'active'):
                pipeline.set(f"subscription:{subscription_id}:active", 
                           str(subscription.active), ex=ttl)
        
        # Also cache the list itself for potential list operations
        pipeline.set("all_subscriptions", pickle.dumps(subscription_ids), ex=ttl)
        
        # Execute all commands at once
        pipeline.execute()
        logger.info(f"Cached {len(subscriptions)} subscriptions in a single pipeline operation")
    except RedisError as e:
        logger.warning(f"Failed to cache all subscriptions: {str(e)}")
        # Don't use fallback - if Redis is down, we'll just bypass the cache