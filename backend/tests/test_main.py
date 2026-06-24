import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_healthz(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_returns_200_without_real_db(app, monkeypatch):
    # Patch the DB check so the test doesn't need a real Postgres
    import app.main as main_module
    async def _fake_check():
        return {"db": "ok", "redis": "ok"}
    monkeypatch.setattr(main_module, "_readyz_check", _fake_check)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["db"] == "ok"
