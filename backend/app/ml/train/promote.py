"""
Model promotion logic.

Writes a production.json pointer file and only promotes a new model if it
strictly improves on validation log-loss AND passes a non-negative Kelly ROI
backtest.
"""

import json
import os
import pickle
import datetime
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _model_dir() -> Path:
    base = os.environ.get("MODEL_DIR", "models")
    return Path(base)


def _production_json_path() -> Path:
    return _model_dir() / "production.json"


def get_production_metrics(track: str) -> Optional[dict]:
    """Return current production model metrics for a track, or None."""
    path = _production_json_path()
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return data.get(track)


def promote_if_better(
    track: str,
    model,
    val_log_loss: float,
    val_roi: float,
    model_path: str,
) -> bool:
    """
    Promote *model* to production if it strictly beats the current champion.

    Promotion rules
    ---------------
    - First model for a track: always promoted.
    - Subsequent models: new ``val_log_loss`` must be **strictly less** than
      the current production log-loss AND ``val_roi >= 0``.

    Side effects
    ------------
    - Pickles *model* to *model_path*.
    - Updates ``production.json`` (keyed by track) with the new metrics.

    Returns
    -------
    ``True`` if the model was promoted, ``False`` if it was rejected.
    """
    current = get_production_metrics(track)

    if current is not None:
        if val_log_loss >= current["log_loss"] or val_roi < 0:
            logger.info(
                "[%s] Rejected: log_loss %.4f vs %.4f, roi %.4f",
                track,
                val_log_loss,
                current["log_loss"],
                val_roi,
            )
            return False

    # Persist the model artifact.
    _model_dir().mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    # Update production.json.
    production_path = _production_json_path()
    data: dict = {}
    if production_path.exists():
        with open(production_path) as f:
            data = json.load(f)

    now = datetime.datetime.utcnow()
    data[track] = {
        "model_path": str(model_path),
        "log_loss": val_log_loss,
        "roi": val_roi,
        "version": now.strftime("%Y%m%d_%H%M%S"),
        "promoted_at": now.isoformat(),
    }
    with open(production_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(
        "[%s] Promoted: log_loss %.4f, roi %.4f",
        track,
        val_log_loss,
        val_roi,
    )
    return True


def load_production_model(track: str):
    """Load and return the pickled production model for *track*."""
    metrics = get_production_metrics(track)
    if metrics is None:
        raise FileNotFoundError(f"No production model registered for track '{track}'")
    model_path = metrics["model_path"]
    with open(model_path, "rb") as f:
        return pickle.load(f)


# ---------------------------------------------------------------------------
# Kelly ROI backtest helpers (inline; do NOT import from experiment_ranker)
# ---------------------------------------------------------------------------

def _fractional_kelly(p_win: float, odds_win: float, fraction: float = 0.1) -> float:
    """Return the fractional-Kelly bet size (capped at *fraction*)."""
    b_win = odds_win - 1.0
    q_win = 1.0 - p_win
    if b_win <= 0:
        return 0.0
    kelly_f = (p_win * b_win - q_win) / b_win
    return max(0.0, min(fraction, kelly_f * fraction))


def compute_kelly_roi(model, val_df, features: list) -> float:
    """
    Simulate Kelly betting on the validation set and return the ROI.

    Parameters
    ----------
    model:
        Any object with a ``.predict(X, race_ids=...)`` method (e.g.
        ``EnsembleShim``).
    val_df:
        Validation DataFrame with at least ``race_id``, ``morning_odds``, and
        ``finish_position`` columns.
    features:
        Feature column names passed to ``model.predict``.

    Returns
    -------
    ROI as a float: ``(final_bankroll - 1_000_000) / 1_000_000``.
    """
    import numpy as np

    df = val_df.copy()
    race_ids = df["race_id"]

    # Obtain probabilities from the model.
    probs = model.predict(df[features], race_ids=race_ids)
    df["_prob"] = probs

    bankroll = 1_000_000.0

    for _race_id, group in df.groupby("race_id"):
        odds_vals = group["morning_odds"].values
        prob_vals = group["_prob"].values

        best_idx = -1
        best_f = 0.0
        for i in range(len(prob_vals)):
            f = _fractional_kelly(prob_vals[i], odds_vals[i])
            if f > best_f:
                best_f = f
                best_idx = i

        if best_idx == -1:
            continue

        # Identify the winner (finish_position == 1).
        finish = group["finish_position"].values
        bet_amount = bankroll * best_f
        bankroll -= bet_amount

        winner_mask = finish == 1
        winner_indices = np.where(winner_mask)[0]
        if len(winner_indices) > 0 and best_idx == winner_indices[0]:
            bankroll += bet_amount * odds_vals[best_idx]

    return (bankroll - 1_000_000.0) / 1_000_000.0
