import numpy as np
import pandas as pd
from scipy.special import softmax


def _race_log_loss(model, val_df: pd.DataFrame, features: list, target: str) -> float:
    """Compute per-race softmax log-loss for a model on the val set.

    Passes race_ids to models that support it (EnsembleShim) so the blend uses
    its per-race softmax path. Without this, EnsembleShim.predict applies a
    GLOBAL softmax that squashes all scores to ~1/N near-equal values; the
    subsequent per-race softmax of those then collapses to a uniform
    distribution, making the metric a constant ≈ ln(field_size) regardless of
    the model. Individual ModelShims don't accept race_ids (TypeError → raw).
    """
    df = val_df.copy()
    try:
        df['_score'] = model.predict(df[features], race_ids=df['race_id'])
    except TypeError:
        df['_score'] = model.predict(df[features])
    losses = []
    for _, race in df.groupby('race_id'):
        y_true = (race[target].values == 3).astype(int)
        if y_true.sum() == 0:
            continue
        s = race['_score'].values
        # Ensemble (with race_ids) already returns a per-race probability
        # distribution (≥0, sums to 1) — use it directly. Raw model scores
        # (individual ModelShims) need a softmax to become probabilities.
        if np.all(s >= 0) and abs(float(s.sum()) - 1.0) < 1e-3:
            probs = s
        else:
            probs = softmax(s)
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

    Weight ∝ the model's *skill above the uniform baseline*
    (``baseline_log_loss - val_log_loss``), not ``1/log_loss``. Near uniform
    (≈ ln(field_size)) two models can have similar ``1/loss`` even when one has
    almost no skill and the other a lot — inverse-loss weighting then dilutes
    the strong model. Skill-above-baseline gives a near-useless model near-zero
    weight. Models at/below baseline get a tiny floor weight.
    """
    log_losses = [_race_log_loss(m, val_df, features, target) for m in models]

    # Uniform-prediction baseline: mean ln(field_size) over scored races.
    field_sizes = val_df.groupby('race_id').size()
    baseline = float(np.log(field_sizes).mean())

    skills = [max(baseline - ll, 1e-3) for ll in log_losses]  # floor keeps weights valid
    total = sum(skills)
    weights = [sk / total for sk in skills]
    return EnsembleShim(models, weights)
