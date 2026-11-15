from fastapi import APIRouter

from app.api.v1 import analytics, cron, forecasts, items, meta, sales, waste

api_router = APIRouter()
api_router.include_router(meta.router)
api_router.include_router(items.router)
api_router.include_router(sales.router)
api_router.include_router(waste.router)
api_router.include_router(forecasts.router)
api_router.include_router(analytics.router)
api_router.include_router(cron.router)
