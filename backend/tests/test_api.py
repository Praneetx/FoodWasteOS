from __future__ import annotations

from datetime import date, timedelta

import pytest


def create_item(client, name: str = "Chicken Biryani") -> dict:
    response = client.post(
        "/api/v1/food-items",
        json={"name": name, "preparation_unit": "plate", "batch_size": 5, "unit_cost": 120},
    )
    assert response.status_code == 201, response.text
    return response.json()


def sales_csv(item: str, days: int = 40) -> str:
    lines = ["date,food_item,quantity_sold,prepared_quantity,promotion,stockout,notes"]
    for offset in range(days, 0, -1):
        day = date.today() - timedelta(days=offset)
        sold = 80 + (10 if day.weekday() >= 5 else 0) + (offset % 4)
        lines.append(f"{day.isoformat()},{item},{sold},{sold + 10},false,false,")
    return "\n".join(lines)


def upload_csv(client, content: str):
    return client.post(
        "/api/v1/sales/import",
        files={"file": ("sales.csv", content.encode("utf-8"), "text/csv")},
    )


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_me_returns_demo_tenant(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    body = response.json()
    assert body["restaurant"]["name"] == "Spice Route Kitchen"
    assert body["user"]["role"] == "owner"


def test_sale_upsert_is_idempotent(client):
    item = create_item(client)
    payload = {
        "food_item_id": item["id"],
        "sale_date": date.today().isoformat(),
        "quantity_sold": 90,
        "prepared_quantity": 110,
    }
    assert client.post("/api/v1/sales", json=payload).status_code == 200

    payload["quantity_sold"] = 95
    assert client.post("/api/v1/sales", json=payload).status_code == 200

    rows = client.get("/api/v1/sales").json()
    assert len(rows) == 1
    assert rows[0]["quantity_sold"] == 95


def test_import_reports_bad_rows_without_failing(client):
    csv = (
        "date,food_item,quantity_sold\n"
        f"{(date.today() - timedelta(days=2)).isoformat()},Veg Pulao,40\n"
        "not-a-date,Veg Pulao,30\n"
    )
    response = upload_csv(client, csv)
    assert response.status_code == 200
    report = response.json()
    assert report["imported"] == 1
    assert report["skipped"] == 1
    assert "Veg Pulao" in report["items_created"]


def test_plan_generates_recommendations(client):
    create_item(client)
    assert upload_csv(client, sales_csv("Chicken Biryani")).status_code == 200

    response = client.get("/api/v1/forecasts/plan")
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["target_date"] > date.today().isoformat()
    item = plan["items"][0]
    assert item["status"] == "ok"
    assert item["predicted_demand"] > 0
    assert item["recommended_preparation"] >= item["predicted_demand"]
    assert item["confidence"] in {"low", "medium", "high"}
    assert plan["insights"]

    # Serving the stored plan must be stable and must not duplicate rows.
    again = client.get("/api/v1/forecasts/plan").json()
    assert again["items"][0]["predicted_demand"] == item["predicted_demand"]


def test_plan_without_history_marks_collecting(client):
    create_item(client, "New Dish")
    plan = client.get("/api/v1/forecasts/plan").json()
    assert plan["items"][0]["status"] == "collecting_data"
    assert plan["items"][0]["predicted_demand"] is None


def test_waste_and_analytics(client):
    item = create_item(client)
    response = client.post(
        "/api/v1/waste",
        json={
            "food_item_id": item["id"],
            "waste_date": date.today().isoformat(),
            "quantity_wasted": 4,
            "reason": "unsold",
        },
    )
    assert response.status_code == 201, response.text

    summary = client.get("/api/v1/analytics/summary?days=7").json()
    assert summary["waste_quantity"] == 4
    assert summary["estimated_waste_cost"] == pytest.approx(480.0)
    assert summary["top_wasted"][0]["food_item"] == "Chicken Biryani"


def test_dashboard_includes_tomorrow(client):
    create_item(client)
    upload_csv(client, sales_csv("Chicken Biryani"))
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["series"]) == 14
    assert body["tomorrow"] is not None
    assert body["tomorrow"]["predicted_total"] > 0
