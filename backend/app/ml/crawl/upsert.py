import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.crawl import (
    Horse, HealthRecord, InraceTiming, Jockey, Race, RaceEntry, RaceResult, Trainer, WorkoutTime,
)


async def upsert_horse(session: AsyncSession, name: str, sex: str,
                       age: Optional[int] = None) -> int:
    stmt = (
        pg_insert(Horse)
        .values(name=name, sex=sex, age=age)
        .on_conflict_do_update(
            index_elements=["name"],
            set_={"sex": sa.literal(sex), "age": sa.literal(age)},
        )
        .returning(Horse.id)
    )
    return (await session.execute(stmt)).scalar_one()


async def upsert_jockey(session: AsyncSession, name: str,
                        kra_code: Optional[str] = None) -> int:
    stmt = (
        pg_insert(Jockey)
        .values(name=name, kra_code=kra_code)
        .on_conflict_do_update(
            index_elements=["name"],
            set_={"kra_code": sa.literal(kra_code)},
        )
        .returning(Jockey.id)
    )
    return (await session.execute(stmt)).scalar_one()


async def upsert_trainer(session: AsyncSession, name: str,
                         kra_code: Optional[str] = None) -> int:
    stmt = (
        pg_insert(Trainer)
        .values(name=name, kra_code=kra_code)
        .on_conflict_do_update(
            index_elements=["name"],
            set_={"kra_code": sa.literal(kra_code)},
        )
        .returning(Trainer.id)
    )
    return (await session.execute(stmt)).scalar_one()


async def upsert_race(session: AsyncSession, track: str, race_date: datetime.date,
                      race_number: int, race_name: str, distance_m: int, surface: str,
                      track_condition: Optional[str] = None, weather: Optional[str] = None,
                      humidity: Optional[int] = None,
                      grade: Optional[str] = None, field_size: Optional[int] = None,
                      post_time: Optional[datetime.datetime] = None,
                      video_url: Optional[str] = None,
                      payouts: Optional[dict] = None) -> int:
    stmt = (
        pg_insert(Race)
        .values(
            track=track, race_date=race_date, race_number=race_number,
            race_name=race_name, distance_m=distance_m, surface=surface,
            track_condition=track_condition, weather=weather,
            humidity=humidity, grade=grade, field_size=field_size,
            post_time=post_time, video_url=video_url, payouts=payouts,
        )
        .on_conflict_do_update(
            index_elements=["track", "race_date", "race_number"],
            set_={
                "race_name": sa.literal(race_name),
                "distance_m": sa.literal(distance_m),
                "surface": sa.literal(surface),
                "track_condition": sa.literal(track_condition),
                "weather": sa.literal(weather),
                "humidity": sa.literal(humidity),
                "grade": sa.literal(grade),
                "field_size": sa.literal(field_size),
                "post_time": sa.func.coalesce(sa.literal(post_time), sa.text("races.post_time")),
                # Use COALESCE so backfilled values aren't overwritten by NULL
                "video_url": sa.func.coalesce(sa.literal(video_url), sa.text("races.video_url")),
                "payouts": sa.func.coalesce(
                    sa.literal(payouts, type_=sa.JSON), sa.text("races.payouts")
                ),
            },
        )
        .returning(Race.id)
    )
    return (await session.execute(stmt)).scalar_one()


async def upsert_race_entry(session: AsyncSession, race_id: int, horse_id: int,
                            program_number: int, jockey_id: Optional[int] = None,
                            trainer_id: Optional[int] = None,
                            carry_weight_kg: Optional[float] = None,
                            body_weight_kg: Optional[float] = None,
                            morning_odds: Optional[float] = None) -> None:
    stmt = (
        pg_insert(RaceEntry)
        .values(
            race_id=race_id, horse_id=horse_id, program_number=program_number,
            jockey_id=jockey_id, trainer_id=trainer_id,
            carry_weight_kg=carry_weight_kg, body_weight_kg=body_weight_kg,
            morning_odds=morning_odds,
        )
        .on_conflict_do_update(
            index_elements=["race_id", "program_number"],
            set_={
                "horse_id": sa.literal(horse_id),
                "jockey_id": sa.literal(jockey_id),
                "trainer_id": sa.literal(trainer_id),
                "carry_weight_kg": sa.literal(carry_weight_kg),
                "body_weight_kg": sa.literal(body_weight_kg),
                "morning_odds": sa.literal(morning_odds),
            },
        )
    )
    await session.execute(stmt)


async def upsert_race_result(session: AsyncSession, race_id: int, horse_id: int,
                             finish_position: Optional[int] = None,
                             finish_time_s: Optional[float] = None,
                             final_odds: Optional[float] = None) -> None:
    stmt = (
        pg_insert(RaceResult)
        .values(
            race_id=race_id, horse_id=horse_id,
            finish_position=finish_position,
            finish_time_s=finish_time_s,
            final_odds=final_odds,
        )
        .on_conflict_do_update(
            index_elements=["race_id", "horse_id"],
            set_={
                "finish_position": sa.literal(finish_position),
                "finish_time_s": sa.literal(finish_time_s),
                "final_odds": sa.literal(final_odds),
            },
        )
    )
    await session.execute(stmt)


async def upsert_inrace_timing(session: AsyncSession, race_id: int, horse_id: int,
                               s1f_time: Optional[float] = None,
                               g3f_time: Optional[float] = None,
                               corner1_rank: Optional[int] = None,
                               corner2_rank: Optional[int] = None,
                               corner3_rank: Optional[int] = None,
                               corner4_rank: Optional[int] = None,
                               corner5_rank: Optional[int] = None,
                               corner6_rank: Optional[int] = None,
                               corner7_rank: Optional[int] = None) -> None:
    stmt = (
        pg_insert(InraceTiming)
        .values(
            race_id=race_id, horse_id=horse_id,
            s1f_time=s1f_time, g3f_time=g3f_time,
            corner1_rank=corner1_rank, corner2_rank=corner2_rank,
            corner3_rank=corner3_rank, corner4_rank=corner4_rank,
            corner5_rank=corner5_rank, corner6_rank=corner6_rank,
            corner7_rank=corner7_rank,
        )
        .on_conflict_do_update(
            index_elements=["race_id", "horse_id"],
            set_={
                "s1f_time": sa.literal(s1f_time),
                "g3f_time": sa.literal(g3f_time),
                "corner1_rank": sa.literal(corner1_rank),
                "corner2_rank": sa.literal(corner2_rank),
                "corner3_rank": sa.literal(corner3_rank),
                "corner4_rank": sa.literal(corner4_rank),
                "corner5_rank": sa.literal(corner5_rank),
                "corner6_rank": sa.literal(corner6_rank),
                "corner7_rank": sa.literal(corner7_rank),
            },
        )
    )
    await session.execute(stmt)


async def upsert_health_record(
    session: AsyncSession,
    horse_id: int,
    record_date: datetime.date,
    condition: Optional[str] = None,
    count: int = 1,
) -> None:
    stmt = (
        pg_insert(HealthRecord)
        .values(horse_id=horse_id, record_date=record_date, condition=condition, count=count)
        .on_conflict_do_update(
            index_elements=["horse_id", "record_date", "condition"],
            set_={"count": sa.literal(count)},
        )
    )
    await session.execute(stmt)


async def upsert_workout_time(
    session: AsyncSession,
    horse_id: int,
    workout_date: datetime.date,
    workout_type: Optional[str] = None,
    distance_m: int = 1000,
    time_s: Optional[float] = None,
    rank: Optional[int] = None,
    group_size: Optional[int] = None,
) -> None:
    stmt = (
        pg_insert(WorkoutTime)
        .values(
            horse_id=horse_id, workout_date=workout_date,
            workout_type=workout_type, distance_m=distance_m,
            time_s=time_s, rank=rank, group_size=group_size,
        )
        .on_conflict_do_update(
            index_elements=["horse_id", "workout_date", "distance_m"],
            set_={
                "workout_type": sa.literal(workout_type),
                "time_s": sa.func.coalesce(sa.literal(time_s), sa.text("workout_times.time_s")),
                "rank": sa.func.coalesce(sa.literal(rank), sa.text("workout_times.rank")),
                "group_size": sa.func.coalesce(sa.literal(group_size), sa.text("workout_times.group_size")),
            },
        )
    )
    await session.execute(stmt)
