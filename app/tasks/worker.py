# app/tasks/worker.py

from celery import Celery
from celery.signals import after_setup_logger
from app.config import settings
import logging

# Initialize Celery application
celery_app = Celery(
    "webhook_service",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.delivery",
        "app.tasks.cleanup"
    ]
)

# Configure task routes
celery_app.conf.task_routes = {
    "app.tasks.delivery.*": {"queue": "deliveries"},
    "app.tasks.cleanup.*": {"queue": "cleanup"},
}

# Enhanced worker configuration
celery_app.conf.update(
    # Reliability settings
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    
    # Monitoring and visibility
    task_track_started=True,
    worker_send_task_events=True,
    worker_proc_alive_timeout=30,
    
    # Timeout settings
    task_time_limit=300,
    task_soft_time_limit=240,
    
    # Result handling
    result_extended=True,
    result_persistent=True,
    
    # Serialization
    accept_content=['json'],
    task_serializer='json',
    result_serializer='json',
)

# Periodic tasks configuration
celery_app.conf.beat_schedule = {
    "cleanup-old-logs": {
        "task": "app.tasks.cleanup.cleanup_old_logs",
        "schedule": 3600.0,  # Hourly
        "options": {
            "queue": "cleanup",
            "expires": 3600,
        }
    },
}

# Configure logging
@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# Final task discovery
celery_app.autodiscover_tasks(["app.tasks"], force=True)

# Debugging utility
if __name__ == '__main__':
    celery_app.start()