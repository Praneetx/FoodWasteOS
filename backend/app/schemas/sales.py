from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class SaleUpsert(BaseModel):
    food_item_id: uuid.UUID
    sale_date: date
    quantity_sold: int = Field(ge=0, le=1_000_000)
    prepared_quantity: int | None = Field(default=None, ge=0, le=1_000_000)
    promotion: bool = False
    stockout: bool = False
    notes: str | None = Field(default=None, max_length=500)


class SaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    food_item_id: uuid.UUID
    food_item: str
    sale_date: date
    quantity_sold: int
    prepared_quantity: int | None
    promotion: bool
    stockout: bool


class ImportErrorItem(BaseModel):
    row: int
    message: str


class ImportReport(BaseModel):
    imported: int
    items_created: list[str]
    skipped: int
    errors: list[ImportErrorItem]
