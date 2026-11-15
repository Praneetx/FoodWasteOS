from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import Forecast, Restaurant
from app.services import forecasting
from tests.test_api import create_item, sales_csv, upload_csv

URL = "/api/v1/cron/generate"
SECRET = "test-cron-secret"


@pytest.fixture()
def cron_secret(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", SECRET)
    return SECRET



def seed_tenant(client) -> None:
    create_item(client)
    assert upload_csv(client, sales_csv("Chicken Biryani")).status_code == 200


def forecast_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Forecast))


def test_cron_is_disabled_without_configured_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", None)
    response = client.post(URL, headers={"X-Cron-Secret": "anything"})
    assert response.status_code == 503


def test_cron_requires_secret_header(client, cron_secret):
    assert client.post(URL).status_code == 401


def test_cron_rejects_wrong_secret(client, cron_secret):
    response = client.post(URL, headers={"X-Cron-Secret": "wrong"})
    assert response.status_code == 403


def test_cron_does_not_accept_a_user_token(client, cron_secret):
    response = client.post(URL, headers={"Authorization": "Bearer some-user-jwt"})
    assert response.status_code == 401


def test_cron_generates_tomorrows_plan(client, cron_secret, db_session):
    seed_tenant(client)
    assert forecast_count(db_session) == 0

    response = client.post(URL, headers={"X-Cron-Secret": cron_secret})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["restaurants"] == 1
    assert report["plans_generated"] == 1
    assert report["failed"] == []
    assert forecast_count(db_session) == 1

    plan = client.get("/api/v1/forecasts/plan").json()
    assert plan["items"][0]["status"] == "ok"


def test_cron_is_idempotent_and_can_cover_several_days(client, cron_secret, db_session):
    seed_tenant(client)
    headers = {"X-Cron-Secret": cron_secret}

    assert client.post(URL, headers=headers, json={"days_ahead": 3}).status_code == 200
    assert forecast_count(db_session) == 3

    again = client.post(URL, headers=headers, json={"days_ahead": 3})
    assert again.json()["plans_generated"] == 3
    assert forecast_count(db_session) == 3


def test_cron_without_force_keeps_existing_plan(client, cron_secret):
    seed_tenant(client)
    headers = {"X-Cron-Secret": cron_secret}
    client.post(URL, headers=headers)
    before = client.get("/api/v1/forecasts/plan").json()["generated_at"]

    client.post(URL, headers=headers, json={"force": False})
    after = client.get("/api/v1/forecasts/plan").json()["generated_at"]
    assert after == before


def test_cron_rejects_out_of_range_days(client, cron_secret):
    response = client.post(URL, headers={"X-Cron-Secret": cron_secret}, json={"days_ahead": 30})
    assert response.status_code == 422


def test_cron_isolates_a_failing_restaurant(client, cron_secret, db_session, monkeypatch):
    seed_tenant(client)
    broken = Restaurant(name="Broken Kitchen")
    db_session.add(broken)
    db_session.commit()
    broken_id = broken.id

    real_generate = forecasting.generate_plan

    def flaky(db, restaurant, target_date, force=False):
        if restaurant.id == broken_id:
            raise RuntimeError("boom")
        return real_generate(db, restaurant, target_date, force=force)

    monkeypatch.setattr(forecasting, "generate_plan", flaky)

    response = client.post(URL, headers={"X-Cron-Secret": cron_secret})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["restaurants"] == 2
    assert report["plans_generated"] == 1
    assert [row["restaurant_id"] for row in report["failed"]] == [str(broken_id)]
    assert forecast_count(db_session) == 1
