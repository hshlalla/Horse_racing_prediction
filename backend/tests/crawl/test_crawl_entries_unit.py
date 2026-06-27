import pytest
import datetime
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_crawl_entries_upserts_races_and_entries():
    """crawl_entries stores race and entry rows given mocked HTTP."""
    from app.ml.crawl.crawl_entries import crawl_entries

    fake_races = [1, 2]
    fake_entries = [
        {
            "horse_no": 1,
            "horse_name": "천하무적",
            "sex": "수",
            "age": 4,
            "jockey": "김철수",
            "trainer": "이영희",
            "carry_weight": 57.0,
            "weight": 490.0,
            "morning_odds": 3.5,
        }
    ]
    fake_meta = {"distance_m": 1200, "surface": "Dirt", "track_condition": "건조"}

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.ml.crawl.crawl_entries._fetch_race_list", new=AsyncMock(return_value=fake_races)), \
         patch("app.ml.crawl.crawl_entries._fetch_race_entries", new=AsyncMock(return_value=fake_entries)), \
         patch("app.ml.crawl.crawl_entries._fetch_race_meta", new=AsyncMock(return_value=fake_meta)), \
         patch("app.ml.crawl.crawl_entries.upsert_horse", new=AsyncMock(return_value=1)), \
         patch("app.ml.crawl.crawl_entries.upsert_jockey", new=AsyncMock(return_value=1)), \
         patch("app.ml.crawl.crawl_entries.upsert_trainer", new=AsyncMock(return_value=1)), \
         patch("app.ml.crawl.crawl_entries.upsert_race", new=AsyncMock(return_value=1)), \
         patch("app.ml.crawl.crawl_entries.upsert_race_entry", new=AsyncMock()):

        result = await crawl_entries(
            target_date=datetime.date(2026, 6, 28),
            tracks=["SEOUL"],
            session=mock_session,
        )

    assert result["races_upserted"] == 2
    assert result["entries_upserted"] == 2
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_crawl_entries_empty_race_list_returns_zeros():
    """When no races found for a date, return zero counts and no errors."""
    from app.ml.crawl.crawl_entries import crawl_entries

    mock_session = AsyncMock()
    with patch("app.ml.crawl.crawl_entries._fetch_race_list", new=AsyncMock(return_value=[])):
        result = await crawl_entries(
            target_date=datetime.date(2026, 6, 28),
            tracks=["SEOUL"],
            session=mock_session,
        )

    assert result["races_upserted"] == 0
    assert result["entries_upserted"] == 0
    assert result["errors"] == []
