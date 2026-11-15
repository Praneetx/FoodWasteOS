"""Idempotency, limits and metric correctness for the data the pilot will depend on."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import DailySale, FoodItem, Forecast, Restaurant
from tests.test_api import create_item, sales_csv, upload_csv

TODAY = date.today()


def waste_payload(item_id: str, quantity: float, reason: str, day: date = TODAY) -> dict:
    return {
        "food_item_id": item_id,
        "waste_date": day.isoformat(),
        "quantity_wasted": quantity,
        "reason": reason,
    }


def forecast_count(db) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Forecast))


# --------------------------------------------------------------------------- waste


def test_waste_same_reason_updates_instead_of_duplicating(client):
    item = create_item(client)
    assert client.post("/api/v1/waste", json=waste_payload(item["id"], 3, "unsold")).status_code == 201
    assert client.post("/api/v1/waste", json=waste_payload(item["id"], 5, "unsold")).status_code == 201

    rows = client.get("/api/v1/waste").json()
    assert len(rows) == 1
    assert rows[0]["quantity_wasted"] == 5


def test_waste_with_different_reasons_is_recorded_in_parts(client):
    item = create_item(client)
    client.post("/api/v1/waste", json=waste_payload(item["id"], 3, "unsold"))
    client.post("/api/v1/waste", json=waste_payload(item["id"], 2, "spoilage"))

    rows = client.get("/api/v1/waste").json()
    assert {row["reason"]: row["quantity_wasted"] for row in rows} == {"unsold": 3, "spoilage": 2}
    assert client.get("/api/v1/analytics/summary?days=7").json()["waste_quantity"] == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"quantity_wasted": 0, "reason": "unsold"},
        {"quantity_wasted": -2, "reason": "unsold"},
        {"quantity_wasted": 3, "reason": "dropped on floor"},
    ],
)
def test_waste_rejects_invalid_values(client, payload):
    item = create_item(client)
    body = {"food_item_id": item["id"], "waste_date": TODAY.isoformat(), **payload}
    assert client.post("/api/v1/waste", json=body).status_code == 422


# --------------------------------------------------------------------------- CSV import


def test_csv_duplicate_rows_in_one_file_last_wins(client):
    day = (TODAY - timedelta(days=1)).isoformat()
    csv = (
        "date,food_item,quantity_sold\n"
        f"{day},Veg Pulao,10\n"
        f"{day},Veg Pulao,25\n"
    )
    report = upload_csv(client, csv).json()
    assert report["imported"] == 1

    rows = client.get("/api/v1/sales").json()
    assert len(rows) == 1
    assert rows[0]["quantity_sold"] == 25


def test_csv_reupload_is_idempotent(client):
    content = sales_csv("Chicken Biryani", days=10)
    upload_csv(client, content)
    upload_csv(client, content)
    assert len(client.get("/api/v1/sales?start=2000-01-01").json()) == 10


def test_csv_over_the_size_limit_is_413(client, monkeypatch):
    monkeypatch.setattr(settings, "max_csv_bytes", 100)
    response = upload_csv(client, sales_csv("Chicken Biryani", days=30))
    assert response.status_code == 413


def test_csv_missing_required_columns_is_400(client):
    response = upload_csv(client, "date,quantity_sold\n2026-01-01,5\n")
    assert response.status_code == 400
    assert "food_item" in response.json()["detail"]


# --------------------------------------------------------------------------- accuracy


def test_accuracy_with_no_scored_forecasts_returns_zeros(client):
    create_item(client)
    body = client.get("/api/v1/forecasts/accuracy?days=28").json()
    assert body["evaluated_items"] == 0
    assert body["mae"] == 0 and body["wape"] == 0 and body["bias"] == 0


def test_accuracy_matches_a_hand_computed_fixture(client, db_session):
    item = create_item(client)
    restaurant = db_session.scalar(select(Restaurant))
    item_id = uuid.UUID(item["id"])
    day_one, day_two = TODAY - timedelta(days=3), TODAY - timedelta(days=2)

    # predicted 100 (band 90-110) in both cases; actuals 90 and 120.
    for day, actual in ((day_one, 90), (day_two, 120)):
        db_session.add(
            DailySale(
                restaurant_id=restaurant.id,
                food_item_id=item_id,
                sale_date=day,
                quantity_sold=actual,
            )
        )
        db_session.add(
            Forecast(
                restaurant_id=restaurant.id,
                food_item_id=item_id,
                target_date=day,
                predicted_demand=100,
                lower_bound=90,
                upper_bound=110,
                recommended_preparation=110,
                confidence="high",
                model_version="weekday_average_v1",
                method="weekday_average_v1",
                sample_size=20,
            )
        )
    db_session.commit()

    body = client.get("/api/v1/forecasts/accuracy?days=28").json()
    assert body["evaluated_items"] == 1
    assert body["mae"] == pytest.approx(15.0)  # (|100-90| + |100-120|) / 2
    assert body["wape"] == pytest.approx(30 / 210, abs=1e-4)
    assert body["bias"] == pytest.approx(-5.0)  # ((100-90) + (100-120)) / 2
    assert body["within_band_pct"] == pytest.approx(50.0)  # 90 inside, 120 outside


# --------------------------------------------------------------------------- generation


def test_force_false_keeps_the_plan_and_force_true_recomputes_it(client):
    create_item(client)
    upload_csv(client, sales_csv("Chicken Biryani"))
    item_id = client.get("/api/v1/food-items").json()[0]["id"]

    first = client.post("/api/v1/forecasts/generate", json={"force": False}).json()
    baseline = first["items"][0]["predicted_demand"]

    # Same weekday as the plan's target date, one week earlier: a large spike.
    target = date.fromisoformat(first["target_date"])
    client.post(
        "/api/v1/sales",
        json={
            "food_item_id": item_id,
            "sale_date": (target - timedelta(days=7)).isoformat(),
            "quantity_sold": 900,
        },
    )

    cached = client.post("/api/v1/forecasts/generate", json={"force": False}).json()
    assert cached["items"][0]["predicted_demand"] == baseline
    assert cached["generated_at"] == first["generated_at"]

    forced = client.post("/api/v1/forecasts/generate", json={"force": True}).json()
    assert forced["items"][0]["predicted_demand"] > baseline
    assert forced["generated_at"] > first["generated_at"]


def test_force_removes_deactivated_dishes_from_the_stored_plan(client, db_session):
    create_item(client, "Chicken Biryani")
    create_item(client, "Paneer Tikka")
    upload_csv(client, sales_csv("Chicken Biryani"))
    upload_csv(client, sales_csv("Paneer Tikka"))

    client.post("/api/v1/forecasts/generate", json={"force": True})
    assert forecast_count(db_session) == 2

    tikka = next(
        row for row in client.get("/api/v1/food-items").json() if row["name"] == "Paneer Tikka"
    )
    assert client.patch(f"/api/v1/food-items/{tikka['id']}", json={"is_active": False}).status_code == 200

    plan = client.post("/api/v1/forecasts/generate", json={"force": True}).json()
    assert [row["food_item"] for row in plan["items"]] == ["Chicken Biryani"]
    assert forecast_count(db_session) == 1


def test_force_clears_the_plan_when_every_dish_is_deactivated(client, db_session):
    create_item(client)
    upload_csv(client, sales_csv("Chicken Biryani"))
    client.post("/api/v1/forecasts/generate", json={"force": True})
    assert forecast_count(db_session) == 1

    item = db_session.scalar(select(FoodItem))
    client.patch(f"/api/v1/food-items/{item.id}", json={"is_active": False})

    plan = client.post("/api/v1/forecasts/generate", json={"force": True}).json()
    assert plan["items"] == []
    assert forecast_count(db_session) == 0
