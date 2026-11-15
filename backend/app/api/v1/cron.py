from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_cron_secret
from app.db.session import get_db
from app.schemas.forecasts import CronGenerateOut, CronGenerateRequest
from app.services.forecasting import generate_for_all_restaurants

router = APIRouter(prefix="/cron", tags=["cron"], dependencies=[Depends(require_cron_secret)])


@router.post("/generate", response_model=CronGenerateOut)
def nightly_generate(
    payload: CronGenerateRequest | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Generate upcoming plans for all restaurants. Authenticated by ``X-Cron-Secret``."""
    options = payload or CronGenerateRequest()
    return generate_for_all_restaurants(db, days_ahead=options.days_ahead, force=options.force)
