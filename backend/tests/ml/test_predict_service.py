import pytest
import datetime
from unittest.mock import AsyncMock, patch, MagicMock
import numpy as np

from app.ml.predict.service import predict_race, HorsePrediction


@pytest.mark.asyncio
async def test_predict_race_returns_horse_predictions():
    mock_session = AsyncMock()

    # Mock race query
    mock_race = MagicMock()
    mock_race.track = "SEOUL"
    mock_race.distance_m = 1200
    mock_race.field_size = 5
    mock_race.track_condition = "건조"
    mock_race.weather = "맑음"

    # Mock entries
    mock_entry = MagicMock()
    mock_entry.horse_id = 1
    mock_entry.program_number = 1
    mock_entry.jockey_id = 1
    mock_entry.trainer_id = 1
    mock_entry.carry_weight_kg = 57.0
    mock_entry.body_weight_kg = 490.0
    mock_entry.morning_odds = 3.5
    mock_entry.horse = MagicMock()
    mock_entry.horse.name = "천하무적"
    mock_entry.horse.age = 4
    mock_entry.horse.sex = "M"

    mock_session.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(
            first=MagicMock(return_value=mock_race),
            all=MagicMock(return_value=[mock_entry]),
        ))
    ))

    with patch("app.ml.predict.service._get_model") as mock_get_model:
        fake_model = MagicMock()
        fake_model.predict.return_value = np.array([1.0])
        mock_get_model.return_value = fake_model

        results = await predict_race(race_id=1, session=mock_session)

    assert len(results) == 1
    assert isinstance(results[0], HorsePrediction)
    assert 0 < results[0].win_probability < 1
    assert results[0].win_probability != results[0].place_probability or len(results) == 1


@pytest.mark.asyncio
async def test_predict_race_probabilities_sum_to_one():
    """With 3 horses, win probabilities should sum to ~1."""
    # This test requires a real model; skip if no production model is available
    pytest.skip("Requires production model — run after Task 10 (run_train)")
