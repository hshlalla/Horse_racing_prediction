import pandas as pd
import numpy as np
import pytest
from app.ml.train.dataset import _apply_features


@pytest.fixture
def raw_df():
    """Minimal raw DataFrame mimicking _QUERY output."""
    return pd.DataFrame({
        "race_id":       [1, 1, 2, 2],
        "race_date":     pd.to_datetime(["2024-01-01"] * 4),
        "horse_id":      [10, 20, 10, 20],
        "jockey_id":     [1, 2, 1, 2],
        "trainer_id":    [1, 2, 1, 2],
        "sire_id":       [None, None, None, None],
        "program_number":[1, 2, 1, 2],
        "distance_m":    [1200, 1200, 1400, 1400],
        "field_size":    [2, 2, 2, 2],
        "track":         ["SEOUL"] * 4,
        "surface":       ["Dirt", "Turf", "Dirt", "Turf"],
        "grade":         ["G3", None, "G3", None],
        "track_condition":["건조"] * 4,
        "weather":       ["맑음"] * 4,
        "humidity":      [50] * 4,
        "carry_weight_kg":[57.0] * 4,
        "body_weight_kg": [490.0, 510.0, 495.0, 505.0],
        "morning_odds":  [3.5, 2.0, 4.0, 1.8],
        "horse_age":     [4] * 4,
        "horse_sex":     ["M"] * 4,
        "s1f_time":      [14.0] * 4,
        "g3f_time":      [38.0] * 4,
        "corner1_rank":  [1, 2, 2, 1],
        "corner2_rank":  [None] * 4,
        "corner3_rank":  [None] * 4,
        "corner4_rank":  [None] * 4,
        "corner5_rank":  [None] * 4,
        "corner6_rank":  [None] * 4,
        "corner7_rank":  [None] * 4,
        "finish_position":[1, 2, 2, 1],
        "finish_time_s": [72.0, 72.5, 84.0, 83.5],
        "is_win":        [1, 0, 0, 1],
    })


def test_surface_is_categorical(raw_df):
    df = _apply_features(raw_df.copy())
    assert df["surface"].dtype.name == "category"
    assert set(df["surface"].cat.categories) >= {"Dirt", "Turf"}


def test_grade_filled_and_categorical(raw_df):
    df = _apply_features(raw_df.copy())
    assert df["grade"].dtype.name == "category"
    assert df["grade"].isna().sum() == 0   # nulls filled with 'unknown'


def test_body_weight_delta_first_race_is_zero(raw_df):
    df = _apply_features(raw_df.copy())
    # Horse 10 and 20 both appear first in race 1 — delta should be 0
    first_race = df[df["race_id"] == 1]
    assert (first_race["body_weight_delta_kg"] == 0.0).all()


def test_body_weight_delta_second_race(raw_df):
    df = _apply_features(raw_df.copy())
    # Horse 10: race1=490, race2=495 → delta=+5
    horse10_r2 = df[(df["horse_id"] == 10) & (df["race_id"] == 2)]
    assert abs(horse10_r2["body_weight_delta_kg"].values[0] - 5.0) < 1e-6


def test_morning_odds_rank_within_race(raw_df):
    df = _apply_features(raw_df.copy())
    race1 = df[df["race_id"] == 1].sort_values("program_number")
    # race1: horse10 odds=3.5, horse20 odds=2.0 → horse20 rank=1, horse10 rank=2
    assert race1[race1["horse_id"] == 20]["morning_odds_rank"].values[0] == 1
    assert race1[race1["horse_id"] == 10]["morning_odds_rank"].values[0] == 2
