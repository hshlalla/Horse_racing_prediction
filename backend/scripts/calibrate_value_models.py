"""
Retrofit isotonic calibration onto the value model of each production ensemble
WITHOUT a full retrain. Fits raw upset score → actual upset rate on the val set
and re-saves the ensemble in place. Future retrains fit this automatically
(train_value_model), this script just makes existing models calibrated now.

    DATABASE_URL=... uv run python -m scripts.calibrate_value_models
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

TRACKS = ["SEOUL", "BUSAN", "JEJU"]
CAT = ["horse_sex", "track", "track_condition", "weather", "surface", "grade"]
ODDS_THR = 5.0


def main():
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL not set"); sys.exit(1)

    from app.ml.train.dataset import load_dataset_pg, FEATURES
    from app.ml.train.promote import get_production_metrics

    _tr, val_df, _te, features, _t = load_dataset_pg(db_url)

    saved_any = False
    for track in TRACKS:
        metrics = get_production_metrics(track)
        if not metrics:
            print(f"[{track}] no production model — skip"); continue
        path = metrics["model_path"]
        with open(path, "rb") as f:
            ens = pickle.load(f)
        vm = getattr(ens, "value_model", None)
        if vm is None:
            print(f"[{track}] no value_model — skip"); continue

        va = val_df[val_df["track"] == track].copy()
        if len(va) < 50:
            print(f"[{track}] too few val rows ({len(va)}) — skip"); continue
        for c in features:
            if c in CAT:
                va[c] = va[c].astype("category")
            else:
                va[c] = pd.to_numeric(va[c], errors="coerce").fillna(0.0)

        mfeats = [f for f in features if f in set(getattr(ens, "feature_names_", features))]
        raw = vm._raw_proba(va[mfeats])
        odds = pd.to_numeric(va["morning_odds"], errors="coerce").fillna(0).values
        target = ((odds > ODDS_THR) & (va["finish_position"].values == 1)).astype(int)

        if len(set(target.tolist())) < 2:
            print(f"[{track}] val target single-class — skip"); continue

        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(raw, target)
        vm.calibrator = cal

        calibrated = np.clip(cal.predict(raw), 0.0, 1.0)
        base = target.mean()
        # Atomic replace so an interrupted dump can't corrupt the live artifact.
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(ens, f)
        os.replace(tmp, path)
        saved_any = True
        print(f"[{track}] calibrated & saved {os.path.basename(path)}")
        print(f"    raw mean {raw.mean():.3f} (p90 {np.percentile(raw,90):.3f})"
              f" → calibrated mean {calibrated.mean():.3f} (p90 {np.percentile(calibrated,90):.3f})"
              f" | actual base rate {base:.3f}")

    # Bump production.json mtime so a running server hot-reloads the models
    # (service._get_model caches keyed on production.json mtime, not the .pkl).
    if saved_any:
        from app.ml.train.promote import _production_json_path
        pj = _production_json_path()
        if pj.exists():
            os.utime(pj, None)
            print(f"touched {pj} → running servers will reload on next request")


if __name__ == "__main__":
    main()
