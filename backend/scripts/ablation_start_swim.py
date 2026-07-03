"""
Ablation: do the sparse board features (start_training / swim / workout_count)
help prediction once their data is densified?

Same methodology as the health-feature experiment: retrain the per-track
ensemble WITH vs WITHOUT the candidate features and compare per-race
val_log_loss (the fixed _race_log_loss metric). No promotion / no save.

Run AFTER densifying board data:
    DATABASE_URL=... uv run python -m scripts.ablation_start_swim --track SEOUL

The candidate features must exist as columns in load_dataset_pg's output
(dataset.py still produces them even though FEATURES excludes them).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np


CANDIDATES = [
    "start_training_passed",
    "days_since_start_training",
    "swim_count_recent",
    "recent_workout_count_30d",
]


def _coverage(df, cols):
    out = {}
    for c in cols:
        if c not in df.columns:
            out[c] = "MISSING COL"
            continue
        s = df[c]
        # non-default = not null and not the sentinel (0 / 999)
        nz = ((s.notna()) & (s != 0) & (s != 999)).mean() * 100
        out[c] = f"{nz:.1f}% non-default"
    return out


def _eval(track_train, track_val, features, target):
    from app.ml.train.models.lgbm_binary import train_lgbm
    from app.ml.train.models.catboost_binary import train_catboost
    from app.ml.train.models.ensemble import build_ensemble, _race_log_loss

    lgbm = train_lgbm(track_train, track_val, features, target)
    cat = train_catboost(track_train, track_val, features, target)
    ens = build_ensemble([lgbm, cat], track_val, features, target)
    ll = _race_log_loss(ens, track_val, features, target)
    ll_lgbm = _race_log_loss(lgbm, track_val, features, target)
    ll_cat = _race_log_loss(cat, track_val, features, target)
    return ll, ll_lgbm, ll_cat, ens.weights


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="SEOUL", choices=["SEOUL", "BUSAN", "JEJU"])
    ap.add_argument("--candidates", default="", help="comma-separated subset to test (default: all)")
    args = ap.parse_args()

    global CANDIDATES
    if args.candidates:
        CANDIDATES = [c.strip() for c in args.candidates.split(",") if c.strip()]

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL not set"); sys.exit(1)

    from app.ml.train.dataset import load_dataset_pg, FEATURES

    train_df, val_df, _t, features, target = load_dataset_pg(db_url)
    tr = train_df[train_df["track"] == args.track].copy()
    va = val_df[val_df["track"] == args.track].copy()
    print(f"{args.track}: train={len(tr)} rows / {tr['race_id'].nunique()} races, "
          f"val={len(va)} rows / {va['race_id'].nunique()} races")

    present = [c for c in CANDIDATES if c in train_df.columns]
    missing = [c for c in CANDIDATES if c not in train_df.columns]
    if missing:
        print(f"WARNING: candidate cols not produced by dataset: {missing}")

    print("\n-- candidate feature coverage (train) --")
    for c, v in _coverage(tr, present).items():
        print(f"   {c}: {v}")
    print("-- candidate feature coverage (val) --")
    for c, v in _coverage(va, present).items():
        print(f"   {c}: {v}")

    base = list(FEATURES)
    plus = base + [c for c in present if c not in base]

    print(f"\nBASELINE features={len(base)} | +candidates features={len(plus)}")
    print("Training BASELINE (without candidates)...")
    b_ll, b_l, b_c, b_w = _eval(tr, va, base, target)
    print("Training +CANDIDATES...")
    p_ll, p_l, p_c, p_w = _eval(tr, va, plus, target)

    print("\n" + "=" * 60)
    print(f"ABLATION RESULT — {args.track}")
    print("=" * 60)
    print(f"  ensemble val_log_loss  baseline {b_ll:.4f}  → +cand {p_ll:.4f}  "
          f"(Δ {p_ll - b_ll:+.4f})")
    print(f"  lgbm     val_log_loss  baseline {b_l:.4f}  → +cand {p_l:.4f}  "
          f"(Δ {p_l - b_l:+.4f})")
    print(f"  catboost val_log_loss  baseline {b_c:.4f}  → +cand {p_c:.4f}  "
          f"(Δ {p_c - b_c:+.4f})")
    verdict = "HELPS ✅" if p_ll < b_ll - 0.002 else (
        "HURTS ❌" if p_ll > b_ll + 0.002 else "NO EFFECT ➖")
    print(f"  verdict (ensemble): {verdict}  (lower log_loss = better)")


if __name__ == "__main__":
    main()
