"""Audit trail for plan generation.

One ``model_runs`` row is written each time plans are (re)computed so a tenant's
training window, parameters and measured accuracy can be reviewed later. The row
is added to the caller's session and committed together with the forecasts, so a
run is never recorded without its plan (and vice versa).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import ModelRun, Restaurant
from app.services.evaluation import evaluate_rows, forecast_actual_rows

logger = logging.getLogger(__name__)

ACCURACY_WINDOW_DAYS = 28


def _decimal(value: float, places: int) -> Decimal:
    return Decimal(str(round(float(value), places)))


def _recent_accuracy(db: Session, restaurant: Restaurant, as_of: date) -> dict | None:
    """MAE/WAPE/bias of past forecasts that already have actuals; ``None`` if there are none.

    Never fabricates zeros: a restaurant with no scored forecasts yet gets NULL metrics.
    """
    try:
        rows = forecast_actual_rows(
            db, restaurant.id, as_of - timedelta(days=ACCURACY_WINDOW_DAYS), as_of
        )
        if not rows:
            return None
        result = evaluate_rows(rows)
        result["evaluated_items"] = len({forecast.food_item_id for forecast, _ in rows})
        return result
    except Exception:  # noqa: BLE001 - auditing must never block plan generation
        logger.exception("model_run: accuracy unavailable restaurant=%s", restaurant.id)
        return None


def record_run(
    db: Session,
    restaurant: Restaurant,
    *,
    model_type: str,
    target_date: date,
    as_of: date,
    history: pd.DataFrame,
    items_forecast: int,
    items_collecting: int,
) -> ModelRun:
    """Add (not commit) a ``model_runs`` row describing this generation."""
    train_start = train_end = None
    if not history.empty:
        train_start = history["sale_date"].min()
        train_end = history["sale_date"].max()

    accuracy = _recent_accuracy(db, restaurant, as_of)

    run = ModelRun(
        restaurant_id=restaurant.id,
        model_type=model_type,
        trained_at=datetime.now(timezone.utc),
        train_start=train_start,
        train_end=train_end,
        mae=_decimal(accuracy["mae"], 3) if accuracy else None,
        wape=_decimal(accuracy["wape"], 4) if accuracy else None,
        bias=_decimal(accuracy["bias"], 3) if accuracy else None,
        params={
            "target_date": target_date.isoformat(),
            "service_level": settings.forecast_service_level,
            "history_days": settings.forecast_history_days,
            "min_observations": settings.forecast_min_observations,
            "items_forecast": items_forecast,
            "items_collecting_data": items_collecting,
            "accuracy_window_days": ACCURACY_WINDOW_DAYS,
            "accuracy_items_evaluated": accuracy["evaluated_items"] if accuracy else 0,
        },
        artifact_path=None,
    )
    db.add(run)
    return run
