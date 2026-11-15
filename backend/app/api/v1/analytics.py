from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_restaurant
from app.db.models import Restaurant
from app.db.session import get_db
from app.schemas.forecasts import AnalyticsSummaryOut, DashboardOut
from app.services import analytics
from app.services.forecasting import local_today

router = APIRouter(tags=["analytics"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> dict:
    return analytics.dashboard(db, restaurant, date or local_today(restaurant))


@router.get("/analytics/summary", response_model=AnalyticsSummaryOut)
def analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> dict:
    return analytics.summary(db, restaurant, days)
