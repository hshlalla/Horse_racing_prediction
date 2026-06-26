import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.prediction_service import get_race_predictions
from app.ml.predict.service import HorsePrediction
import datetime


@pytest.mark.asyncio
async def test_predictions_endpoint_returns_list():
    """Test that get_race_predictions properly calls predict_race with db and race_id."""
    mock_preds = [
        HorsePrediction(
            horse_id=1, horse_name="천하무적", program_number=1,
            win_probability=0.35, place_probability=0.65,
            model_versions={"track": "SEOUL"},
            features_snapshot={"distance_m": 1200},
            computed_at=datetime.datetime.now(datetime.timezone.utc),
        )
    ]

    # Mock the dependencies
    mock_db = MagicMock()

    # Patch get_race_detail and predict_race
    with patch("app.services.prediction_service.get_race_detail",
               new=AsyncMock(return_value={"id": 1, "track": "SEOUL"})):
        with patch("app.services.prediction_service.predict_race",
                   new=AsyncMock(return_value=mock_preds)) as mock_predict:
            result = await get_race_predictions(mock_db, 1)

    # Verify predict_race was called with correct arguments
    mock_predict.assert_called_once_with(mock_db, 1)

    # Verify the result
    assert result == mock_preds
    assert len(result) == 1
    assert result[0].horse_name == "천하무적"
    assert result[0].win_probability == 0.35
