from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FoodWaste
from app.services.catalog import get_item_or_404


def upsert_waste(
    db: Session,
    *,
    restaurant_id: uuid.UUID,
    food_item_id: uuid.UUID,
    waste_date: date,
    quantity_wasted: float,
    reason: str,
    notes: str | None = None,
) -> FoodWaste:
    get_item_or_404(db, restaurant_id, food_item_id)

    waste = db.scalar(
        select(FoodWaste).where(
            FoodWaste.restaurant_id == restaurant_id,
            FoodWaste.food_item_id == food_item_id,
            FoodWaste.waste_date == waste_date,
            FoodWaste.reason == reason,
        )
    )
    if waste is None:
        waste = FoodWaste(
            restaurant_id=restaurant_id,
            food_item_id=food_item_id,
            waste_date=waste_date,
            reason=reason,
        )
        db.add(waste)

    waste.quantity_wasted = Decimal(str(quantity_wasted))
    waste.notes = notes
    db.commit()
    db.refresh(waste)
    return waste
