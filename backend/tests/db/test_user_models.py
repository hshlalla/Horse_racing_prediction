import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.users import User, Favorite
from app.db.models.crawl import Horse


@pytest.mark.asyncio
async def test_insert_user(db_session: AsyncSession):
    user = User(email="test@example.com", password_hash="$2b$12$hashed")
    db_session.add(user)
    await db_session.flush()
    assert user.id is not None


@pytest.mark.asyncio
async def test_favorite_unique_constraint(db_session: AsyncSession):
    from sqlalchemy.exc import IntegrityError
    user = User(email="fav@example.com", password_hash="hash")
    horse = Horse(name="즐겨찾기마", sex="M")
    db_session.add_all([user, horse])
    await db_session.flush()

    fav1 = Favorite(user_id=user.id, horse_id=horse.id)
    fav2 = Favorite(user_id=user.id, horse_id=horse.id)
    db_session.add(fav1)
    await db_session.flush()
    db_session.add(fav2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
