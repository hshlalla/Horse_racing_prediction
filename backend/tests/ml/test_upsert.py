import pytest
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.ml.crawl.upsert import (
    upsert_horse, upsert_jockey, upsert_trainer,
    upsert_race, upsert_race_result, upsert_inrace_timing, upsert_race_entry,
)

@pytest.fixture
async def session(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()

@pytest.mark.asyncio
async def test_upsert_horse_idempotent(session):
    id1 = await upsert_horse(session, name="천하무적", sex="M", age=4)
    id2 = await upsert_horse(session, name="천하무적", sex="M", age=4)
    assert id1 == id2

@pytest.mark.asyncio
async def test_upsert_jockey_idempotent(session):
    id1 = await upsert_jockey(session, name="김민수", kra_code="JK001")
    id2 = await upsert_jockey(session, name="김민수", kra_code="JK001")
    assert id1 == id2

@pytest.mark.asyncio
async def test_upsert_race_idempotent(session):
    id1 = await upsert_race(session, track="SEOUL", race_date=datetime.date(2026, 6, 21),
                            race_number=1, race_name="1경주", distance_m=1200, surface="DIRT")
    id2 = await upsert_race(session, track="SEOUL", race_date=datetime.date(2026, 6, 21),
                            race_number=1, race_name="1경주 수정", distance_m=1200, surface="DIRT")
    assert id1 == id2  # same race, name update is fine — same PK
