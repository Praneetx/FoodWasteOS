"""Supabase JWT verification and the tenant identity object."""

import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient

from app.core.config import settings


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    restaurant_id: uuid.UUID
    email: str
    name: str | None
    role: str

    def require_role(self, *roles: str) -> None:
        if self.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role: {', '.join(roles)}",
            )


@lru_cache
def _jwks_client() -> PyJWKClient:
    if not settings.jwks_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_URL is not configured",
        )
    return PyJWKClient(settings.jwks_url)


def decode_token(token: str) -> dict:
    """Verify a Supabase access token and return its claims."""
    try:
        if settings.supabase_jwt_secret:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_aud,
            )

        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=settings.supabase_jwt_aud,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
