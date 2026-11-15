"""Backtesting utilities: metrics and rolling-origin evaluation.

Never evaluate with a random train/test split — that leaks the future into the
past. ``walk_forward`` retrains on data before each test day and predicts it,
mirroring how the product actually runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml.baseline import weekday_average_forecast


@dataclass(frozen=True)
class ForecastError:
    target_date: date
    actual: float
    predicted: float
    lower: float | None = None
    upper: float | None = None

    @property
    def error(self) -> float:
        return self.predicted - self.actual


def metrics(errors: list[ForecastError]) -> dict[str, float | int]:
    """MAE, WAPE, bias and band coverage for a list of observations."""
    if not errors:
        return {"n": 0, "mae": 0.0, "wape": 0.0, "bias": 0.0, "within_band_pct": 0.0}

    actual = np.array([e.actual for e in errors], dtype=float)
    predicted = np.array([e.predicted for e in errors], dtype=float)
    abs_error = np.abs(predicted - actual)

    banded = [e for e in errors if e.lower is not None and e.upper is not None]
    within = sum(1 for e in banded if e.lower <= e.actual <= e.upper)
    total_actual = float(actual.sum())

    return {
        "n": len(errors),
        "mae": round(float(abs_error.mean()), 3),
        "wape": round(float(abs_error.sum() / total_actual), 4) if total_actual > 0 else 0.0,
        "bias": round(float((predicted - actual).mean()), 3),
        "within_band_pct": round(100.0 * within / len(banded), 2) if banded else 0.0,
    }


def walk_forward(
    history: pd.DataFrame,
    test_start: date,
    test_end: date,
    service_level: float = 0.85,
) -> list[ForecastError]:
    """Evaluate the weekday-average baseline over ``[test_start, test_end]``."""
    if history.empty:
        return []

    frame = history.copy()
    frame["ds"] = pd.to_datetime(frame["sale_date"]).dt.date
    frame = frame.sort_values("ds")

    errors: list[ForecastError] = []
    current = test_start
    while current <= test_end:
        train = frame[frame["ds"] < current]
        actual_rows = frame[frame["ds"] == current]
        if not actual_rows.empty:
            prediction = weekday_average_forecast(train, current, service_level=service_level)
            if prediction is not None:
                errors.append(
                    ForecastError(
                        target_date=current,
                        actual=float(actual_rows["quantity_sold"].sum()),
                        predicted=prediction.predicted,
                        lower=prediction.lower,
                        upper=prediction.upper,
                    )
                )
        current += timedelta(days=1)
    return errors
