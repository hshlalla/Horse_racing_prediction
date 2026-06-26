import pytest
import datetime
from unittest.mock import AsyncMock, patch
from app.ml.crawl.pipeline import run_crawl

@pytest.mark.asyncio
async def test_run_crawl_returns_summary():
    with patch("app.ml.crawl.pipeline.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("app.ml.crawl.pipeline.KRALiveParser") as mock_parser:
            mock_parser.parse_chulma_list.return_value = []
            result = await run_crawl(
                datetime.date(2026, 6, 21),
                datetime.date(2026, 6, 21),
                use_synthetic_fallback=False,
            )
    assert "races_upserted" in result
    assert "failures" in result
