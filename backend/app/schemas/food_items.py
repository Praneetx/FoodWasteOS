from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class FoodItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    preparation_unit: str = Field(default="plate", min_length=1, max_length=32)
    batch_size: float = Field(default=1, gt=0, le=100_000)
    unit_cost: float | None = Field(default=None, ge=0, le=1_000_000)


class FoodItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    preparation_unit: str | None = Field(default=None, min_length=1, max_length=32)
    batch_size: float | None = Field(default=None, gt=0, le=100_000)
    unit_cost: float | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None


class FoodItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    preparation_unit: str
    batch_size: float
    unit_cost: float | None
    is_active: bool
