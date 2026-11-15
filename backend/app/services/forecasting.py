"""Plan generation: the product's core use case.

Orchestrates data loading, the forecaster, the safety buffer and persistence of
the materialized plan. Routers stay thin; this module never imports FastAPI
response models.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import DailySale, FoodItem, Forecast, Restaurant
from app.ml.baseline import DOW_NAMES, METHOD, recommend_preparation, weekday_average_forecast

logger = logging.getLogger(__name__)

MODEL_LABEL = METHOD
HISTORY_COLUMNS = ["food_item_id", "sale_date", "quantity_sold", "promotion", "stockout"]


def local_today(restaurant: Restaurant) -> date:
    try:
        tz = ZoneInfo(restaurant.timezone or "Asia/Kolkata")
    except Exception:  # noqa: BLE001 - invalid stored timezone must not break the app
        tz = ZoneInfo("Asia/Kolkata")
    return datetime.now(tz).date()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _load_history(db: Session, restaurant_id: uuid.UUID, before: date) -> pd.DataFrame:
    rows = db.execute(
        select(
            DailySale.food_item_id,
            DailySale.sale_date,
            DailySale.quantity_sold,
            DailySale.promotion,
            DailySale.stockout,
        ).where(
            DailySale.restaurant_id == restaurant_id,
            DailySale.sale_date < before,
            DailySale.sale_date >= before - timedelta(days=settings.forecast_history_days),
        )
    ).all()
    return pd.DataFrame(rows, columns=HISTORY_COLUMNS)


def _observation_counts(db: Session, restaurant_id: uuid.UUID, before: date) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(DailySale.food_item_id, DailySale.sale_date).where(
            DailySale.restaurant_id == restaurant_id,
            DailySale.sale_date < before,
        )
    ).all()
    counts: dict[uuid.UUID, int] = {}
    for item_id, _ in rows:
        counts[item_id] = counts.get(item_id, 0) + 1
    return counts


def _last_week_sales(
    db: Session, restaurant_id: uuid.UUID, target_date: date
) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(DailySale.food_item_id, DailySale.quantity_sold).where(
            DailySale.restaurant_id == restaurant_id,
            DailySale.sale_date == target_date - timedelta(days=7),
        )
    ).all()
    return {item_id: quantity for item_id, quantity in rows}


def typical_weekday_total(
    db: Session, restaurant_id: uuid.UUID, target_date: date
) -> float | None:
    """Average restaurant-wide sales on the same weekday over the last 4 weeks."""
    rows = db.execute(
        select(DailySale.sale_date, DailySale.quantity_sold).where(
            DailySale.restaurant_id == restaurant_id,
            DailySale.sale_date < target_date,
            DailySale.sale_date >= target_date - timedelta(days=28),
        )
    ).all()
    by_date: dict[date, int] = {}
    for sale_date, quantity in rows:
        by_date[sale_date] = by_date.get(sale_date, 0) + int(quantity)

    same_weekday = [
        total for day, total in sorted(by_date.items()) if day.weekday() == target_date.weekday()
    ][-4:]
    return sum(same_weekday) / len(same_weekday) if same_weekday else None


def _insights(
    db: Session,
    restaurant_id: uuid.UUID,
    target_date: date,
    predicted_total: float,
    recommended_total: float,
    low_confidence: int,
    collecting: int,
) -> list[str]:
    insights: list[str] = []
    dow_name = DOW_NAMES[target_date.weekday()]
    usual = typical_weekday_total(db, restaurant_id, target_date)

    if predicted_total > 0 and usual:
        change = (predicted_total / usual - 1.0) * 100
        if abs(change) < 3:
            insights.append(f"Expected demand is in line with a usual {dow_name}.")
        else:
            direction = "above" if change > 0 else "below"
            insights.append(
                f"Expected demand is {abs(change):.0f}% {direction} a usual {dow_name}."
            )

    if recommended_total > 0:
        insights.append(
            f"Prepare about {recommended_total:.0f} portions in total for {dow_name}."
        )

    if low_confidence:
        insights.append(
            f"{low_confidence} dish{'es' if low_confidence > 1 else ''} have low confidence — "
            "treat those numbers as a starting point."
        )
    if collecting:
        insights.append(
            f"{collecting} dish{'es' if collecting > 1 else ''} need more sales history before "
            "they can be forecast."
        )
    if not insights:
        insights.append("Import at least 7 days of sales per dish to unlock a preparation plan.")
    return insights


def compose_plan(db: Session, restaurant: Restaurant, target_date: date) -> dict:
    """Materialized plan + dishes that still lack history."""
    items = list(
        db.scalars(
            select(FoodItem)
            .where(FoodItem.restaurant_id == restaurant.id, FoodItem.is_active.is_(True))
            .order_by(FoodItem.name)
        )
    )
    forecasts = {
        row.food_item_id: row
        for row in db.scalars(
            select(Forecast).where(
                Forecast.restaurant_id == restaurant.id,
                Forecast.target_date == target_date,
            )
        )
    }
    observations = _observation_counts(db, restaurant.id, target_date)
    last_week = _last_week_sales(db, restaurant.id, target_date)

    plan_items: list[dict] = []
    for item in items:
        forecast = forecasts.get(item.id)
        if forecast is not None:
            plan_items.append(
                {
                    "food_item_id": item.id,
                    "food_item": item.name,
                    "preparation_unit": item.preparation_unit,
                    "predicted_demand": float(forecast.predicted_demand),
                    "recommended_preparation": float(forecast.recommended_preparation),
                    "lower_bound": None if forecast.lower_bound is None else float(forecast.lower_bound),
                    "upper_bound": None if forecast.upper_bound is None else float(forecast.upper_bound),
                    "confidence": forecast.confidence,
                    "method": forecast.method,
                    "sample_size": forecast.sample_size,
                    "last_same_weekday_sold": float(last_week[item.id]) if item.id in last_week else None,
                    "status": "ok",
                    "observations": observations.get(item.id, 0),
                }
            )
        else:
            plan_items.append(
                {
                    "food_item_id": item.id,
                    "food_item": item.name,
                    "preparation_unit": item.preparation_unit,
                    "predicted_demand": None,
                    "recommended_preparation": None,
                    "lower_bound": None,
                    "upper_bound": None,
                    "confidence": None,
                    "method": None,
                    "sample_size": 0,
                    "last_same_weekday_sold": None,
                    "status": "collecting_data",
                    "observations": observations.get(item.id, 0),
                }
            )

    generated_at = max(
        (_as_utc(row.generated_at) for row in forecasts.values()),
        default=datetime.now(timezone.utc),
    )
    predicted_total = sum(
        row["predicted_demand"] for row in plan_items if row["predicted_demand"] is not None
    )
    recommended_total = sum(
        row["recommended_preparation"]
        for row in plan_items
        if row["recommended_preparation"] is not None
    )
    low_confidence = sum(1 for row in plan_items if row["confidence"] == "low")
    collecting = sum(1 for row in plan_items if row["status"] == "collecting_data")

    return {
        "target_date": target_date,
        "model": MODEL_LABEL,
        "generated_at": generated_at,
        "stale": datetime.now(timezone.utc) - generated_at > timedelta(hours=36),
        "insights": _insights(
            db,
            restaurant.id,
            target_date,
            predicted_total,
            recommended_total,
            low_confidence,
            collecting,
        ),
        "items": plan_items,
    }


def generate_plan(
    db: Session,
    restaurant: Restaurant,
    target_date: date,
    force: bool = False,
) -> dict:
    existing = list(
        db.scalars(
            select(Forecast).where(
                Forecast.restaurant_id == restaurant.id,
                Forecast.target_date == target_date,
            )
        )
    )
    if existing and not force:
        return compose_plan(db, restaurant, target_date)

    items = list(
        db.scalars(
            select(FoodItem).where(
                FoodItem.restaurant_id == restaurant.id, FoodItem.is_active.is_(True)
            )
        )
    )
    if not items:
        return compose_plan(db, restaurant, target_date)

    history = _load_history(db, restaurant.id, target_date)
    existing_by_item = {row.food_item_id: row for row in existing}
    generated: set[uuid.UUID] = set()

    for item in items:
        item_history = history[history["food_item_id"] == item.id] if not history.empty else history
        prediction = weekday_average_forecast(
            item_history,
            target_date,
            service_level=settings.forecast_service_level,
            min_observations=settings.forecast_min_observations,
        )
        if prediction is None:
            continue

        row = existing_by_item.get(item.id)
        if row is None:
            row = Forecast(
                restaurant_id=restaurant.id,
                food_item_id=item.id,
                target_date=target_date,
            )
            db.add(row)

        row.predicted_demand = prediction.predicted
        row.lower_bound = prediction.lower
        row.upper_bound = prediction.upper
        row.recommended_preparation = recommend_preparation(
            prediction.predicted, prediction.upper, float(item.batch_size)
        )
        row.confidence = prediction.confidence
        row.model_version = prediction.method
        row.method = prediction.method
        row.sample_size = prediction.sample_size
        row.generated_at = datetime.now(timezone.utc)
        generated.add(item.id)

    for item_id, row in existing_by_item.items():
        if item_id not in generated:
            db.delete(row)

    db.commit()
    logger.info(
        "forecast.generated restaurant=%s date=%s items=%s", restaurant.id, target_date, len(generated)
    )
    return compose_plan(db, restaurant, target_date)


def generate_for_all_restaurants(db: Session, *, days_ahead: int = 1, force: bool = True) -> dict:
    """Materialise upcoming plans for every restaurant (nightly job).

    Plans cover each restaurant's local tomorrow through ``days_ahead`` days out.
    One tenant's failure is rolled back and reported without blocking the others.
    Generation is idempotent, so re-running the job never duplicates forecast rows.
    """
    restaurants = list(db.scalars(select(Restaurant).order_by(Restaurant.created_at)))
    plans = 0
    failures: list[dict] = []

    for restaurant in restaurants:
        restaurant_id = restaurant.id
        start = local_today(restaurant) + timedelta(days=1)
        try:
            for offset in range(days_ahead):
                generate_plan(db, restaurant, start + timedelta(days=offset), force=force)
                plans += 1
        except Exception:  # noqa: BLE001 - one tenant must not stop the nightly run
            db.rollback()
            logger.exception("forecast.nightly_failed restaurant=%s", restaurant_id)
            failures.append({"restaurant_id": restaurant_id, "error": "plan generation failed"})

    logger.info(
        "forecast.nightly restaurants=%s plans=%s failed=%s days_ahead=%s force=%s",
        len(restaurants),
        plans,
        len(failures),
        days_ahead,
        force,
    )
    return {
        "restaurants": len(restaurants),
        "plans_generated": plans,
        "failed": failures,
        "days_ahead": days_ahead,
        "force": force,
    }


def clear_plan(db: Session, restaurant_id: uuid.UUID, target_date: date) -> None:
    db.execute(
        delete(Forecast).where(
            Forecast.restaurant_id == restaurant_id,
            Forecast.target_date == target_date,
        )
    )
    db.commit()
