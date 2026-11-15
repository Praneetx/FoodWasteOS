from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser, decode_token
from app.db.models import Restaurant, User
from app.db.seed import ensure_demo_tenant
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Resolve the caller to an app user + tenant.

    ``dev`` mode trusts a local demo tenant; it is rejected outside development
    by ``config`` validation in ``main``.
    """
    if settings.auth_mode == "dev":
        return ensure_demo_tenant(db)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_token(credentials.credentials)
    subject = claims.get("sub")
    try:
        user_id = uuid.UUID(str(subject))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token subject"
        ) from exc

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user profile is not provisioned for this restaurant",
        )

    return CurrentUser(
        id=user.id,
        restaurant_id=user.restaurant_id,
        email=user.email,
        name=user.name,
        role=user.role,
    )


def get_restaurant(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Restaurant:
    restaurant = db.get(Restaurant, user.restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="restaurant not found")
    return restaurant
