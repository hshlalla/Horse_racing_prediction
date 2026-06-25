import datetime
import random
from pydantic import BaseModel
from typing import List

class HorsePrediction(BaseModel):
    horse_id: int
    horse_name: str
    program_number: int
    win_probability: float
    place_probability: float
    model_versions: dict[str, str]
    features_snapshot: dict
    computed_at: datetime.datetime

async def predict_race(race_id: int, entries: list) -> List[HorsePrediction]:
    # This is a stub implementation
    predictions = []
    
    # Generate random probabilities that sum to ~1
    raw_probs = [random.uniform(0.1, 0.9) for _ in entries]
    total = sum(raw_probs)
    win_probs = [p / total for p in raw_probs]
    
    for i, entry in enumerate(entries):
        predictions.append(HorsePrediction(
            horse_id=entry.horse.id,
            horse_name=entry.horse.name,
            program_number=entry.program_number,
            win_probability=win_probs[i],
            place_probability=min(win_probs[i] * 3, 0.99), # Simplified place probability
            model_versions={"lgbm": "v1.0-mock", "catboost": "v1.0-mock", "ensemble": "v1.0-mock"},
            features_snapshot={"mock": True},
            computed_at=datetime.datetime.now(datetime.timezone.utc)
        ))
        
    predictions.sort(key=lambda x: x.win_probability, reverse=True)
    return predictions
