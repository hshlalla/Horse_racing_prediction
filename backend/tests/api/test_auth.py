import pytest
from fastapi import Request
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import create_app
from app.db.base import Base
from app.api import deps
from app.core import rate_limit


async def no_rate_limit(request: Request) -> None:
    """No-op rate limiter for tests."""
    pass


@pytest.fixture
async def client(engine):
    """HTTP client backed by a fresh test DB."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[rate_limit.auth_rate_limit] = no_rate_limit

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        yield c


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "rider@example.com",
        "password": "Secure123!"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data

    resp2 = await client.post("/api/v1/auth/login", json={
        "email": "rider@example.com",
        "password": "Secure123!"
    })
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "Pass1234!"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_TAKEN"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "pw@example.com", "password": "Correct1!"
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "pw@example.com", "password": "Wrong1!"
    })
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "ref@example.com", "password": "Token123!"
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "ref@example.com", "password": "Token123!"
    })
    # refresh token is in the httpOnly cookie
    assert "rt" in login_resp.cookies
    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()
