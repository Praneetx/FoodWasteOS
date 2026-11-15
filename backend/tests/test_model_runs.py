from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.db.models import ModelRun, Restaurant
from tests.test_api import create_item, sales_csv, upload_csv

GENERATE = "/api/v1/forecasts/generate"


def runs(db) -> list[ModelRun]:
    db.expire_all()
    return list(db.scalars(select(ModelRun).order_by(ModelRun.trained_at, ModelRun.id)))


def seed_tenant(client) -> None:
    create_item(client)
    assert upload_csv(client, sales_csv("Chicken Biryani")).status_code == 200


def test_generation_records_a_model_run(client, db_session):
    seed_tenant(client)
    assert runs(db_session) == []

    response = client.post(GENERATE, json={"force": True})
    assert response.status_code == 200, response.text

    [run] = runs(db_session)
    restaurant = db_session.scalar(select(Restaurant))
    assert run.restaurant_id == restaurant.id
    assert run.model_type == "weekday_average_v1"
    assert run.train_end == date.today() - timedelta(days=1)
    assert run.train_start == date.today() - timedelta(days=40)
    assert run.artifact_path is None
    assert run.params["items_forecast"] == 1
    assert run.params["items_collecting_data"] == 0
    assert run.params["target_date"] == response.json()["target_date"]


def test_two_generations_record_two_runs(client, db_session):
    seed_tenant(client)
    client.post(GENERATE, json={"force": True})
    client.post(GENERATE, json={"force": True})
    assert len(runs(db_session)) == 2


def test_serving_a_stored_plan_does_not_record_a_run(client, db_session):
    seed_tenant(client)
    client.post(GENERATE, json={"force": True})
    assert len(runs(db_session)) == 1

    client.get("/api/v1/forecasts/plan")
    client.post(GENERATE, json={"force": False})
    assert len(runs(db_session)) == 1


def test_no_run_when_nothing_could_be_forecast(client, db_session):
    create_item(client, "New Dish")
    response = client.post(GENERATE, json={"force": True})
    assert response.status_code == 200
    assert runs(db_session) == []


def test_metrics_are_null_until_forecasts_can_be_scored(client, db_session):
    seed_tenant(client)
    client.post(GENERATE, json={"force": True})

    [run] = runs(db_session)
    assert run.mae is None and run.wape is None and run.bias is None
    assert run.params["accuracy_items_evaluated"] == 0


def test_metrics_use_past_forecasts_that_have_actuals(client, db_session):
    seed_tenant(client)
    past = (date.today() - timedelta(days=3)).isoformat()
    assert client.post(GENERATE, json={"target_date": past, "force": True}).status_code == 200
    assert client.post(GENERATE, json={"force": True}).status_code == 200

    latest = runs(db_session)[-1]
    assert latest.mae is not None
    assert latest.wape is not None
    assert latest.bias is not None
    assert latest.params["accuracy_items_evaluated"] == 1
