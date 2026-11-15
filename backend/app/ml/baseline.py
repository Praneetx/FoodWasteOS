"""The v0 forecaster: recency-weighted historical weekday average.

This is the reference model every challenger must beat. It is deliberately
simple: no training, fully explainable, and immediately useful with 2–4 weeks
of data.

Prediction for day-of-week ``d`` is the exponentially weighted mean of the last
``max_weeks`` observations of that weekday. The uncertainty band comes from the
measured dispersion of those observations, not from a fixed percentage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd

METHOD = "weekday_average_v1"
DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class Prediction:
    predicted: float
    lower: float
    upper: float
    confidence: str
    sample_size: int
    method: str
    last_same_weekday_sold: float | None


def _z(service_level: float) -> float:
    return NormalDist().inv_cdf(min(max(service_level, 0.5), 0.99))


def _confidence(sample_size: int, spread: float, predicted: float, censored: bool) -> str:
    if censored or predicted <= 0:
        return "low"
    cv = spread / predicted
    if sample_size >= 14 and cv <= 0.12:
        return "high"
    if sample_size >= 14 and cv <= 0.25:
        return "medium"
    return "low"


def weekday_average_forecast(
    history: pd.DataFrame,
    target_date: date,
    service_level: float = 0.85,
    min_observations: int = 7,
    max_weeks: int = 8,
) -> Prediction | None:
    """Forecast one dish for ``target_date``.

    ``history`` needs ``sale_date`` and ``quantity_sold`` columns for a single
    item. Returns ``None`` when there is not enough history to say anything.
    """
    if history is None or len(history) < min_observations:
        return None

    frame = history.copy()
    frame["ds"] = pd.to_datetime(frame["sale_date"])
    frame = frame.sort_values("ds")
    frame["quantity_sold"] = frame["quantity_sold"].astype(float)

    target_dow = pd.Timestamp(target_date).weekday()
    same_dow = frame[frame["ds"].dt.weekday == target_dow].tail(max_weeks)

    if same_dow.empty:
        recent = frame.tail(14)
        predicted = float(recent["quantity_sold"].mean())
        spread = float(recent["quantity_sold"].std() or 0.0)
        if pd.isna(spread):
            spread = 0.0
        last_same = None
    else:
        values = same_dow["quantity_sold"].to_numpy()
        weights = np.power(0.9, np.arange(len(values))[::-1])
        predicted = float(np.average(values, weights=weights))
        spread = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        last_same = float(values[-1])

    if spread == 0.0:
        # Pool dispersion across weekdays so a single observation still gets a band.
        within_dow = frame.groupby(frame["ds"].dt.weekday)["quantity_sold"].transform("mean")
        spread = float(np.sqrt(((frame["quantity_sold"] - within_dow) ** 2).mean()))

    z = _z(service_level)
    lower = max(0.0, predicted - z * spread)
    upper = predicted + z * spread

    recent = frame.tail(14)
    censored = bool("stockout" in frame and recent["stockout"].fillna(False).any())

    return Prediction(
        predicted=round(predicted, 2),
        lower=round(lower, 2),
        upper=round(upper, 2),
        confidence=_confidence(len(frame), spread, predicted, censored),
        sample_size=len(frame),
        method=METHOD,
        last_same_weekday_sold=last_same,
    )


def recommend_preparation(predicted: float, upper: float, batch_size: float) -> float:
    """Turn a demand band into a kitchen-executable quantity.

    Target the upper band, clamp the safety buffer to 0–25% of the point
    forecast, then round up to the dish's preparation batch (e.g. 5 portions).
    """
    batch = float(batch_size) if batch_size and batch_size > 0 else 1.0
    if predicted <= 0:
        return 0.0
    target = min(max(upper, predicted), predicted * 1.25)
    return float(math.ceil(target / batch) * batch)
