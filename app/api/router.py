from fastapi import APIRouter
from app.api import subscriptions, webhooks, analytics

router = APIRouter()

router.include_router(
    subscriptions.router,
    prefix="/subscriptions",
    tags=["subscriptions"]
)

router.include_router(
    webhooks.router,
    prefix="/webhooks",
    tags=["webhooks"]
)

router.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["analytics"]
)