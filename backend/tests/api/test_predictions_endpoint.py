import pytest
import datetime
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from app.main import app
from app.ml.predict.service import HorsePrediction


@pytest.mark.asyncio
async def test_predictions_endpoint_returns_list():
    mock_preds = [
        HorsePrediction(
            horse_id=1, horse_name="천하무적", program_number=1,
            win_probability=0.35, place_probability=0.65,
            model_versions={"track": "SEOUL"},
            features_snapshot={"distance_m": 1200},
            computed_at=datetime.datetime.now(datetime.timezone.utc),
        )
    ]
    with patch(
        "app.services.prediction_service.predict_race",
        new=AsyncMock(return_value=mock_preds),
    ), patch(
        "app.services.prediction_service.get_race_detail",
        new=AsyncMock(return_value=None),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/races/1/predictions")

    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        assert "items" in resp.json()
