import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.api.deps import get_db
from app.core.errors import error_response
from app.services import race_service
from pydantic import BaseModel

router = APIRouter(prefix="/races", tags=["races"])

class RaceListResponseItem(BaseModel):
    id: int
    track: str
    race_date: datetime.date
    race_number: int
    race_name: str
    distance_m: int
    surface: str
    post_time: Optional[datetime.datetime]
    field_size: Optional[int]

class RaceListResponse(BaseModel):
    items: List[RaceListResponseItem]

class RaceEntryResponse(BaseModel):
    id: int
    program_number: int
    horse_id: int
    horse_name: str
    jockey_name: Optional[str]
    trainer_name: Optional[str]
    carry_weight_kg: Optional[float]
    morning_odds: Optional[float]

class RaceDetailResponse(RaceListResponseItem):
    track_condition: Optional[str]
    weather: Optional[str]
    video_url: Optional[str]
    entries: List[RaceEntryResponse]

@router.get("", response_model=RaceListResponse)
async def list_races(
    date: datetime.date = Query(...),
    track: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    races = await race_service.get_races_by_date(db, date, track)
    items = []
    for r in races:
        items.append(RaceListResponseItem(
            id=r.id, track=r.track, race_date=r.race_date, race_number=r.race_number,
            race_name=r.race_name, distance_m=r.distance_m, surface=r.surface,
            post_time=r.post_time, field_size=r.field_size
        ))
    return RaceListResponse(items=items)

@router.get("/{race_id}", response_model=RaceDetailResponse)
async def get_race(race_id: int, db: AsyncSession = Depends(get_db)):
    race = await race_service.get_race_detail(db, race_id)
    if not race:
        return error_response("RACE_NOT_FOUND", "Race not found", 404)
    
    entries = []
    for e in race.entries:
        entries.append(RaceEntryResponse(
            id=e.id,
            program_number=e.program_number,
            horse_id=e.horse.id,
            horse_name=e.horse.name,
            jockey_name=e.jockey.name if e.jockey else None,
            trainer_name=e.trainer.name if e.trainer else None,
            carry_weight_kg=e.carry_weight_kg,
            morning_odds=e.morning_odds
        ))
    
    return RaceDetailResponse(
        id=race.id, track=race.track, race_date=race.race_date, race_number=race.race_number,
        race_name=race.race_name, distance_m=race.distance_m, surface=race.surface,
        post_time=race.post_time, field_size=race.field_size,
        track_condition=race.track_condition, weather=race.weather,
        video_url=race.video_url,
        entries=entries
    )
