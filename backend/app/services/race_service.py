import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from app.db.models.crawl import Race, RaceEntry, Horse, Jockey, Trainer


async def get_races_by_date(db: AsyncSession, date: datetime.date, track: str = None) -> list[Race]:
    query = select(Race).where(Race.race_date == date)
    if track:
        query = query.where(Race.track == track)
    query = query.order_by(Race.post_time)
    result = await db.execute(query)
    return list(result.scalars().all())


from typing import Optional

async def get_race_detail(db: AsyncSession, race_id: int) -> Optional[Race]:
    query = (
        select(Race)
        .options(
            joinedload(Race.entries).joinedload(RaceEntry.horse),
            joinedload(Race.entries).joinedload(RaceEntry.jockey),
            joinedload(Race.entries).joinedload(RaceEntry.trainer),
        )
        .where(Race.id == race_id)
    )
    result = await db.execute(query)
    return result.scalars().first()
