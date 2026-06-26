"""
Tests for backend/app/ml/train/promote.py
"""

import json
import pickle
import pytest
import numpy as np
from pathlib import Path

from app.ml.train.promote import promote_if_better, get_production_metrics, load_production_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeModel:
    """Minimal model stub that satisfies pickle and predict contracts."""

    def predict(self, X, race_ids=None):
        return np.zeros(len(X))


# ---------------------------------------------------------------------------
# Core promotion tests (from the brief)
# ---------------------------------------------------------------------------

def test_first_promotion_always_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    result = promote_if_better(
        "SEOUL", model, val_log_loss=0.8, val_roi=0.05,
        model_path=str(tmp_path / "model_v1.pkl"),
    )
    assert result is True
    metrics = get_production_metrics("SEOUL")
    assert metrics is not None
    assert metrics["log_loss"] == 0.8


def test_better_model_replaces_production(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better(
        "SEOUL", model, val_log_loss=0.8, val_roi=0.05,
        model_path=str(tmp_path / "model_v1.pkl"),
    )
    result = promote_if_better(
        "SEOUL", model, val_log_loss=0.7, val_roi=0.10,
        model_path=str(tmp_path / "model_v2.pkl"),
    )
    assert result is True
    assert get_production_metrics("SEOUL")["log_loss"] == 0.7


def test_worse_model_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better(
        "SEOUL", model, val_log_loss=0.7, val_roi=0.10,
        model_path=str(tmp_path / "model_v1.pkl"),
    )
    result = promote_if_better(
        "SEOUL", model, val_log_loss=0.9, val_roi=-0.05,
        model_path=str(tmp_path / "model_v2.pkl"),
    )
    assert result is False
    assert get_production_metrics("SEOUL")["log_loss"] == 0.7


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

def test_negative_roi_blocks_promotion_even_if_lower_loss(tmp_path, monkeypatch):
    """A model with strictly lower log-loss must still be rejected if ROI < 0."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better(
        "BUSAN", model, val_log_loss=0.7, val_roi=0.05,
        model_path=str(tmp_path / "model_v1.pkl"),
    )
    result = promote_if_better(
        "BUSAN", model, val_log_loss=0.5, val_roi=-0.01,
        model_path=str(tmp_path / "model_v2.pkl"),
    )
    assert result is False
    assert get_production_metrics("BUSAN")["log_loss"] == 0.7


def test_equal_log_loss_is_rejected(tmp_path, monkeypatch):
    """Strictly better means strictly less; equal loss must be rejected."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better(
        "SEOUL", model, val_log_loss=0.7, val_roi=0.05,
        model_path=str(tmp_path / "model_v1.pkl"),
    )
    result = promote_if_better(
        "SEOUL", model, val_log_loss=0.7, val_roi=0.10,
        model_path=str(tmp_path / "model_v2.pkl"),
    )
    assert result is False


def test_zero_roi_is_accepted(tmp_path, monkeypatch):
    """ROI == 0 satisfies the non-negative constraint."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better(
        "SEOUL", model, val_log_loss=0.8, val_roi=0.05,
        model_path=str(tmp_path / "model_v1.pkl"),
    )
    result = promote_if_better(
        "SEOUL", model, val_log_loss=0.6, val_roi=0.0,
        model_path=str(tmp_path / "model_v2.pkl"),
    )
    assert result is True
    assert get_production_metrics("SEOUL")["log_loss"] == 0.6


def test_first_promotion_with_negative_roi(tmp_path, monkeypatch):
    """First promotion is unconditional — even negative ROI should succeed."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    result = promote_if_better(
        "JEJU", model, val_log_loss=0.9, val_roi=-0.5,
        model_path=str(tmp_path / "model_v1.pkl"),
    )
    assert result is True


def test_multiple_tracks_independent(tmp_path, monkeypatch):
    """Each track has an independent production.json entry."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better(
        "SEOUL", model, val_log_loss=0.7, val_roi=0.05,
        model_path=str(tmp_path / "seoul_v1.pkl"),
    )
    promote_if_better(
        "BUSAN", model, val_log_loss=0.9, val_roi=0.02,
        model_path=str(tmp_path / "busan_v1.pkl"),
    )
    # Improve BUSAN without touching SEOUL
    promote_if_better(
        "BUSAN", model, val_log_loss=0.8, val_roi=0.03,
        model_path=str(tmp_path / "busan_v2.pkl"),
    )
    assert get_production_metrics("SEOUL")["log_loss"] == 0.7
    assert get_production_metrics("BUSAN")["log_loss"] == 0.8


def test_production_json_schema(tmp_path, monkeypatch):
    """production.json must contain expected keys."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better(
        "SEOUL", model, val_log_loss=0.75, val_roi=0.03,
        model_path=str(tmp_path / "model_v1.pkl"),
    )
    with open(tmp_path / "production.json") as f:
        data = json.load(f)
    entry = data["SEOUL"]
    for key in ("model_path", "log_loss", "roi", "version", "promoted_at"):
        assert key in entry, f"Missing key: {key}"


def test_load_production_model_roundtrip(tmp_path, monkeypatch):
    """load_production_model must return the same pickled object."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better(
        "SEOUL", model, val_log_loss=0.75, val_roi=0.03,
        model_path=str(tmp_path / "model_v1.pkl"),
    )
    loaded = load_production_model("SEOUL")
    # Same class, same behaviour.
    assert isinstance(loaded, FakeModel)
    assert list(loaded.predict(np.zeros((3, 1)))) == [0.0, 0.0, 0.0]


def test_load_production_model_missing_raises(tmp_path, monkeypatch):
    """load_production_model raises FileNotFoundError for unknown track."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        load_production_model("UNKNOWN_TRACK")


def test_get_production_metrics_no_file(tmp_path, monkeypatch):
    """get_production_metrics returns None when no production.json exists."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    assert get_production_metrics("SEOUL") is None
