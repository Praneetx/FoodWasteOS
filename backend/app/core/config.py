from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration. No secrets in code."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FoodWasteOS API"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/foodwasteos"
    allowed_origins: str = "http://localhost:5173"

    # "dev" trusts a demo tenant and must never be enabled in production.
    auth_mode: Literal["dev", "supabase"] = "supabase"
    supabase_url: str | None = None
    supabase_jwt_aud: str = "authenticated"
    supabase_jwt_secret: str | None = None  # legacy HS256 projects only

    forecast_service_level: float = 0.85
    forecast_history_days: int = 180
    forecast_min_observations: int = 7
    # A stored plan older than this is flagged stale in the API and UI.
    plan_stale_hours: int = 36
    ml_artifact_dir: str = "./artifacts"

    max_csv_bytes: int = 5_000_000
    seed_demo_data: bool = False
    cron_secret: str | None = None

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def jwks_url(self) -> str | None:
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
