"""Forecast-vs-actual evaluation shared by analytics and the model-run audit trail.

Kept free of imports from ``forecasting`` so both can depend on it.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db.models import DailySale, Forecast
from app.ml.evaluate import ForecastError, metrics


def forecast_actual_rows(
    db: Session, restaurant_id: uuid.UUID, start: date, end: date
) -> list[tuple[Forecast, int]]:
    """Materialised forecasts with a recorded sale on their target date, ``start <= d < end``."""
    return list(
        db.execute(
            select(Forecast, DailySale.quantity_sold)
            .join(
                DailySale,
                and_(
                    DailySale.food_item_id == Forecast.food_item_id,
                    DailySale.sale_date == Forecast.target_date,
                ),
            )
            .where(
                Forecast.restaurant_id == restaurant_id,
                Forecast.target_date >= start,
                Forecast.target_date < end,
            )
        ).all()
    )


def evaluate_rows(rows: list[tuple[Forecast, int]]) -> dict[str, float | int]:
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
    return metrics(errors)
