from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    food_item_id: uuid.UUID
    food_item: str
    preparation_unit: str
    predicted_demand: float | None
    recommended_preparation: float | None
    lower_bound: float | None
    upper_bound: float | None
    confidence: str | None
    method: str | None
    sample_size: int
    last_same_weekday_sold: float | None
    status: Literal["ok", "collecting_data"] = "ok"
    observations: int | None = None


class PlanOut(BaseModel):
    target_date: date
    model: str
    generated_at: datetime
    stale: bool
    insights: list[str]
    items: list[PlanItem]


class GenerateRequest(BaseModel):
    target_date: date | None = None
    force: bool = False


class AccuracyOut(BaseModel):
    window_days: int
    evaluated_items: int
    mae: float
    wape: float
    bias: float
    within_band_pct: float
    stockout_days: int


class DashboardSeriesPoint(BaseModel):
    date: date
    sold: int
    wasted: float


class TomorrowSummary(BaseModel):
    target_date: date
    predicted_total: float
    recommended_total: float
    vs_usual_pct: float | None


class DashboardOut(BaseModel):
    date: date
    sales_quantity: int
    waste_quantity: float
    waste_rate: float
    estimated_waste_cost: float | None
    currency: str
    series: list[DashboardSeriesPoint]
    tomorrow: TomorrowSummary | None


class TopWasted(BaseModel):
    food_item: str
    quantity: float
    cost: float | None


class WeeklyTrendPoint(BaseModel):
    week_start: date
    sold: int
    wasted: float


class AnalyticsSummaryOut(BaseModel):
    start: date
    end: date
    sales_quantity: int
    waste_quantity: float
    waste_rate: float
    estimated_waste_cost: float | None
    currency: str
    top_wasted: list[TopWasted]
    weekly_trend: list[WeeklyTrendPoint]
