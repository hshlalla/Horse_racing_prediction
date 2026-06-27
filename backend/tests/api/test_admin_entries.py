import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_crawl_entries_endpoint_returns_ok():
    """POST /admin/crawl/entries accepts request and returns ok immediately."""
    with patch(
        "app.api.v1.admin.crawl_entries",
        new=AsyncMock(return_value={"races_upserted": 3, "entries_upserted": 45, "errors": []}),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/admin/crawl/entries",
                json={"date": "2026-06-28", "tracks": ["SEOUL"]},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["date"] == "2026-06-28"
    assert body["tracks"] == ["SEOUL"]


@pytest.mark.asyncio
async def test_crawl_entries_defaults_all_tracks():
    """When tracks omitted, response contains all three tracks."""
    with patch(
        "app.api.v1.admin.crawl_entries",
        new=AsyncMock(return_value={"races_upserted": 0, "entries_upserted": 0, "errors": []}),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/admin/crawl/entries",
                json={"date": "2026-06-28"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["tracks"]) == {"SEOUL", "BUSAN", "JEJU"}
