import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.seed import seed_demo_data
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    if settings.auth_mode == "dev" and settings.app_env in {"staging", "production"}:
        raise RuntimeError("AUTH_MODE=dev must never be enabled outside local development")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Dev convenience only; production schema comes from supabase/schema.sql.
        if settings.app_env == "development":
            Base.metadata.create_all(bind=engine)
            if settings.seed_demo_data:
                with SessionLocal() as db:
                    seed_demo_data(db)
                    logger.info("demo data ready")
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Daily Preparation Intelligence Engine for restaurants.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"])
    def health():
        try:
            with SessionLocal() as db:
                db.execute(text("select 1"))
        except Exception:  # noqa: BLE001 - health must report, not raise
            logger.exception("health check failed")
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "database": "unavailable",
                    "version": settings.app_version,
                },
            )
        return {"status": "ok", "database": "ok", "version": settings.app_version}

    @app.get("/", include_in_schema=False)
    def root():
        return {"name": settings.app_name, "version": settings.app_version, "docs": "/docs"}

    return app


app = create_app()
