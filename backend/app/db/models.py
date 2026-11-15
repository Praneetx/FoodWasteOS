from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str | None] = mapped_column(String(160))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    default_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role in ('owner', 'manager', 'staff')", name="role_valid"),)

    # Mirrors auth.users.id from Supabase.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="owner")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FoodItem(Base):
    __tablename__ = "food_items"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "name", name="uq_food_items_tenant_name"),
        CheckConstraint("batch_size > 0", name="batch_size_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    preparation_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="plate")
    batch_size: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=1)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DailySale(Base):
    __tablename__ = "daily_sales"
    __table_args__ = (
        UniqueConstraint("food_item_id", "sale_date", name="uq_daily_sales_item_date"),
        CheckConstraint("quantity_sold >= 0", name="quantity_sold_non_negative"),
        Index("ix_daily_sales_tenant_date", "restaurant_id", "sale_date"),
        Index("ix_daily_sales_item_date", "food_item_id", "sale_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    food_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("food_items.id", ondelete="CASCADE"), nullable=False
    )
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prepared_quantity: Mapped[int | None] = mapped_column(Integer)
    promotion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stockout: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class FoodWaste(Base):
    __tablename__ = "food_waste"
    __table_args__ = (
        UniqueConstraint("food_item_id", "waste_date", "reason", name="uq_food_waste_item_date_reason"),
        CheckConstraint("quantity_wasted > 0", name="quantity_wasted_positive"),
        CheckConstraint(
            "reason in ('overproduction', 'unsold', 'spoilage', 'expired', 'other')",
            name="reason_valid",
        ),
        Index("ix_food_waste_tenant_date", "restaurant_id", "waste_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    food_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("food_items.id", ondelete="CASCADE"), nullable=False
    )
    waste_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_wasted: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    train_start: Mapped[date | None] = mapped_column(Date)
    train_end: Mapped[date | None] = mapped_column(Date)
    mae: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    wape: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    bias: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    # jsonb on Postgres (matches supabase/schema.sql); plain JSON on SQLite for tests/demo.
    params: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    artifact_path: Mapped[str | None] = mapped_column(Text)


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("food_item_id", "target_date", name="uq_forecasts_item_date"),
        CheckConstraint(
            "confidence in ('high', 'medium', 'low')", name="confidence_valid"
        ),
        Index("ix_forecasts_tenant_date", "restaurant_id", "target_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    food_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("food_items.id", ondelete="CASCADE"), nullable=False
    )
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_demand: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    recommended_preparation: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
