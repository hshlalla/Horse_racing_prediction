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
    completed: bool = False

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
    finish_position: Optional[int] = None
    finish_time_s: Optional[float] = None

class RaceDetailResponse(RaceListResponseItem):
    track_condition: Optional[str]
    weather: Optional[str]
    humidity: Optional[int] = None
    video_url: Optional[str]
    payouts: Optional[dict] = None
    entries: List[RaceEntryResponse]

@router.get("/latest-date")
async def get_latest_race_date(db: AsyncSession = Depends(get_db)):
    """Return the most recent date that has at least one race."""
    from sqlalchemy import select, func
    from app.db.models.crawl import Race
    result = await db.execute(select(func.max(Race.race_date)))
    latest = result.scalar()
    return {"date": (latest or datetime.date.today()).isoformat()}


@router.get("", response_model=RaceListResponse)
async def list_races(
    date: datetime.date = Query(...),
    track: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select, func
    from app.db.models.crawl import Race, RaceResult

    races = await race_service.get_races_by_date(db, date, track)
    if not races:
        return RaceListResponse(items=[])

    # 결과 있는 race_id 집합을 한 번에 조회
    race_ids = [r.id for r in races]
    res = await db.execute(
        select(RaceResult.race_id)
        .where(RaceResult.race_id.in_(race_ids))
        .where(RaceResult.finish_position.isnot(None))
        .distinct()
    )
    completed_ids = {row[0] for row in res.all()}

    items = []
    for r in races:
        items.append(RaceListResponseItem(
            id=r.id, track=r.track, race_date=r.race_date, race_number=r.race_number,
            race_name=r.race_name, distance_m=r.distance_m, surface=r.surface,
            post_time=r.post_time, field_size=r.field_size,
            completed=r.id in completed_ids,
        ))
    return RaceListResponse(items=items)

@router.post("/{race_id}/fetch-results")
async def fetch_race_results(race_id: int, db: AsyncSession = Depends(get_db)):
    """KRA에서 경주 결과를 즉시 크롤링합니다."""
    from sqlalchemy import delete
    from app.db.models.crawl import Race, RacePrediction
    from app.ml.crawl.pipeline import _ingest_race_detail
    from app.db.session import async_session_factory

    race = await race_service.get_race_detail(db, race_id)
    if not race:
        return error_response("RACE_NOT_FOUND", "Race not found", 404)

    race_date_str = race.race_date.strftime("%Y%m%d")

    async with async_session_factory() as session:
        ok = await _ingest_race_detail(session, race.track, race_date_str, race.race_number)

    if not ok:
        return {"ok": False, "message": "KRA에서 결과를 아직 가져올 수 없습니다. 잠시 후 다시 시도해주세요."}

    # 예측 캐시 삭제 (결과 반영)
    await db.execute(delete(RacePrediction).where(RacePrediction.race_id == race_id))
    await db.commit()

    return {"ok": True, "message": "결과를 성공적으로 가져왔습니다."}


@router.get("/{race_id}", response_model=RaceDetailResponse)
async def get_race(race_id: int, db: AsyncSession = Depends(get_db)):
    race = await race_service.get_race_detail(db, race_id)
    if not race:
        return error_response("RACE_NOT_FOUND", "Race not found", 404)
    
    results_map = getattr(race, '_loaded_results', {})
    
    entries = []
    for e in race.entries:
        result = results_map.get(e.horse_id)
        entries.append(RaceEntryResponse(
            id=e.id,
            program_number=e.program_number,
            horse_id=e.horse.id,
            horse_name=e.horse.name,
            jockey_name=e.jockey.name if e.jockey else None,
            trainer_name=e.trainer.name if e.trainer else None,
            carry_weight_kg=e.carry_weight_kg,
            morning_odds=e.morning_odds,
            finish_position=result.finish_position if result else None,
            finish_time_s=result.finish_time_s if result else None,
        ))
    
    return RaceDetailResponse(
        id=race.id, track=race.track, race_date=race.race_date, race_number=race.race_number,
        race_name=race.race_name, distance_m=race.distance_m, surface=race.surface,
        post_time=race.post_time, field_size=race.field_size,
        track_condition=race.track_condition, weather=race.weather,
        humidity=race.humidity,
        video_url=race.video_url,
        payouts=race.payouts,
        entries=entries
    )

