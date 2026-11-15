from __future__ import annotations

import uuid
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FoodItem


def get_item_or_404(db: Session, restaurant_id: uuid.UUID, item_id: uuid.UUID) -> FoodItem:
    item = db.scalar(
        select(FoodItem).where(
            FoodItem.id == item_id,
            FoodItem.restaurant_id == restaurant_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="food item not found")
    return item


def list_items(db: Session, restaurant_id: uuid.UUID, include_inactive: bool = False) -> list[FoodItem]:
    query = select(FoodItem).where(FoodItem.restaurant_id == restaurant_id)
    if not include_inactive:
        query = query.where(FoodItem.is_active.is_(True))
    return list(db.scalars(query.order_by(FoodItem.name)))


def create_item(db: Session, restaurant_id: uuid.UUID, payload) -> FoodItem:
    duplicate = db.scalar(
        select(FoodItem).where(
            FoodItem.restaurant_id == restaurant_id,
            FoodItem.name == payload.name,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="food item already exists")

    item = FoodItem(
        restaurant_id=restaurant_id,
        name=payload.name,
        preparation_unit=payload.preparation_unit,
        batch_size=payload.batch_size,
        unit_cost=payload.unit_cost,
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
