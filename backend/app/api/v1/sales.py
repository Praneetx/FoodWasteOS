from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_restaurant
from app.core.config import settings
from app.core.security import CurrentUser
from app.db.models import DailySale, FoodItem, Restaurant
from app.db.session import get_db
from app.schemas.sales import ImportReport, SaleOut, SaleUpsert
from app.services import catalog, sales as sales_service
from app.services.forecasting import local_today

router = APIRouter(prefix="/sales", tags=["sales"])

CSV_TEMPLATE = (
    "date,food_item,quantity_sold,prepared_quantity,promotion,stockout,notes\n"
    "2026-11-14,Chicken Biryani,95,130,false,false,\n"
    "2026-11-14,Paneer Tikka,30,38,true,false,\n"
)


def _to_out(sale: DailySale, item_name: str) -> SaleOut:
    return SaleOut(
        id=sale.id,
        food_item_id=sale.food_item_id,
        food_item=item_name,
        sale_date=sale.sale_date,
        quantity_sold=sale.quantity_sold,
        prepared_quantity=sale.prepared_quantity,
        promotion=sale.promotion,
        stockout=sale.stockout,
    )


@router.get("", response_model=list[SaleOut])
def list_sales(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    food_item_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> list[SaleOut]:
    end = end or local_today(restaurant)
    start = start or end - timedelta(days=29)

    query = (
        select(DailySale, FoodItem.name)
        .join(FoodItem, FoodItem.id == DailySale.food_item_id)
        .where(
            DailySale.restaurant_id == restaurant.id,
            DailySale.sale_date >= start,
            DailySale.sale_date <= end,
        )
    )
    if food_item_id is not None:
        query = query.where(DailySale.food_item_id == food_item_id)

    rows = db.execute(
        query.order_by(DailySale.sale_date.desc(), FoodItem.name)
    ).all()
    return [_to_out(sale, name) for sale, name in rows]


@router.post("", response_model=SaleOut)
def upsert_sale(
    payload: SaleUpsert,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> SaleOut:
    item = catalog.get_item_or_404(db, restaurant.id, payload.food_item_id)
    sale = sales_service.upsert_sale(
        db,
        restaurant_id=restaurant.id,
        food_item_id=payload.food_item_id,
        sale_date=payload.sale_date,
        quantity_sold=payload.quantity_sold,
        prepared_quantity=payload.prepared_quantity,
        promotion=payload.promotion,
        stockout=payload.stockout,
        notes=payload.notes,
    )
    return _to_out(sale, item.name)


@router.post("/import", response_model=ImportReport)
def import_sales(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    restaurant: Restaurant = Depends(get_restaurant),
) -> dict:
    user.require_role("owner", "manager")
    content = file.file.read()
    return sales_service.import_sales_csv(
        db, restaurant.id, content, settings.max_csv_bytes
    )


@router.get("/template.csv")
def sales_template() -> Response:
    return Response(
        content=CSV_TEMPLATE,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="foodwasteos-sales-template.csv"'},
    )
