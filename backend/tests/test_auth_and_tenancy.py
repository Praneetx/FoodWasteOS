"""401/403 paths, role enforcement and tenant isolation.

These run in ``supabase`` auth mode with real HS256 tokens so the genuine
verification code is exercised (no mocked ``decode_token``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest

from app.core.config import settings
from app.db.models import Restaurant, User
from tests.test_api import sales_csv

SECRET = "unit-test-jwt-secret-that-is-long-enough"
TODAY = date.today().isoformat()


def token_for(subject, *, audience="authenticated", expires_in=3600, secret=SECRET) -> str:
    claims = {
        "sub": str(subject),
        "aud": audience,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def as_user(user: User) -> dict:
    return bearer(token_for(user.id))


def add_restaurant(db, name: str) -> Restaurant:
    restaurant = Restaurant(name=name)
    db.add(restaurant)
    db.commit()
    return restaurant


def add_user(db, restaurant: Restaurant, role: str) -> User:
    user = User(
        restaurant_id=restaurant.id,
        name=f"{role} of {restaurant.name}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role=role,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def tenants(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)

    kitchen_a = add_restaurant(db_session, "Kitchen A")
    kitchen_b = add_restaurant(db_session, "Kitchen B")
    return SimpleNamespace(
        a_owner=add_user(db_session, kitchen_a, "owner"),
        a_manager=add_user(db_session, kitchen_a, "manager"),
        a_staff=add_user(db_session, kitchen_a, "staff"),
        b_owner=add_user(db_session, kitchen_b, "owner"),
    )


def create_dish(client, user: User, name: str = "Chicken Biryani") -> dict:
    response = client.post(
        "/api/v1/food-items",
        headers=as_user(user),
        json={"name": name, "preparation_unit": "plate", "batch_size": 5, "unit_cost": 120},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- 401 / 403


def test_missing_token_is_401(client, tenants):
    assert client.get("/api/v1/me").status_code == 401


def test_garbage_token_is_401(client, tenants):
    assert client.get("/api/v1/me", headers=bearer("not-a-jwt")).status_code == 401


def test_expired_token_is_401(client, tenants):
    token = token_for(tenants.a_owner.id, expires_in=-60)
    assert client.get("/api/v1/me", headers=bearer(token)).status_code == 401


def test_wrong_audience_is_401(client, tenants):
    token = token_for(tenants.a_owner.id, audience="someone-else")
    assert client.get("/api/v1/me", headers=bearer(token)).status_code == 401


def test_token_signed_with_another_secret_is_401(client, tenants):
    token = token_for(tenants.a_owner.id, secret="a-different-secret-of-sufficient-length")
    assert client.get("/api/v1/me", headers=bearer(token)).status_code == 401


def test_non_uuid_subject_is_401(client, tenants):
    assert client.get("/api/v1/me", headers=bearer(token_for("not-a-uuid"))).status_code == 401


def test_valid_token_for_unprovisioned_user_is_403(client, tenants):
    response = client.get("/api/v1/me", headers=bearer(token_for(uuid.uuid4())))
    assert response.status_code == 403
    assert "not provisioned" in response.json()["detail"]


def test_valid_token_resolves_the_right_tenant(client, tenants):
    body = client.get("/api/v1/me", headers=as_user(tenants.a_staff)).json()
    assert body["restaurant"]["name"] == "Kitchen A"
    assert body["user"]["role"] == "staff"


# --------------------------------------------------------------------------- roles


def test_staff_cannot_use_owner_manager_routes(client, tenants):
    dish = create_dish(client, tenants.a_owner)
    staff = as_user(tenants.a_staff)

    assert (
        client.post(
            "/api/v1/food-items",
            headers=staff,
            json={"name": "Nope", "preparation_unit": "plate", "batch_size": 1},
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/api/v1/food-items/{dish['id']}", headers=staff, json={"is_active": False})
        .status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/sales/import",
            headers=staff,
            files={"file": ("s.csv", sales_csv("Chicken Biryani", 10).encode(), "text/csv")},
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/forecasts/generate", headers=staff, json={"force": True}).status_code
        == 403
    )


def test_staff_can_record_daily_numbers_and_read_the_plan(client, tenants):
    dish = create_dish(client, tenants.a_owner)
    staff = as_user(tenants.a_staff)

    sale = client.post(
        "/api/v1/sales",
        headers=staff,
        json={"food_item_id": dish["id"], "sale_date": TODAY, "quantity_sold": 40},
    )
    assert sale.status_code == 200, sale.text

    waste = client.post(
        "/api/v1/waste",
        headers=staff,
        json={
            "food_item_id": dish["id"],
            "waste_date": TODAY,
            "quantity_wasted": 3,
            "reason": "unsold",
        },
    )
    assert waste.status_code == 201, waste.text
    assert client.get("/api/v1/forecasts/plan", headers=staff).status_code == 200


def test_manager_can_manage_the_catalogue(client, tenants):
    dish = create_dish(client, tenants.a_manager, "Manager Special")
    response = client.patch(
        f"/api/v1/food-items/{dish['id']}",
        headers=as_user(tenants.a_manager),
        json={"batch_size": 8},
    )
    assert response.status_code == 200
    assert response.json()["batch_size"] == 8


# --------------------------------------------------------------------------- tenant isolation


def test_other_tenants_dish_is_404_everywhere(client, tenants):
    dish_b = create_dish(client, tenants.b_owner, "Kitchen B Secret")
    owner_a = as_user(tenants.a_owner)

    assert (
        client.post(
            "/api/v1/sales",
            headers=owner_a,
            json={"food_item_id": dish_b["id"], "sale_date": TODAY, "quantity_sold": 5},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/waste",
            headers=owner_a,
            json={
                "food_item_id": dish_b["id"],
                "waste_date": TODAY,
                "quantity_wasted": 2,
                "reason": "spoilage",
            },
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/food-items/{dish_b['id']}", headers=owner_a, json={"name": "Hijacked"}
        ).status_code
        == 404
    )


def test_lists_never_leak_across_tenants(client, tenants):
    dish_a = create_dish(client, tenants.a_owner, "Kitchen A Dish")
    dish_b = create_dish(client, tenants.b_owner, "Kitchen B Dish")

    for owner, dish in ((tenants.a_owner, dish_a), (tenants.b_owner, dish_b)):
        headers = as_user(owner)
        client.post(
            "/api/v1/sales",
            headers=headers,
            json={"food_item_id": dish["id"], "sale_date": TODAY, "quantity_sold": 10},
        )
        client.post(
            "/api/v1/waste",
            headers=headers,
            json={
                "food_item_id": dish["id"],
                "waste_date": TODAY,
                "quantity_wasted": 1,
                "reason": "unsold",
            },
        )

    headers_a = as_user(tenants.a_owner)
    assert [row["name"] for row in client.get("/api/v1/food-items", headers=headers_a).json()] == [
        "Kitchen A Dish"
    ]
    assert [row["food_item"] for row in client.get("/api/v1/sales", headers=headers_a).json()] == [
        "Kitchen A Dish"
    ]
    assert [row["food_item"] for row in client.get("/api/v1/waste", headers=headers_a).json()] == [
        "Kitchen A Dish"
    ]
    plan_names = [
        row["food_item"] for row in client.get("/api/v1/forecasts/plan", headers=headers_a).json()["items"]
    ]
    assert plan_names == ["Kitchen A Dish"]
    assert client.get("/api/v1/analytics/summary", headers=headers_a).json()["sales_quantity"] == 10
