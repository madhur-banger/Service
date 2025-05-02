# app/tasks/worker.py

from celery import Celery
from app.config import settings

celery_app = Celery(
    "webhook_service",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.task_routes = {
    "app.tasks.delivery.*": {"queue": "deliveries"},
    "app.tasks.cleanup.*": {"queue": "cleanup"},
}

celery_app.conf.beat_schedule = {
    "cleanup-old-logs": {
        "task": "app.tasks.cleanup.cleanup_old_logs",
        "schedule": 3600.0,  # Run hourly
    },
}

celery_app.autodiscover_tasks(["app.tasks"])

