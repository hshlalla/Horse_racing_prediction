"""Tests for admin API endpoints."""
import datetime
import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import create_app
from app.api import deps


# ---------------------------------------------------------------------------
# Shared fixture: HTTP client with a mocked DB session
# ---------------------------------------------------------------------------

def _make_mock_db():
    """Return an AsyncSession-like mock that satisfies the data/status queries."""

    async def _scalar_zero(*args, **kwargs):
        return 0

    async def _scalar_none(*args, **kwargs):
        return None

    async def _scalars_empty(*args, **kwargs):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result

    # execute always returns an object whose .scalar() / .scalars().all() work
    execute_result = MagicMock()
    execute_result.scalar.return_value = 0
    execute_result.scalars.return_value.all.return_value = []

    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock(return_value=execute_result)
    return db


@pytest_asyncio.fixture
async def admin_client():
    """HTTP client with DB dependency overridden by an empty mock session."""
    mock_db = _make_mock_db()

    async def override_get_db():
        yield mock_db

    application = create_app()
    application.dependency_overrides[deps.get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# /api/v1/admin/ml/status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_ml_status_returns_json():
    """GET /admin/ml/status returns expected JSON shape even without models dir."""
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/ml/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "tracks" in body
    assert "last_updated" in body


@pytest.mark.asyncio
async def test_admin_ml_status_reads_production_json(tmp_path):
    """GET /admin/ml/status returns track data from production.json when present."""
    prod = {
        "SEOUL": {
            "version": "v20260601_120000",
            "log_loss": 0.42,
            "roi": 0.05,
            "promoted_at": "2026-06-01T12:00:00",
        }
    }
    (tmp_path / "production.json").write_text(json.dumps(prod))

    application = create_app()
    with patch.dict("os.environ", {"MODEL_DIR": str(tmp_path)}):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            resp = await client.get("/api/v1/admin/ml/status")

    assert resp.status_code == 200
    body = resp.json()
    seoul = next(t for t in body["tracks"] if t["track"] == "SEOUL")
    assert seoul["model_version"] == "v20260601_120000"
    assert seoul["log_loss"] == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# /api/v1/admin/data/status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_data_status_returns_json(admin_client: AsyncClient):
    """GET /admin/data/status returns expected JSON shape with empty DB."""
    resp = await admin_client.get("/api/v1/admin/data/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "crawl_states" in body
    assert "failures" in body
    assert "db_summary" in body


@pytest.mark.asyncio
async def test_admin_data_status_db_summary_fields(admin_client: AsyncClient):
    """db_summary contains the required count fields."""
    resp = await admin_client.get("/api/v1/admin/data/status")
    assert resp.status_code == 200
    summary = resp.json()["db_summary"]
    assert "total_races" in summary
    assert "total_horses" in summary
    assert "total_jockeys" in summary


@pytest.mark.asyncio
async def test_admin_data_status_crawl_states_includes_all_tracks(admin_client: AsyncClient):
    """crawl_states always includes SEOUL, BUSAN, and JEJU even with empty DB."""
    resp = await admin_client.get("/api/v1/admin/data/status")
    assert resp.status_code == 200
    state_tracks = {s["track"] for s in resp.json()["crawl_states"]}
    assert {"SEOUL", "BUSAN", "JEJU"}.issubset(state_tracks)


# ---------------------------------------------------------------------------
# /api/v1/admin/data/retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_data_retry_invalid_date():
    """POST /admin/data/retry with a non-date string returns 422."""
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/admin/data/retry",
            json={"track": "SEOUL", "date": "not-a-date"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_data_retry_queues_background_task():
    """POST /admin/data/retry with a valid payload returns 200 with ok=True."""
    application = create_app()
    with patch("app.ml.crawl.pipeline.run_crawl", new=AsyncMock(return_value={})):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/admin/data/retry",
                json={"track": "BUSAN", "date": "2026-06-20"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["track"] == "BUSAN"
    assert body["date"] == "2026-06-20"
