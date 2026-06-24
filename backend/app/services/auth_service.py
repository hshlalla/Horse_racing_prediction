import datetime
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.core.config import settings
from app.db.models.users import User, Session


class EmailTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class InvalidRefreshToken(Exception):
    pass


async def register(db: AsyncSession, email: str, password: str) -> tuple[User, str, str]:
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise EmailTaken(email)
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    await db.flush()
    access_token, refresh_raw = await _issue_tokens(db, user)
    await db.commit()
    return user, access_token, refresh_raw


async def login(db: AsyncSession, email: str, password: str) -> tuple[User, str, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentials()
    access_token, refresh_raw = await _issue_tokens(db, user)
    await db.commit()
    return user, access_token, refresh_raw


async def refresh(db: AsyncSession, refresh_raw: str) -> tuple[str, str]:
    token_hash = hash_refresh_token(refresh_raw)
    result = await db.execute(
        select(Session).where(Session.refresh_token_hash == token_hash)
    )
    session = result.scalar_one_or_none()
    now = datetime.datetime.now(datetime.UTC)

    if session is None:
        raise InvalidRefreshToken("not found")

    if session.revoked_at is not None:
        # Reuse detected: revoke entire family
        await db.execute(
            update(Session)
            .where(Session.family_id == session.family_id)
            .values(revoked_at=now)
        )
        await db.commit()
        raise InvalidRefreshToken("token reuse detected")

    if session.expires_at.replace(tzinfo=datetime.UTC) < now:
        raise InvalidRefreshToken("expired")

    # Revoke old token
    session.revoked_at = now
    await db.flush()

    # Issue new tokens in same family
    result2 = await db.execute(select(User).where(User.id == session.user_id))
    user = result2.scalar_one()
    raw_new, hash_new = generate_refresh_token()
    new_session = Session(
        user_id=user.id,
        refresh_token_hash=hash_new,
        expires_at=now + datetime.timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        family_id=session.family_id,
    )
    db.add(new_session)
    access_token = create_access_token(user_id=user.id)
    await db.commit()
    return access_token, raw_new


async def logout(db: AsyncSession, refresh_raw: str) -> None:
    token_hash = hash_refresh_token(refresh_raw)
    result = await db.execute(
        select(Session).where(Session.refresh_token_hash == token_hash)
    )
    session = result.scalar_one_or_none()
    if session:
        session.revoked_at = datetime.datetime.now(datetime.UTC)
        await db.commit()


async def _issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    raw, hashed = generate_refresh_token()
    session = Session(
        user_id=user.id,
        refresh_token_hash=hashed,
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
        family_id=str(uuid.uuid4()),
    )
    db.add(session)
    await db.flush()
    return create_access_token(user_id=user.id), raw
