from app.tasks.worker import celery_app
from app.db.base import SessionLocal
from app.db.crud import cleanup_old_logs

@celery_app.task(name="app.tasks.cleanup.cleanup_old_logs")
def cleanup_old_logs_task():
    """Clean up old webhook delivery logs."""
    db = SessionLocal()
    try:
        cleanup_old_logs(db)
        return {"status": "success", "message": "Cleaned up old logs"}
    finally:
        db.close()