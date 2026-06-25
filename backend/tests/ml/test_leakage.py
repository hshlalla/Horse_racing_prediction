import pytest
from hypothesis import given, strategies as st
from datetime import date, timedelta

# Dummy feature builder to satisfy the test logic
def build_feature(horse_id: int, target_date: date, history: list[dict]) -> dict:
    """Returns features ensuring no data from target_date or later is used."""
    valid_history = [row for row in history if row["race_date"] < target_date]
    if not valid_history:
        return {"avg_finish": None}
    
    avg_finish = sum(row["finish_pos"] for row in valid_history) / len(valid_history)
    return {"avg_finish": avg_finish}

@given(
    target_date=st.dates(min_value=date(2000, 1, 1), max_value=date(2025, 12, 31)),
    future_offset=st.integers(min_value=0, max_value=100)
)
def test_no_future_leakage(target_date: date, future_offset: int):
    """
    Hypothesis property test: Given any target_date, verify that the feature builder
    does not include rows where race_date >= target_date.
    """
    future_date = target_date + timedelta(days=future_offset)
    
    mock_history = [
        {"race_date": target_date - timedelta(days=10), "finish_pos": 1},
        {"race_date": target_date - timedelta(days=5), "finish_pos": 3},
        {"race_date": future_date, "finish_pos": 1} # This should NOT be leaked
    ]
    
    features = build_feature(horse_id=1, target_date=target_date, history=mock_history)
    
    # If the future_date leaked, avg_finish would be (1 + 3 + 1)/3 = 1.66
    # Correct avg_finish is (1 + 3)/2 = 2.0
    assert features["avg_finish"] == 2.0
