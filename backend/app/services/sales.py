from __future__ import annotations

import io
import uuid
from datetime import date

import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailySale, FoodItem
from app.services.catalog import get_item_or_404

SALE_ALIASES = {
    "sale_date": "date",
    "item": "food_item",
    "item_name": "food_item",
    "name": "food_item",
    "sold": "quantity_sold",
    "qty": "quantity_sold",
    "quantity": "quantity_sold",
    "prepared": "prepared_quantity",
    "prepared_qty": "prepared_quantity",
    "promo": "promotion",
}
REQUIRED_COLUMNS = ("date", "food_item", "quantity_sold")
_TRUTHY = {"1", "true", "yes", "y", "t"}


def upsert_sale(
    db: Session,
    *,
    restaurant_id: uuid.UUID,
    food_item_id: uuid.UUID,
    sale_date: date,
    quantity_sold: int,
    prepared_quantity: int | None = None,
    promotion: bool = False,
    stockout: bool = False,
    notes: str | None = None,
    commit: bool = True,
) -> DailySale:
    """Idempotent write: one row per dish per day."""
    get_item_or_404(db, restaurant_id, food_item_id)

    sale = db.scalar(
        select(DailySale).where(
            DailySale.restaurant_id == restaurant_id,
            DailySale.food_item_id == food_item_id,
            DailySale.sale_date == sale_date,
        )
    )
    if sale is None:
        sale = DailySale(restaurant_id=restaurant_id, food_item_id=food_item_id, sale_date=sale_date)
        db.add(sale)

    sale.quantity_sold = quantity_sold
    sale.prepared_quantity = prepared_quantity
    sale.promotion = promotion
    sale.stockout = stockout
    sale.notes = notes

    if commit:
        db.commit()
        db.refresh(sale)
    return sale


def _parse_bool(value) -> bool:
    return str(value).strip().lower() in _TRUTHY


def _parse_int(value) -> int:
    number = float(str(value).strip())
    if number != int(number):
        raise ValueError("must be a whole number")
    return int(number)


def import_sales_csv(
    db: Session,
    restaurant_id: uuid.UUID,
    content: bytes,
    max_bytes: int,
) -> dict:
    """Import a CSV with partial success: bad rows are reported, not fatal."""
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty file")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file exceeds {max_bytes // 1_000_000} MB",
        )

    try:
        frame = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    except Exception as exc:  # noqa: BLE001 - user-supplied file
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="could not parse CSV"
        ) from exc

    frame.columns = [str(c).strip().lower().replace(" ", "_") for c in frame.columns]
    frame = frame.rename(columns={c: SALE_ALIASES[c] for c in frame.columns if c in SALE_ALIASES})
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"missing required columns: {', '.join(missing)}",
        )

    items = {
        item.name.strip().lower(): item
        for item in db.scalars(select(FoodItem).where(FoodItem.restaurant_id == restaurant_id))
    }
    records: dict[tuple[uuid.UUID, date], dict] = {}
    errors: list[dict] = []
    created_items: list[str] = []

    for row_number, row in frame.iterrows():
        try:
            parsed_date = pd.to_datetime(str(row["date"]).strip(), errors="coerce")
            if pd.isna(parsed_date):
                raise ValueError("invalid date")
            item_name = str(row["food_item"]).strip()
            if not item_name:
                raise ValueError("food_item is empty")
            quantity = _parse_int(row["quantity_sold"])
            if quantity < 0:
                raise ValueError("quantity_sold must be >= 0")

            prepared = None
            if str(row.get("prepared_quantity", "")).strip():
                prepared = _parse_int(row["prepared_quantity"])
                if prepared < 0:
                    raise ValueError("prepared_quantity must be >= 0")

            records[(item_name, parsed_date.date())] = {
                "item_name": item_name,
                "sale_date": parsed_date.date(),
                "quantity_sold": quantity,
                "prepared_quantity": prepared,
                "promotion": _parse_bool(row.get("promotion", "")),
                "stockout": _parse_bool(row.get("stockout", "")),
                "notes": str(row.get("notes", "")).strip() or None,
            }
        except ValueError as exc:
            errors.append({"row": int(row_number) + 2, "message": str(exc)})

    for record in records.values():
        key = record["item_name"].strip().lower()
        if key not in items:
            item = FoodItem(
                restaurant_id=restaurant_id,
                name=record["item_name"],
                preparation_unit="plate",
                batch_size=1,
            )
            db.add(item)
            items[key] = item
            created_items.append(record["item_name"])
    db.flush()

    for record in records.values():
        item = items[record["item_name"].strip().lower()]
        upsert_sale(
            db,
            restaurant_id=restaurant_id,
            food_item_id=item.id,
            sale_date=record["sale_date"],
            quantity_sold=record["quantity_sold"],
            prepared_quantity=record["prepared_quantity"],
            promotion=record["promotion"],
            stockout=record["stockout"],
            notes=record["notes"],
            commit=False,
        )

    db.commit()
    return {
        "imported": len(records),
        "items_created": created_items,
        "skipped": len(errors),
        "errors": errors[:200],
    }
