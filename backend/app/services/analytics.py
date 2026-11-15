"""Read-side aggregations for the dashboard, analytics and forecast accuracy.

All figures are computed from tenant-scoped rows. Cost figures degrade to
``None`` for dishes without a unit cost rather than silently pretending waste
is free.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import DailySale, FoodItem, FoodWaste, Forecast, Restaurant
from app.ml.evaluate import ForecastError, metrics
from app.services.forecasting import generate_plan, local_today, typical_weekday_total

logger = logging.getLogger(__name__)


def _daily_sales(db: Session, restaurant_id: uuid.UUID, start: date, end: date) -> dict[date, int]:
    rows = db.execute(
        select(DailySale.sale_date, func.sum(DailySale.quantity_sold))
        .where(
            DailySale.restaurant_id == restaurant_id,
            DailySale.sale_date >= start,
            DailySale.sale_date <= end,
        )
        .group_by(DailySale.sale_date)
    ).all()
    return {day: int(quantity or 0) for day, quantity in rows}


def _waste_detail(
    db: Session, restaurant: Restaurant, start: date, end: date
) -> list[dict]:
    rows = db.execute(
        select(
            FoodWaste.food_item_id,
            FoodItem.name,
            FoodWaste.waste_date,
            func.sum(FoodWaste.quantity_wasted),
            FoodItem.unit_cost,
        )
        .join(FoodItem, FoodItem.id == FoodWaste.food_item_id)
        .where(
            FoodWaste.restaurant_id == restaurant.id,
            FoodWaste.waste_date >= start,
            FoodWaste.waste_date <= end,
        )
        .group_by(
            FoodWaste.food_item_id,
            FoodItem.name,
            FoodWaste.waste_date,
            FoodItem.unit_cost,
        )
    ).all()

    default_cost = float(restaurant.default_unit_cost) if restaurant.default_unit_cost is not None else None
    detail = []
    for item_id, name, waste_date, quantity, unit_cost in rows:
        quantity_value = float(quantity or 0)
        cost = float(unit_cost) if unit_cost is not None else default_cost
        detail.append(
            {
                "food_item_id": item_id,
                "food_item": name,
                "date": waste_date,
                "quantity": quantity_value,
                "cost": round(quantity_value * cost, 2) if cost is not None else None,
            }
        )
    return detail


def _waste_totals(detail: list[dict]) -> tuple[float, float, bool]:
    known = [row for row in detail if row["cost"] is not None]
    total_cost = round(sum(row["cost"] for row in known), 2)
    total_quantity = sum(row["quantity"] for row in detail)
    return total_quantity, total_cost, bool(known)


def dashboard(db: Session, restaurant: Restaurant, on_date: date) -> dict:
    start = on_date - timedelta(days=13)
    sales = _daily_sales(db, restaurant.id, start, on_date)
    waste_detail = _waste_detail(db, restaurant, start, on_date)

    waste_by_date: dict[date, float] = {}
    for row in waste_detail:
        waste_by_date[row["date"]] = waste_by_date.get(row["date"], 0.0) + row["quantity"]

    series = [
        {
            "date": day,
            "sold": sales.get(day, 0),
            "wasted": round(waste_by_date.get(day, 0.0), 2),
        }
        for day in (start + timedelta(days=offset) for offset in range(14))
    ]

    sales_today = sales.get(on_date, 0)
    waste_today = round(waste_by_date.get(on_date, 0.0), 2)
    total_quantity, total_cost, has_cost = _waste_totals(
        [row for row in waste_detail if row["date"] == on_date]
    )

    denominator = sales_today + waste_today
    tomorrow_date = on_date + timedelta(days=1)
    tomorrow = None
    try:
        plan = generate_plan(db, restaurant, tomorrow_date)
        planned = [row for row in plan["items"] if row["predicted_demand"] is not None]
        predicted_total = sum(row["predicted_demand"] for row in planned)
        usual = typical_weekday_total(db, restaurant.id, tomorrow_date)
        tomorrow = {
            "target_date": tomorrow_date,
            "predicted_total": round(predicted_total, 2),
            "recommended_total": round(
                sum(row["recommended_preparation"] for row in planned), 2
            ),
            "vs_usual_pct": round((predicted_total / usual - 1) * 100, 1)
            if usual and predicted_total
            else None,
        }
    except Exception:  # noqa: BLE001 - dashboard must render even if a plan fails
        logger.exception("dashboard: tomorrow plan unavailable restaurant=%s", restaurant.id)

    return {
        "date": on_date,
        "sales_quantity": sales_today,
        "waste_quantity": waste_today,
        "waste_rate": round(waste_today / denominator, 4) if denominator else 0.0,
        "estimated_waste_cost": total_cost if has_cost else None,
        "currency": restaurant.currency,
        "series": series,
        "tomorrow": tomorrow,
    }


def summary(db: Session, restaurant: Restaurant, days: int = 30) -> dict:
    end = local_today(restaurant)
    start = end - timedelta(days=max(days, 1) - 1)
    sales = _daily_sales(db, restaurant.id, start, end)
    waste_detail = _waste_detail(db, restaurant, start, end)

    waste_by_date: dict[date, float] = {}
    per_item: dict[uuid.UUID, dict] = {}
    for row in waste_detail:
        waste_by_date[row["date"]] = waste_by_date.get(row["date"], 0.0) + row["quantity"]
        bucket = per_item.setdefault(
            row["food_item_id"],
            {"food_item": row["food_item"], "quantity": 0.0, "cost": 0.0, "has_cost": False},
        )
        bucket["quantity"] += row["quantity"]
        if row["cost"] is not None:
            bucket["cost"] += row["cost"]
            bucket["has_cost"] = True

    sales_total = sum(sales.values())
    waste_total, waste_cost, has_cost = _waste_totals(waste_detail)
    denominator = sales_total + waste_total

    weekly: dict[date, dict] = {}
    for day, quantity in sales.items():
        bucket_start = day - timedelta(days=day.weekday())
        weekly.setdefault(bucket_start, {"week_start": bucket_start, "sold": 0, "wasted": 0.0})
        weekly[bucket_start]["sold"] += quantity
    for day, quantity in waste_by_date.items():
        bucket_start = day - timedelta(days=day.weekday())
        weekly.setdefault(bucket_start, {"week_start": bucket_start, "sold": 0, "wasted": 0.0})
        weekly[bucket_start]["wasted"] += quantity

    top_wasted = sorted(per_item.values(), key=lambda row: row["quantity"], reverse=True)[:5]

    return {
        "start": start,
        "end": end,
        "sales_quantity": sales_total,
        "waste_quantity": round(waste_total, 2),
        "waste_rate": round(waste_total / denominator, 4) if denominator else 0.0,
        "estimated_waste_cost": waste_cost if has_cost else None,
        "currency": restaurant.currency,
        "top_wasted": [
            {
                "food_item": row["food_item"],
                "quantity": round(row["quantity"], 2),
                "cost": round(row["cost"], 2) if row["has_cost"] else None,
            }
            for row in top_wasted
        ],
        "weekly_trend": [
            {
                "week_start": row["week_start"],
                "sold": row["sold"],
                "wasted": round(row["wasted"], 2),
            }
            for row in sorted(weekly.values(), key=lambda item: item["week_start"])
        ],
    }


def accuracy(db: Session, restaurant: Restaurant, days: int = 28) -> dict:
    """Compare materialized forecasts with the sales that actually happened."""
    end = local_today(restaurant)
    start = end - timedelta(days=max(days, 1))

    rows = db.execute(
        select(Forecast, DailySale.quantity_sold)
        .join(
            DailySale,
            and_(
                DailySale.food_item_id == Forecast.food_item_id,
                DailySale.sale_date == Forecast.target_date,
            ),
        )
        .where(
            Forecast.restaurant_id == restaurant.id,
            Forecast.target_date >= start,
            Forecast.target_date < end,
        )
    ).all()

    errors = [
        ForecastError(
            target_date=forecast.target_date,
            actual=float(quantity),
            predicted=float(forecast.predicted_demand),
            lower=None if forecast.lower_bound is None else float(forecast.lower_bound),
            upper=None if forecast.upper_bound is None else float(forecast.upper_bound),
        )
        for forecast, quantity in rows
    ]
    result = metrics(errors)

    stockout_days = db.scalar(
        select(func.count(func.distinct(DailySale.sale_date))).where(
            DailySale.restaurant_id == restaurant.id,
            DailySale.sale_date >= start,
            DailySale.stockout.is_(True),
        )
    )

    return {
        "window_days": days,
        "evaluated_items": len({forecast.food_item_id for forecast, _ in rows}),
        "mae": result["mae"],
        "wape": result["wape"],
        "bias": result["bias"],
        "within_band_pct": result["within_band_pct"],
        "stockout_days": int(stockout_days or 0),
    }
