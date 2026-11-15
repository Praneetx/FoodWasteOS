"""Random Forest challenger (experimental, not enabled by default).

Only promote this model for a tenant when it beats the weekday-average baseline
on rolling-origin backtests (see ``app.ml.evaluate``). It is kept behind an
explicit flag so a plan can always name the model that produced it.
"""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from app.ml import features

MODEL_VERSION = "rf_v1"


class RandomForestForecaster:
    model_version = MODEL_VERSION

    def __init__(self, n_estimators: int = 300, min_samples_leaf: int = 2, random_state: int = 42):
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
            n_jobs=-1,
        )
        self.feature_columns: list[str] = []

    def _design_matrix(self, rows: pd.DataFrame) -> pd.DataFrame:
        encoded = rows.copy()
        encoded["item_key"] = encoded["food_item_id"].astype(str)
        matrix = pd.get_dummies(encoded[features.FEATURE_COLUMNS + ["item_key"]], columns=["item_key"])
        if self.feature_columns:
            matrix = matrix.reindex(columns=self.feature_columns, fill_value=0)
        return matrix

    def fit(self, frame: pd.DataFrame) -> "RandomForestForecaster":
        prepared = features.prepare(frame)
        supervised = features.build_supervised(prepared)
        if len(supervised) < 20:
            raise ValueError("not enough history to fit a Random Forest (need >= 20 complete rows)")

        matrix = self._design_matrix(supervised)
        self.feature_columns = list(matrix.columns)
        self.model.fit(matrix, supervised["quantity_sold"])
        return self

    def predict(self, frame: pd.DataFrame, target_date) -> dict[str, float]:
        if not self.feature_columns:
            raise RuntimeError("call fit() before predict()")

        prepared = features.prepare(frame)
        rows = []
        for item_id, item_history in prepared.groupby("food_item_id"):
            row = features.build_inference_row(item_history, target_date)
            if row is None:
                continue
            row["food_item_id"] = item_id
            rows.append(row)

        if not rows:
            return {}

        matrix = self._design_matrix(pd.DataFrame(rows))
        predictions = self.model.predict(matrix)
        return {
            str(row["food_item_id"]): max(0.0, round(float(value), 2))
            for row, value in zip(rows, predictions)
        }
