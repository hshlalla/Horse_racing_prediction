"""
Isotonic regression probability calibration for the prediction service.

Maps raw model scores (softmax probabilities) to calibrated probabilities
that better reflect true win likelihoods, then renormalises per race to sum to 1.
"""

import numpy as np
from sklearn.isotonic import IsotonicRegression


def fit_calibration(raw_probs: np.ndarray, y_binary: np.ndarray) -> IsotonicRegression:
    """
    Fit an isotonic regression calibrator on raw model probabilities.

    Parameters
    ----------
    raw_probs : 1D array of raw softmax probabilities from the model.
    y_binary  : 1D binary array, 1 if horse won, 0 otherwise.

    Returns
    -------
    Fitted IsotonicRegression instance.
    """
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_probs, y_binary)
    return calibrator


def apply_calibration(raw_probs: np.ndarray, calibrator) -> np.ndarray:
    """
    Apply calibration and renormalise so probabilities sum to 1.

    Parameters
    ----------
    raw_probs  : 1D array of raw softmax probabilities for all horses in one race.
    calibrator : Fitted IsotonicRegression instance from fit_calibration().

    Returns
    -------
    1D array of calibrated, renormalised probabilities summing to 1.

    Notes
    -----
    Isotonic regression is monotone non-decreasing, so horses with equal
    target labels map to the same calibrated value.  To preserve original
    ordering as a tiebreaker (important for downstream ranking), a tiny
    perturbation proportional to raw_probs is added before renormalisation.
    The perturbation is scaled to at most 1e-6 × the minimum non-zero
    calibrated value so it cannot materially change the calibration.
    """
    calibrated = calibrator.predict(raw_probs)
    calibrated = np.clip(calibrated, 1e-7, 1.0)

    # Break ties by adding a negligible nudge proportional to original scores.
    # Scale so the nudge is never more than 1e-6 of the smallest calibrated value.
    min_val = calibrated.min()
    nudge_scale = min_val * 1e-6 / (raw_probs.max() - raw_probs.min() + 1e-12)
    calibrated = calibrated + nudge_scale * raw_probs

    total = calibrated.sum()
    if total > 0:
        calibrated = calibrated / total
    else:
        calibrated = np.ones(len(calibrated)) / len(calibrated)
    return calibrated
