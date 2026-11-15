"""Feature engineering for demand forecasting.

Every lag/rolling feature is computed from data strictly *before* the target day,
so a prediction for day ``t`` never sees day ``t``.

The v0 pipeline assumes one row per item per day (the canonical import shape).
Missing days are tolerated, but lag features then refer to the previous *observed*
day rather than the previous calendar day; normalise the series before serious
backtesting.
"""

from __future__ import annotations

import pandas as pd

LAG_DAYS = (1, 7, 14, 28)
ROLLING_WINDOWS = (7, 28)

FEATURE_COLUMNS = [
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_7",
    "rolling_std_7",
    "rolling_mean_28",
    "rolling_std_28",
    "dow",
    "is_weekend",
    "month",
    "promotion",
    "stockout",
    "days_since_start",
]


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Sort by item/date and normalise dtypes."""
    if frame.empty:
        return frame.assign(ds=pd.Series(dtype="datetime64[ns]"))

    out = frame.copy()
    out["ds"] = pd.to_datetime(out["sale_date"])
    out = out.sort_values(["food_item_id", "ds"]).reset_index(drop=True)
    out["quantity_sold"] = out["quantity_sold"].astype(float)
    for boolean_col in ("promotion", "stockout"):
        if boolean_col not in out:
            out[boolean_col] = False
        out[boolean_col] = out[boolean_col].fillna(False).astype(float)
    return out


def add_item_features(prepared: pd.DataFrame) -> pd.DataFrame:
    """Add calendar, lag and rolling features per dish."""
    if prepared.empty:
        return prepared

    out = prepared.copy()
    grouped = out.groupby("food_item_id", group_keys=False)

    for lag in LAG_DAYS:
        out[f"lag_{lag}"] = grouped["quantity_sold"].shift(lag)
    for window in ROLLING_WINDOWS:
        # shift(1) first: the window must end before the target day.
        out[f"rolling_mean_{window}"] = grouped["quantity_sold"].transform(
            lambda s: s.shift(1).rolling(window, min_periods=3).mean()
        )
        out[f"rolling_std_{window}"] = grouped["quantity_sold"].transform(
            lambda s: s.shift(1).rolling(window, min_periods=3).std()
        )

    out["dow"] = out["ds"].dt.weekday
    out["is_weekend"] = (out["dow"] >= 5).astype(int)
    out["month"] = out["ds"].dt.month
    start = out.groupby("food_item_id")["ds"].transform("min")
    out["days_since_start"] = (out["ds"] - start).dt.days
    return out


def build_supervised(prepared: pd.DataFrame) -> pd.DataFrame:
    """Rows complete enough to train on (target plus all features present)."""
    if prepared.empty:
        return prepared
    featured = add_item_features(prepared)
    return featured.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)


def build_inference_row(prepared: pd.DataFrame, target_date) -> dict | None:
    """Feature row describing ``target_date`` from one dish's history."""
    if prepared.empty:
        return None

    history = prepared.sort_values("ds")
    target = pd.Timestamp(target_date)
    by_date = dict(zip(history["ds"], history["quantity_sold"]))
    before = history[history["ds"] < target]

    row: dict[str, float] = {f"lag_{lag}": by_date.get(target - pd.Timedelta(days=lag)) for lag in LAG_DAYS}
    if row["lag_1"] is None and not before.empty:
        row["lag_1"] = float(before["quantity_sold"].iloc[-1])
    if row["lag_1"] is None:
        return None

    for window in ROLLING_WINDOWS:
        tail = before.tail(window)
        row[f"rolling_mean_{window}"] = float(tail["quantity_sold"].mean()) if len(tail) else None
        row[f"rolling_std_{window}"] = float(tail["quantity_sold"].std()) if len(tail) > 1 else 0.0

    if row["rolling_mean_7"] is None:
        return None

    # Gaps in the history leave some lags undefined; use the recent level as a
    # conservative fill so the model sees a numeric feature vector.
    for lag in LAG_DAYS:
        if row[f"lag_{lag}"] is None:
            row[f"lag_{lag}"] = row["rolling_mean_7"]

    row.update(
        {
            "dow": float(target.weekday()),
            "is_weekend": float(target.weekday() >= 5),
            "month": float(target.month),
            "promotion": 0.0,
            "stockout": 0.0,
            "days_since_start": float((target - history["ds"].min()).days),
        }
    )
    return row
