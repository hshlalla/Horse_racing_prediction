from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import joinedload
from app.db.models.users import Favorite
from app.db.models.crawl import Horse
from typing import List

async def get_user_favorites(db: AsyncSession, user_id: int) -> List[Favorite]:
    query = (
        select(Favorite)
        .options(joinedload(Favorite.horse))
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())

async def add_favorite(db: AsyncSession, user_id: int, horse_id: int) -> Favorite:
    # Check if already exists
    existing = await db.execute(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.horse_id == horse_id)
    )
    if existing.scalar_one_or_none():
        return None

    favorite = Favorite(user_id=user_id, horse_id=horse_id)
    db.add(favorite)
    await db.commit()
    return favorite

async def remove_favorite(db: AsyncSession, user_id: int, horse_id: int) -> bool:
    result = await db.execute(
        delete(Favorite).where(Favorite.user_id == user_id, Favorite.horse_id == horse_id)
    )
    await db.commit()
    return result.rowcount > 0
