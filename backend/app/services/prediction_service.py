from sqlalchemy.ext.asyncio import AsyncSession
from app.services.race_service import get_race_detail
from app.ml.predict.service import predict_race, HorsePrediction
from typing import List

async def get_race_predictions(db: AsyncSession, race_id: int) -> List[HorsePrediction]:
    race = await get_race_detail(db, race_id)
    if not race:
        return []
    
    # In a real app, this would read from the DB or trigger the ML pipeline if not cached
    # Now calls real ML inference pipeline
    return await predict_race(db, race_id)
