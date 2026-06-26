import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models.crawl import (
    Horse, Jockey, Trainer, Race, RaceEntry, RaceResult, InraceTiming
)


async def upsert_horse(session: AsyncSession, name: str, sex: str,
                       age: Optional[int] = None) -> int:
    """Find horse by name or insert. Returns horse.id."""
    result = await session.execute(select(Horse).where(Horse.name == name))
    horse = result.scalars().first()
    if horse is None:
        horse = Horse(name=name, sex=sex, age=age)
        session.add(horse)
        await session.flush()
    return horse.id


async def upsert_jockey(session: AsyncSession, name: str,
                        kra_code: Optional[str] = None) -> int:
    """Find jockey by kra_code (or name if no code) or insert."""
    if kra_code:
        result = await session.execute(select(Jockey).where(Jockey.kra_code == kra_code))
    else:
        result = await session.execute(select(Jockey).where(Jockey.name == name))
    jockey = result.scalars().first()
    if jockey is None:
        jockey = Jockey(name=name, kra_code=kra_code)
        session.add(jockey)
        await session.flush()
    return jockey.id


async def upsert_trainer(session: AsyncSession, name: str,
                         kra_code: Optional[str] = None) -> int:
    """Find trainer by kra_code (or name if no code) or insert."""
    if kra_code:
        result = await session.execute(select(Trainer).where(Trainer.kra_code == kra_code))
    else:
        result = await session.execute(select(Trainer).where(Trainer.name == name))
    trainer = result.scalars().first()
    if trainer is None:
        trainer = Trainer(name=name, kra_code=kra_code)
        session.add(trainer)
        await session.flush()
    return trainer.id


async def upsert_race(session: AsyncSession, track: str, race_date: datetime.date,
                      race_number: int, race_name: str, distance_m: int, surface: str,
                      track_condition: Optional[str] = None, weather: Optional[str] = None,
                      grade: Optional[str] = None, field_size: Optional[int] = None,
                      post_time: Optional[datetime.datetime] = None) -> int:
    """Upsert race by (track, race_date, race_number). Returns race.id."""
    result = await session.execute(
        select(Race).where(
            Race.track == track,
            Race.race_date == race_date,
            Race.race_number == race_number,
        )
    )
    race = result.scalars().first()
    if race is None:
        race = Race(
            track=track, race_date=race_date, race_number=race_number,
            race_name=race_name, distance_m=distance_m, surface=surface,
            track_condition=track_condition, weather=weather,
            grade=grade, field_size=field_size, post_time=post_time,
        )
        session.add(race)
        await session.flush()
    else:
        # Update mutable fields
        race.race_name = race_name
        race.track_condition = track_condition
        race.weather = weather
        race.field_size = field_size
        race.post_time = post_time
    return race.id


async def upsert_race_entry(session: AsyncSession, race_id: int, horse_id: int,
                            program_number: int, jockey_id: Optional[int] = None,
                            trainer_id: Optional[int] = None,
                            carry_weight_kg: Optional[float] = None,
                            body_weight_kg: Optional[float] = None,
                            morning_odds: Optional[float] = None) -> None:
    """Upsert race entry by (race_id, program_number)."""
    result = await session.execute(
        select(RaceEntry).where(
            RaceEntry.race_id == race_id,
            RaceEntry.program_number == program_number,
        )
    )
    entry = result.scalars().first()
    if entry is None:
        entry = RaceEntry(
            race_id=race_id, horse_id=horse_id, program_number=program_number,
            jockey_id=jockey_id, trainer_id=trainer_id,
            carry_weight_kg=carry_weight_kg, body_weight_kg=body_weight_kg,
            morning_odds=morning_odds,
        )
        session.add(entry)
    else:
        entry.jockey_id = jockey_id
        entry.trainer_id = trainer_id
        entry.carry_weight_kg = carry_weight_kg
        entry.body_weight_kg = body_weight_kg
        entry.morning_odds = morning_odds


async def upsert_race_result(session: AsyncSession, race_id: int, horse_id: int,
                             finish_position: Optional[int] = None,
                             finish_time_s: Optional[float] = None,
                             final_odds: Optional[float] = None) -> None:
    """Upsert race result by (race_id, horse_id)."""
    result = await session.execute(
        select(RaceResult).where(
            RaceResult.race_id == race_id,
            RaceResult.horse_id == horse_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        row = RaceResult(
            race_id=race_id, horse_id=horse_id,
            finish_position=finish_position,
            finish_time_s=finish_time_s,
            final_odds=final_odds,
        )
        session.add(row)
    else:
        row.finish_position = finish_position
        row.finish_time_s = finish_time_s
        row.final_odds = final_odds


async def upsert_inrace_timing(session: AsyncSession, race_id: int, horse_id: int,
                               s1f_time: Optional[float] = None,
                               g3f_time: Optional[float] = None) -> None:
    """Upsert inrace timing by (race_id, horse_id)."""
    result = await session.execute(
        select(InraceTiming).where(
            InraceTiming.race_id == race_id,
            InraceTiming.horse_id == horse_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        row = InraceTiming(
            race_id=race_id, horse_id=horse_id,
            s1f_time=s1f_time, g3f_time=g3f_time,
        )
        session.add(row)
    else:
        row.s1f_time = s1f_time
        row.g3f_time = g3f_time
