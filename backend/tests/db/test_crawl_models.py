import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.crawl import Horse, Race, RaceEntry


@pytest.mark.asyncio
async def test_insert_horse(db_session: AsyncSession):
    horse = Horse(
        name="테스트마",
        sex="M",
        age=4,
        breed_origin="KOR",
    )
    db_session.add(horse)
    await db_session.flush()
    assert horse.id is not None


@pytest.mark.asyncio
async def test_insert_race(db_session: AsyncSession):
    import datetime
    race = Race(
        track="SEOUL",
        race_date=datetime.date(2024, 1, 6),
        race_number=1,
        race_name="서울 1경주",
        distance_m=1200,
        surface="TURF",
        grade="G3",
        race_class="일반",
        field_size=10,
    )
    db_session.add(race)
    await db_session.flush()
    assert race.id is not None
