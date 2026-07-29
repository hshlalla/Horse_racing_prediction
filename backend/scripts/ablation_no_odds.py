"""
How much does dropping morning_odds hurt, and can re-adding previously-dropped
features recover the loss?

Trains the SEOUL ensemble under three feature sets and compares per-race
val_log_loss (the fixed _race_log_loss metric). Lower = better; the uniform
baseline ln(field_size) is the "no skill" reference.

    DATABASE_URL=... uv run python -m scripts.ablation_no_odds
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ODDS_FEATS = ["morning_odds", "morning_odds_rank", "odds_drift"]

# Features dropped in v2 for ~zero importance *while odds was present*; odds may
# have been absorbing their signal, so they could matter once odds is gone.
# (track excluded: constant for a single-track model. workout/swim excluded:
#  structurally sparse / discontinued — see dataset.py.)
READD = [
    "body_weight_kg", "body_weight_delta_kg", "horse_age", "horse_sex",
    "humidity", "sire_win_rate", "jockey_changed", "surface", "grade",
]


def _eval(tr, va, feats, target):
    from app.ml.train.models.lgbm_binary import train_lgbm
    from app.ml.train.models.catboost_binary import train_catboost
    from app.ml.train.models.ensemble import build_ensemble, _race_log_loss
    lgbm = train_lgbm(tr, va, feats, target)
    cat = train_catboost(tr, va, feats, target)
    ens = build_ensemble([lgbm, cat], va, feats, target)
    return {
        "ensemble": _race_log_loss(ens, va, feats, target),
        "lgbm": _race_log_loss(lgbm, va, feats, target),
        "catboost": _race_log_loss(cat, va, feats, target),
        "n_feats": len(feats),
    }


def main():
    db = os.environ.get("DATABASE_URL", "")
    if not db:
        print("DATABASE_URL not set"); sys.exit(1)
    from app.ml.train.dataset import load_dataset_pg, FEATURES

    train_df, val_df, _t, features, target = load_dataset_pg(db)
    track = "SEOUL"
    tr = train_df[train_df["track"] == track].copy()
    va = val_df[val_df["track"] == track].copy()

    # uniform "no skill" baseline for reference
    fs = va.groupby("race_id").size()
    uniform = float(np.log(fs).mean())

    base = list(FEATURES)
    no_odds = [f for f in base if f not in ODDS_FEATS]
    readd_present = [c for c in READD if c in train_df.columns and c not in no_odds]
    no_odds_plus = no_odds + readd_present

    print(f"{track}: train={len(tr)} rows/{tr['race_id'].nunique()} races, "
          f"val={len(va)} rows/{va['race_id'].nunique()} races")
    print(f"uniform baseline ln(field) = {uniform:.4f}  (no-skill reference)")
    print(f"re-added features: {readd_present}\n")

    configs = [
        ("A) 현행 (배당 포함)", base),
        ("B) 배당 제거", no_odds),
        ("C) 배당 제거 + 제외피처 재추가", no_odds_plus),
    ]
    results = {}
    for name, feats in configs:
        print(f"training {name} ({len(feats)} feats)...")
        results[name] = _eval(tr, va, feats, target)

    print("\n" + "=" * 64)
    print(f"RESULT — {track}  (ensemble val_log_loss, lower=better)")
    print("=" * 64)
    a = results["A) 현행 (배당 포함)"]["ensemble"]
    for name, r in results.items():
        e = r["ensemble"]
        vs_base = e - a
        vs_unif = uniform - e
        print(f"  {name:32s} ens {e:.4f}  (vs현행 {vs_base:+.4f} | vs무작위 {vs_unif:+.4f})  "
              f"[lgbm {r['lgbm']:.3f} cat {r['catboost']:.3f}]")
    print(f"\n  무작위(uniform) = {uniform:.4f}")


if __name__ == "__main__":
    main()
