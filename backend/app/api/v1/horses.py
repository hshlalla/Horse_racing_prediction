import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List

from app.api.deps import get_db
from app.core.errors import error_response
from app.db.models.crawl import Horse, RaceEntry, RaceResult, Race, Pedigree
from pydantic import BaseModel


router = APIRouter(prefix="/horses", tags=["horses"])


class HorseBioResponse(BaseModel):
    id: int
    name: str
    sex: Optional[str]
    age: Optional[int]
    breed_origin: Optional[str]
    import_year: Optional[int]
    sire_name: Optional[str]
    dam_name: Optional[str]
    lifetime_starts: int
    lifetime_wins: int
    lifetime_places: int  # top-3


class HorseHistoryItem(BaseModel):
    race_id: int
    race_date: datetime.date
    track: str
    race_number: int
    distance_m: int
    surface: str
    finish_position: Optional[int]
    finish_time_s: Optional[float]
    final_odds: Optional[float]
    field_size: Optional[int]


class HorseHistoryResponse(BaseModel):
    items: List[HorseHistoryItem]
    next_cursor: Optional[str] = None


@router.get("/{horse_id}", response_model=HorseBioResponse)
async def get_horse(horse_id: int, db: AsyncSession = Depends(get_db)):
    """Horse bio + recent form."""
    result = await db.execute(select(Horse).where(Horse.id == horse_id))
    horse = result.scalar_one_or_none()
    if not horse:
        return error_response("HORSE_NOT_FOUND", "Horse not found", 404)

    # Pedigree lookup
    ped_result = await db.execute(select(Pedigree).where(Pedigree.horse_id == horse_id))
    pedigree = ped_result.scalar_one_or_none()
    sire_name = None
    dam_name = None
    if pedigree:
        if pedigree.sire_id:
            sire = await db.execute(select(Horse).where(Horse.id == pedigree.sire_id))
            sire_obj = sire.scalar_one_or_none()
            sire_name = sire_obj.name if sire_obj else None
        if pedigree.dam_id:
            dam = await db.execute(select(Horse).where(Horse.id == pedigree.dam_id))
            dam_obj = dam.scalar_one_or_none()
            dam_name = dam_obj.name if dam_obj else None

    # Lifetime stats
    results = await db.execute(
        select(RaceResult).where(RaceResult.horse_id == horse_id)
    )
    all_results = results.scalars().all()
    lifetime_starts = len(all_results)
    lifetime_wins = sum(1 for r in all_results if r.finish_position == 1)
    lifetime_places = sum(1 for r in all_results if r.finish_position and r.finish_position <= 3)

    return HorseBioResponse(
        id=horse.id,
        name=horse.name,
        sex=horse.sex,
        age=horse.age,
        breed_origin=horse.breed_origin,
        import_year=horse.import_year,
        sire_name=sire_name,
        dam_name=dam_name,
        lifetime_starts=lifetime_starts,
        lifetime_wins=lifetime_wins,
        lifetime_places=lifetime_places,
    )


@router.get("/{horse_id}/history", response_model=HorseHistoryResponse)
async def get_horse_history(horse_id: int, db: AsyncSession = Depends(get_db)):
    """Past finishes for a horse."""
    # Verify horse exists
    result = await db.execute(select(Horse).where(Horse.id == horse_id))
    horse = result.scalar_one_or_none()
    if not horse:
        return error_response("HORSE_NOT_FOUND", "Horse not found", 404)

    # Join race_results with races to get full history
    stmt = (
        select(RaceResult, Race)
        .join(Race, RaceResult.race_id == Race.id)
        .where(RaceResult.horse_id == horse_id)
        .order_by(Race.race_date.desc())
    )
    rows = await db.execute(stmt)
    items = []
    for rr, race in rows:
        items.append(HorseHistoryItem(
            race_id=race.id,
            race_date=race.race_date,
            track=race.track,
            race_number=race.race_number,
            distance_m=race.distance_m,
            surface=race.surface,
            finish_position=rr.finish_position,
            finish_time_s=rr.finish_time_s,
            final_odds=rr.final_odds,
            field_size=race.field_size,
        ))

    return HorseHistoryResponse(items=items)
