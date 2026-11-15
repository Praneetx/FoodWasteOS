from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    email: str
    role: str


class RestaurantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    location: str | None
    timezone: str
    currency: str


class MeOut(BaseModel):
    user: UserOut
    restaurant: RestaurantOut
