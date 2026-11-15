from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WasteReason = Literal["overproduction", "unsold", "spoilage", "expired", "other"]


class WasteCreate(BaseModel):
    food_item_id: uuid.UUID
    waste_date: date
    quantity_wasted: float = Field(gt=0, le=1_000_000)
    reason: WasteReason
    notes: str | None = Field(default=None, max_length=500)


class WasteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    food_item_id: uuid.UUID
    food_item: str
    waste_date: date
    quantity_wasted: float
    reason: str
