from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api.deps import get_db
from app.core.errors import error_response
from app.services import prediction_service
from app.ml.predict.service import HorsePrediction
from app.db.models.crawl import RaceEntry
from pydantic import BaseModel

router = APIRouter(prefix="/races", tags=["predictions"])

class PredictionListResponse(BaseModel):
    items: List[HorsePrediction]
    # False when no entry has a real morning_odds — the model is odds-dominated,
    # so predictions collapse toward uniform and should not be trusted.
    odds_available: bool = True

@router.get("/{race_id}/predictions", response_model=PredictionListResponse)
async def get_predictions(race_id: int, db: AsyncSession = Depends(get_db)):
    predictions = await prediction_service.get_race_predictions(db, race_id)
    if not predictions:
        return error_response("RACE_NOT_FOUND", "Race not found or no predictions available", 404)

    odds = (
        await db.execute(
            select(RaceEntry.morning_odds).where(RaceEntry.race_id == race_id)
        )
    ).scalars().all()
    odds_available = any(o is not None for o in odds)

    return PredictionListResponse(items=predictions, odds_available=odds_available)
