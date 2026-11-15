from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_restaurant
from app.core.security import CurrentUser
from app.db.models import Restaurant
from app.db.session import get_db
from app.schemas.forecasts import AccuracyOut, GenerateRequest, PlanOut
from app.services.analytics import accuracy as accuracy_service
from app.services.forecasting import generate_plan, local_today

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("/plan", response_model=PlanOut)
def get_plan(
    target_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> dict:
    target = target_date or local_today(restaurant) + timedelta(days=1)
    return generate_plan(db, restaurant, target)


@router.post("/generate", response_model=PlanOut)
def regenerate_plan(
    payload: GenerateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> dict:
    user.require_role("owner", "manager")
    target = payload.target_date or local_today(restaurant) + timedelta(days=1)
    return generate_plan(db, restaurant, target, force=payload.force)


@router.get("/accuracy", response_model=AccuracyOut)
def forecast_accuracy(
    days: int = Query(default=28, ge=7, le=180),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> dict:
    return accuracy_service(db, restaurant, days)
