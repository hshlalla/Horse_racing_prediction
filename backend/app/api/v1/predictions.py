from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api.deps import get_db
from app.core.errors import error_response
from app.services import prediction_service
from app.ml.predict.service import HorsePrediction
from pydantic import BaseModel

router = APIRouter(prefix="/races", tags=["predictions"])

class PredictionListResponse(BaseModel):
    items: List[HorsePrediction]

@router.get("/{race_id}/predictions", response_model=PredictionListResponse)
async def get_predictions(race_id: int, db: AsyncSession = Depends(get_db)):
    predictions = await prediction_service.get_race_predictions(db, race_id)
    if not predictions:
        return error_response("RACE_NOT_FOUND", "Race not found or no predictions available", 404)
    return PredictionListResponse(items=predictions)
