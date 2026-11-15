from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_restaurant
from app.core.security import CurrentUser
from app.db.models import FoodItem, FoodWaste, Restaurant
from app.db.session import get_db
from app.schemas.waste import WasteCreate, WasteOut
from app.services import catalog, waste as waste_service
from app.services.forecasting import local_today

router = APIRouter(prefix="/waste", tags=["waste"])


@router.get("", response_model=list[WasteOut])
def list_waste(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> list[WasteOut]:
    end = end or local_today(restaurant)
    start = start or end - timedelta(days=29)

    rows = db.execute(
        select(FoodWaste, FoodItem.name)
        .join(FoodItem, FoodItem.id == FoodWaste.food_item_id)
        .where(
            FoodWaste.restaurant_id == restaurant.id,
            FoodWaste.waste_date >= start,
            FoodWaste.waste_date <= end,
        )
        .order_by(FoodWaste.waste_date.desc(), FoodItem.name)
    ).all()

    return [
        WasteOut(
            id=waste.id,
            food_item_id=waste.food_item_id,
            food_item=name,
            waste_date=waste.waste_date,
            quantity_wasted=float(waste.quantity_wasted),
            reason=waste.reason,
        )
        for waste, name in rows
    ]


@router.post("", response_model=WasteOut, status_code=201)
def create_waste(
    payload: WasteCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> WasteOut:
    item = catalog.get_item_or_404(db, restaurant.id, payload.food_item_id)
    waste = waste_service.upsert_waste(
        db,
        restaurant_id=restaurant.id,
        food_item_id=payload.food_item_id,
        waste_date=payload.waste_date,
        quantity_wasted=payload.quantity_wasted,
        reason=payload.reason,
        notes=payload.notes,
    )
    return WasteOut(
        id=waste.id,
        food_item_id=waste.food_item_id,
        food_item=item.name,
        waste_date=waste.waste_date,
        quantity_wasted=float(waste.quantity_wasted),
        reason=waste.reason,
    )
