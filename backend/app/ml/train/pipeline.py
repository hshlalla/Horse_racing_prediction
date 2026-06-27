"""
Full training pipeline for one track.

Trains LightGBM + CatBoost, builds a weighted ensemble, evaluates it, and
promotes it to production if it beats the current champion.
"""

import datetime
import logging
import os
from pathlib import Path

import numpy as np
from scipy.special import softmax as _softmax

from app.ml.train.dataset import load_dataset_pg
from app.ml.train.models.lgbm_binary import train_lgbm
from app.ml.train.models.catboost_binary import train_catboost
from app.ml.train.models.ensemble import build_ensemble, _race_log_loss
from app.ml.train.promote import promote_if_better, compute_kelly_roi, _model_dir
from app.ml.predict.calibration import fit_calibration

logger = logging.getLogger(__name__)


def run_train(track: str, db_url: str) -> dict:
    """
    Full training pipeline for one track.

    Steps
    -----
    1. Load dataset from Postgres (all tracks).
    2. Filter train/val DataFrames to *track* (fall back to all-track data when
       fewer than 100 track-specific rows exist).
    3. Train LightGBM and CatBoost models independently.
    4. Build a weighted ensemble from the two models.
    5. Evaluate: val log-loss + Kelly ROI.
    6. Save the ensemble artifact to ``models/{track}/v{timestamp}.pkl``.
    7. Promote if the new model beats the current production champion.

    Parameters
    ----------
    track:
        One of ``"SEOUL"``, ``"BUSAN"``, ``"JEJU"``.
    db_url:
        SQLAlchemy-compatible database URL, e.g.
        ``postgresql+psycopg2://user:pw@host/db``.

    Returns
    -------
    ``{"track": str, "val_log_loss": float, "val_roi": float, "promoted": bool}``
    """
    logger.info("Starting training for track %s", track)

    train_df, val_df, _test_df, features, target = load_dataset_pg(db_url)

    # Filter to track when enough data is available.
    track_train_mask = train_df["track"] == track
    if track_train_mask.sum() > 100:
        track_train = train_df[track_train_mask].copy()
        track_val = val_df[val_df["track"] == track].copy()
    else:
        logger.warning(
            "Only %d rows for track %s in train set — using all tracks",
            track_train_mask.sum(),
            track,
        )
        track_train = train_df
        track_val = val_df

    if len(track_train) < 50:
        logger.warning(
            "Not enough data for %s (%d rows) — skipping",
            track,
            len(track_train),
        )
        return {"track": track, "val_log_loss": 999.0, "val_roi": -1.0, "promoted": False}

    # Train individual models.
    logger.info("[%s] Training LightGBM model", track)
    model_lgbm = train_lgbm(track_train, track_val, features, target)

    logger.info("[%s] Training CatBoost model", track)
    model_catboost = train_catboost(track_train, track_val, features, target)

    # Build ensemble (weights are inverse-log-loss of each sub-model).
    logger.info("[%s] Building ensemble", track)
    ensemble = build_ensemble([model_lgbm, model_catboost], track_val, features, target)

    # Fit isotonic calibrator on val set softmax probabilities.
    _val_probs: list = []
    _val_wins: list = []
    for _, _race in track_val.groupby("race_id"):
        _scores = ensemble.predict(_race[features])
        _p = _softmax(_scores)
        _val_probs.extend(_p.tolist())
        _val_wins.extend(
            (_race["finish_position"] == 1).astype(int).tolist()
        )

    if len(set(_val_wins)) == 2:  # need both classes to fit isotonic
        ensemble.calibrator = fit_calibration(
            np.array(_val_probs), np.array(_val_wins)
        )
    else:
        ensemble.calibrator = None

    # Run SHAP feature importance analysis using the LightGBM model
    try:
        from app.ml.train.shap_analysis import run_shap_analysis
        # Pass the raw LGBMRanker model (.m) instead of the ModelShim wrapper
        shap_result = run_shap_analysis(
            model_lgbm.m, track_val, features,
            output_dir=str(_model_dir() / track)
        )
        if shap_result["drop_candidates"]:
            logger.info(
                "[%s] SHAP drop candidates: %s",
                track, shap_result["drop_candidates"]
            )
        ensemble.shap_importance = shap_result.get("importance", {})
    except Exception as exc:
        logger.warning("[%s] SHAP analysis skipped: %s", track, exc)

    # Evaluate.
    val_log_loss = _race_log_loss(ensemble, track_val, features, target)
    val_roi = compute_kelly_roi(ensemble, track_val, features)

    # Persist the ensemble artifact.
    model_dir = _model_dir() / track
    model_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    model_path = str(model_dir / f"v{ts}.pkl")

    promoted = promote_if_better(
        track,
        ensemble,
        val_log_loss=val_log_loss,
        val_roi=val_roi,
        model_path=model_path,
    )

    logger.info(
        "[%s] Training done: val_log_loss=%.4f, val_roi=%.4f, promoted=%s",
        track,
        val_log_loss,
        val_roi,
        promoted,
    )
    return {
        "track": track,
        "val_log_loss": val_log_loss,
        "val_roi": val_roi,
        "promoted": promoted,
    }
