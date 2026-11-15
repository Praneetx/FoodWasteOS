from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_restaurant
from app.core.security import CurrentUser
from app.db.models import FoodItem, Restaurant
from app.db.session import get_db
from app.schemas.food_items import FoodItemCreate, FoodItemOut, FoodItemUpdate
from app.services import catalog

router = APIRouter(prefix="/food-items", tags=["food items"])


@router.get("", response_model=list[FoodItemOut])
def list_food_items(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> list[FoodItem]:
    return catalog.list_items(db, restaurant.id, include_inactive)


@router.post("", response_model=FoodItemOut, status_code=status.HTTP_201_CREATED)
def create_food_item(
    payload: FoodItemCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> FoodItem:
    user.require_role("owner", "manager")
    return catalog.create_item(db, restaurant.id, payload)


@router.patch("/{item_id}", response_model=FoodItemOut)
def update_food_item(
    item_id: uuid.UUID,
    payload: FoodItemUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> FoodItem:
    user.require_role("owner", "manager")
    item = catalog.get_item_or_404(db, restaurant.id, item_id)
    updates = payload.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] != item.name:
        duplicate = db.scalar(
            select(FoodItem).where(
                FoodItem.restaurant_id == restaurant.id,
                FoodItem.name == updates["name"],
            )
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="food item already exists"
            )

    for field, value in updates.items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)
    return item
