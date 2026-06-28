import numpy as np
import pandas as pd
from scipy.special import softmax


def _race_log_loss(model, val_df: pd.DataFrame, features: list, target: str) -> float:
    """Compute per-race softmax log-loss for a model on the val set."""
    df = val_df.copy()
    df['_score'] = model.predict(df[features])
    losses = []
    for _, race in df.groupby('race_id'):
        y_true = (race[target].values == 3).astype(int)
        if y_true.sum() == 0:
            continue
        probs = softmax(race['_score'].values)
        probs = np.clip(probs, 1e-7, 1 - 1e-7)
        # negative log probability of the winner
        winner_idx = int(np.argmax(y_true))
        losses.append(-np.log(probs[winner_idx]))
    return float(np.mean(losses)) if losses else 1.0


class EnsembleShim:
    def __init__(self, models: list, weights: list):
        self.models = models
        self.weights = weights  # list of floats summing to 1.0

    @property
    def feature_names_(self) -> list:
        """Return feature names from the first sub-model (LightGBM or CatBoost)."""
        for shim in self.models:
            m = getattr(shim, "m", shim)
            if hasattr(m, "feature_name_"):
                fn = m.feature_name_
                return list(fn() if callable(fn) else fn)  # LightGBM
            if hasattr(m, "feature_names_"):
                return list(m.feature_names_)   # CatBoost
        return []

    def predict(self, X: pd.DataFrame, race_ids=None) -> np.ndarray:
        """
        Return weighted blend of sub-model raw scores.

        If race_ids is provided the per-race softmax is applied to each
        sub-model's scores before blending; otherwise a global softmax is
        applied.  The final result is therefore a probability-like vector
        (values in (0, 1), summing to 1 per race when race_ids is given).
        """
        blended = np.zeros(len(X))

        for model, w in zip(self.models, self.weights):
            raw = model.predict(X)

            if race_ids is not None:
                probs = np.empty_like(raw, dtype=float)
                race_id_arr = np.asarray(race_ids)
                for rid in np.unique(race_id_arr):
                    mask = race_id_arr == rid
                    probs[mask] = softmax(raw[mask])
            else:
                probs = softmax(raw)

            blended += w * probs

        return blended


def build_ensemble(models: list, val_df: pd.DataFrame,
                   features: list, target: str) -> EnsembleShim:
    """
    Build a weighted ensemble of ModelShim objects.

    Weight for each model = 1 / val_log_loss, normalised to sum to 1.
    A lower validation log-loss → higher weight.
    """
    log_losses = [_race_log_loss(m, val_df, features, target) for m in models]
    inv_losses = [1.0 / max(ll, 1e-7) for ll in log_losses]
    total = sum(inv_losses)
    weights = [w / total for w in inv_losses]
    return EnsembleShim(models, weights)
