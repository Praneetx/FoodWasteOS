from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.ml import evaluate, features
from app.ml.baseline import recommend_preparation, weekday_average_forecast
from app.ml.rf import RandomForestForecaster


def make_history(days: int = 40, base: float = 100.0) -> pd.DataFrame:
    rows = []
    start = date(2026, 1, 5)
    for offset in range(days):
        day = start + timedelta(days=offset)
        rows.append(
            {
                "sale_date": day,
                "quantity_sold": base + (20 if day.weekday() >= 5 else 0) + (offset % 3),
            }
        )
    return pd.DataFrame(rows)


def test_weekday_average_forecast_band_and_confidence():
    target = date(2026, 1, 5) + timedelta(days=45)
    prediction = weekday_average_forecast(make_history(), target, service_level=0.85)

    assert prediction is not None
    assert prediction.lower <= prediction.predicted <= prediction.upper
    assert prediction.confidence in {"low", "medium", "high"}
    assert prediction.sample_size == 40
    assert prediction.last_same_weekday_sold is not None


def test_recommendation_rounds_to_batch_and_caps_buffer():
    assert recommend_preparation(85, 98, 5) == 100.0
    assert recommend_preparation(85, 200, 5) == 110.0  # capped at 1.25x then rounded up
    assert recommend_preparation(0, 10, 5) == 0.0


def test_features_do_not_leak_current_day():
    frame = pd.DataFrame(
        {
            "food_item_id": ["a"] * 10,
            "sale_date": pd.date_range("2026-01-01", periods=10, freq="D"),
            "quantity_sold": list(range(10, 20)),
        }
    )
    prepared = features.prepare(frame)
    featured = features.add_item_features(prepared)

    assert featured.loc[5, "lag_1"] == 14  # value of day 4, not day 5
    assert pd.isna(featured.loc[0, "lag_1"])
    assert featured.loc[7, "rolling_mean_7"] == sum(range(10, 17)) / 7


def test_walk_forward_metrics():
    history = make_history(days=40)
    errors = evaluate.walk_forward(history, date(2026, 2, 3), date(2026, 2, 13))
    assert errors
    result = evaluate.metrics(errors)
    assert result["n"] == len(errors)
    assert result["mae"] >= 0
    assert 0 <= result["within_band_pct"] <= 100


def test_random_forest_fits_and_predicts():
    rows = []
    for item in ("a", "b"):
        history = make_history(days=45, base=100 if item == "a" else 60)
        history = history.assign(food_item_id=item, promotion=False, stockout=False)
        rows.append(history)
    frame = pd.concat(rows, ignore_index=True)

    forecaster = RandomForestForecaster(n_estimators=25).fit(frame)
    predictions = forecaster.predict(frame, date(2026, 2, 20))

    assert len(predictions) == 2
    assert all(value >= 0 for value in predictions.values())
