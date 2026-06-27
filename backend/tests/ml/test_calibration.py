import numpy as np
import pytest
from app.ml.predict.calibration import fit_calibration, apply_calibration


class _FakeModel:
    """Minimal model stub used for pickle round-trip test."""

    calibrator = None

    def predict(self, X):
        return np.ones(len(X))


def test_calibration_output_sums_to_one():
    raw = np.array([0.6, 0.3, 0.1])
    y = np.array([1, 0, 0])
    cal = fit_calibration(raw, y)
    out = apply_calibration(raw, cal)
    assert abs(out.sum() - 1.0) < 1e-6


def test_calibration_preserves_ranking():
    raw = np.array([0.7, 0.2, 0.1])
    y = np.array([1, 0, 0])
    cal = fit_calibration(raw, y)
    out = apply_calibration(raw, cal)
    assert out[0] > out[1] > out[2]


def test_calibration_clips_out_of_bounds():
    raw = np.array([1.5, -0.1, 0.5])
    y = np.array([1, 0, 0])
    cal = fit_calibration(raw, y)
    out = apply_calibration(raw, cal)
    assert (out >= 0).all()
    assert (out <= 1).all()


def test_calibrator_round_trips_through_pickle():
    """Calibrator attached to a model survives pickle serialize/deserialize."""
    import pickle

    raw = np.array([0.7, 0.2, 0.1])
    y = np.array([1, 0, 0])
    cal = fit_calibration(raw, y)

    m = _FakeModel()
    m.calibrator = cal

    m2 = pickle.loads(pickle.dumps(m))
    assert m2.calibrator is not None
    out = apply_calibration(raw, m2.calibrator)
    assert abs(out.sum() - 1.0) < 1e-6
