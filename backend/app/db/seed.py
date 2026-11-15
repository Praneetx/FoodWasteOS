"""Demo tenant + sample data for local development.

Seeding is idempotent and never runs unless ``SEED_DEMO_DATA`` is enabled in a
non-production environment. The generator deliberately over-prepares (as real
restaurants do) so waste analytics and the planner have something to show.
"""

from __future__ import annotations

import math
import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.db.models import DailySale, FoodItem, FoodWaste, Restaurant, User

DEMO_EMAIL = "demo@foodwasteos.local"
DOW_FACTORS = [0.85, 0.88, 0.92, 0.98, 1.12, 1.25, 1.18]  # Mon..Sun

DEMO_ITEMS = [
    # name, base demand, batch, unit cost
    ("Chicken Biryani", 85, 5, 120),
    ("Paneer Tikka", 35, 4, 180),
    ("Veg Pulao", 45, 5, 90),
    ("Butter Chicken", 60, 5, 160),
    ("Dal Khichdi", 25, 5, 70),
    ("Masala Dosa", 55, 2, 60),
    ("Chole Bhature", 40, 4, 80),
    ("Gulab Jamun", 30, 10, 30),
]


def ensure_demo_tenant(db: Session) -> CurrentUser:
    """Return (creating if needed) the local demo user."""
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is not None:
        return CurrentUser(
            id=user.id,
            restaurant_id=user.restaurant_id,
            email=user.email,
            name=user.name,
            role=user.role,
        )

    restaurant = Restaurant(
        name="Spice Route Kitchen",
        location="Navi Mumbai",
        timezone="Asia/Kolkata",
        currency="INR",
        default_unit_cost=Decimal("90"),
    )
    db.add(restaurant)
    db.flush()

    user = User(
        id=uuid.uuid4(),
        restaurant_id=restaurant.id,
        name="Demo Owner",
        email=DEMO_EMAIL,
        role="owner",
    )
    db.add(user)
    db.commit()

    return CurrentUser(
        id=user.id,
        restaurant_id=restaurant.id,
        email=user.email,
        name=user.name,
        role=user.role,
    )


def seed_demo_data(db: Session, days: int = 76) -> None:
    identity = ensure_demo_tenant(db)
    restaurant = db.get(Restaurant, identity.restaurant_id)
    if restaurant is None:
        return

    existing = db.scalar(
        select(FoodItem).where(FoodItem.restaurant_id == restaurant.id).limit(1)
    )
    if existing is not None:
        return

    rng = random.Random(11)
    today = datetime.now(ZoneInfo(restaurant.timezone)).date()
    items: list[FoodItem] = []

    for name, _base, batch, cost in DEMO_ITEMS:
        item = FoodItem(
            restaurant_id=restaurant.id,
            name=name,
            preparation_unit="plate",
            batch_size=batch,
            unit_cost=Decimal(cost),
        )
        db.add(item)
        items.append(item)
    db.flush()

    for item, (_, base, batch, _cost) in zip(items, DEMO_ITEMS):
        for offset in range(days, -1, -1):
            day = today - timedelta(days=offset)
            factor = DOW_FACTORS[day.weekday()]
            promotion = rng.random() < 0.07
            if promotion:
                factor *= 1.15
            sold = max(0, round(base * factor * rng.gauss(1.0, 0.09)))
            prepared = math.ceil(sold * (1.0 + rng.uniform(0.12, 0.28)) / batch) * batch
            db.add(
                DailySale(
                    restaurant_id=restaurant.id,
                    food_item_id=item.id,
                    sale_date=day,
                    quantity_sold=sold,
                    prepared_quantity=prepared,
                    promotion=promotion,
                    stockout=False,
                )
            )
            wasted = prepared - sold
            if wasted > 0:
                db.add(
                    FoodWaste(
                        restaurant_id=restaurant.id,
                        food_item_id=item.id,
                        waste_date=day,
                        quantity_wasted=Decimal(wasted),
                        reason="unsold",
                    )
                )

    db.commit()
