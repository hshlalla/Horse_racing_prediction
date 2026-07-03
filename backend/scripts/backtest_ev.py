"""
Honest EV backtest.

Mirrors the production inference in app/ml/predict/service.py as closely as a
batch job can:
  * per-race softmax ensemble blend (EnsembleShim.predict with race_ids)
  * isotonic calibration (apply_calibration, per race)
  * edge = calibrated_win_prob - market_prob  (market = normalised 1/odds)

Then simulates flat 1,000 KRW bets on the model's top picks (WIN=top1,
QUINELLA=top2, TRIO=top3) against stored payouts, sweeping a min_edge filter so
we can see whether "only bet when the model sees value" improves ROI.

Cold-start inverse-odds blending (service.py step 7) IS replicated here via
career_starts. The only residual divergence from production is that
career_starts is dataset.py's per-horse cumcount (rows in the loaded window)
whereas service uses a live count of all prior RaceResults — these differ only
for horses with <3 starts whose earliest races fall outside the dataset window.
The --validate flag cross-checks a sample of races against predict_race
(96.7% top-1 match, mean |edge diff| 0.028) so the residual is negligible.

Run:
    DATABASE_URL=... uv run python -m scripts.backtest_ev
    DATABASE_URL=... uv run python -m scripts.backtest_ev --validate 40
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models.crawl import Race
from app.ml.predict.calibration import apply_calibration

CAT_COLS = ["horse_sex", "track", "track_condition", "weather", "surface", "grade"]
EDGE_THRESHOLDS = [0.0, 0.02, 0.05, 0.10, 0.15]
BET = 1000  # KRW per bet
TRACKS = ["SEOUL", "BUSAN", "JEJU"]


async def _load_payout_meta() -> dict[int, dict]:
    """Return {race_id: {"payouts": ..., "track": ..., "year": ...}}."""
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(Race.id, Race.payouts, Race.track, Race.race_date).where(
                    Race.payouts.is_not(None)
                )
            )
        ).all()
    out: dict[int, dict] = {}
    for r in rows:
        if not r.payouts:
            continue
        out[r.id] = {
            "payouts": r.payouts,
            "track": r.track,
            "year": r.race_date.year if r.race_date else None,
        }
    return out


def _coerce(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    df = df.copy()
    for f in features:
        if f in CAT_COLS:
            df[f] = df[f].astype("category")
        else:
            df[f] = pd.to_numeric(df[f], errors="coerce").fillna(0.0)
    return df


def _score_race(model, race_df: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Return calibrated + cold-start-blended per-race win probs (mirrors service.py)."""
    mfeats = [f for f in features if f in set(getattr(model, "feature_names_", features))]
    probs = model.predict(race_df[mfeats], race_ids=race_df["race_id"].values)
    probs = np.asarray(probs, dtype=float)
    if getattr(model, "calibrator", None) is not None:
        probs = apply_calibration(probs, model.calibrator)

    # Cold-start blending (service.py step 7): horses with <3 career starts are
    # pulled toward the normalised inverse-odds anchor.
    anchor = _market_probs(race_df["morning_odds"].values)
    n_starts = race_df["career_starts"].values.astype(float)
    w = np.minimum(n_starts / 3.0, 1.0)
    blended = w * probs + (1.0 - w) * anchor
    s = blended.sum()
    return blended / s if s > 0 else blended


def _market_probs(odds: np.ndarray) -> np.ndarray:
    odds = np.clip(odds.astype(float), 1.0, None)
    inv = 1.0 / odds
    s = inv.sum()
    return inv / s if s > 0 else np.ones_like(inv) / len(inv)


def _payout_return(payouts: dict, key: str, numbers_set: set[str], ordered: list[str] | None = None) -> float:
    """Return winnings for a 1000 KRW bet on this combo, or 0."""
    for p in payouts.get(key, []):
        pn = p.get("numbers", "")
        if ordered is not None:
            if pn == "-".join(ordered):
                return BET * p["odds"]
        else:
            if set(pn.split("-")) == numbers_set:
                return BET * p["odds"]
    return 0.0


def run(models: dict, all_df: pd.DataFrame, meta: dict[int, dict]) -> None:
    # stats[threshold][track_or_ALL][bet_type] = {"inv","ret","hits","races"}
    def _new():
        return {"inv": 0, "ret": 0.0, "hits": 0, "races": 0}

    stats: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(_new)))
    bet_types = ["win", "quinella", "trio"]

    grouped = all_df.groupby("race_id", sort=False)
    n = 0
    for race_id, g in grouped:
        m = meta.get(race_id)
        if m is None or len(g) < 3:
            continue
        track = m["track"]
        model = models.get(track)
        if model is None:
            continue
        payouts = m["payouts"]

        g = g.reset_index(drop=True)
        probs = _score_race(model, g, list(all_df.attrs["features"]))
        mkt = _market_probs(g["morning_odds"].values)
        edge = probs - mkt

        order = np.argsort(-probs)  # rank by win prob desc
        nums = [str(int(g.loc[i, "program_number"])) for i in order]
        top1, top2, top3 = nums[0], set(nums[:2]), set(nums[:3])
        top_edge = float(edge[order[0]])

        win_ret = _payout_return(payouts, "win", {top1})
        q_ret = _payout_return(payouts, "quinella", top2)
        t_ret = _payout_return(payouts, "trio", top3)
        rets = {"win": win_ret, "quinella": q_ret, "trio": t_ret}

        for thr in EDGE_THRESHOLDS:
            if top_edge < thr:
                continue
            for scope in ("ALL", track):
                for bt in bet_types:
                    s = stats[thr][scope][bt]
                    s["inv"] += BET
                    s["ret"] += rets[bt]
                    s["hits"] += int(rets[bt] > 0)
                    s["races"] += 1
        n += 1

    print(f"\nScored {n} races with payouts.\n")
    _print_report(stats, bet_types)


def _harville_pair(probs: np.ndarray, i: int, j: int) -> float:
    """P(horses i and j both finish top-2, any order) via Harville."""
    pi, pj = float(probs[i]), float(probs[j])
    term = 0.0
    if pi < 1.0:
        term += pi * pj / (1.0 - pi)
    if pj < 1.0:
        term += pj * pi / (1.0 - pj)
    return min(term, 0.99)


def run_quinella_gate(models: dict, all_df: pd.DataFrame, meta: dict) -> None:
    """Compare quinella ROI under two gates: (A) favorite win-edge >= thr
    (current API) vs (B) quinella-specific edge = Harville pair prob
    (model) - Harville pair prob (market) for the top-2 combo."""
    features = list(all_df.attrs["features"])

    def _new():
        return {"inv": 0, "ret": 0.0, "hits": 0}

    # stats[gate][thr][scope]
    stats = {"favorite": defaultdict(lambda: defaultdict(_new)),
             "quinella": defaultdict(lambda: defaultdict(_new))}

    for race_id, g in all_df.groupby("race_id", sort=False):
        m = meta.get(race_id)
        if m is None or len(g) < 3:
            continue
        track = m["track"]
        model = models.get(track)
        if model is None:
            continue
        payouts = m["payouts"]
        g = g.reset_index(drop=True)
        probs = _score_race(model, g, features)
        mkt = _market_probs(g["morning_odds"].values)
        edge = probs - mkt
        order = np.argsort(-probs)
        i, j = int(order[0]), int(order[1])
        nums = [str(int(g.loc[k, "program_number"])) for k in order]
        top2 = set(nums[:2])
        q_ret = _payout_return(payouts, "quinella", top2)

        fav_edge = float(edge[i])
        q_edge = _harville_pair(probs, i, j) - _harville_pair(mkt, i, j)
        gate_vals = {"favorite": fav_edge, "quinella": q_edge}

        for gate, val in gate_vals.items():
            for thr in EDGE_THRESHOLDS:
                if val < thr:
                    continue
                for scope in ("ALL", track):
                    s = stats[gate][thr][scope]
                    s["inv"] += BET
                    s["ret"] += q_ret
                    s["hits"] += int(q_ret > 0)

    print("\n=== QUINELLA GATE COMPARISON (bet = top-2 by win prob) ===")
    for gate in ("favorite", "quinella"):
        label = "본선마 win-edge 게이트" if gate == "favorite" else "복승 Harville-edge 게이트"
        print(f"\n--- {gate} gate ({label}) ---")
        for thr in EDGE_THRESHOLDS:
            for scope in ("ALL", "SEOUL"):
                s = stats[gate][thr].get(scope)
                if not s or s["inv"] == 0:
                    continue
                roi = (s["ret"] - s["inv"]) / s["inv"] * 100
                races = s["inv"] // BET
                hr = s["hits"] / races * 100 if races else 0
                print(f"  edge>={thr:.2f} [{scope}]  ROI {roi:+7.1f}%  hit {hr:5.1f}%  races {races}")


def _print_report(stats, bet_types):
    for thr in EDGE_THRESHOLDS:
        print("=" * 70)
        print(f"min_edge >= {thr:.2f}")
        print("=" * 70)
        for scope in ["ALL"] + TRACKS:
            sc = stats[thr].get(scope)
            if not sc:
                continue
            races = sc["win"]["races"]
            if races == 0:
                print(f"  [{scope}] no races pass filter")
                continue
            print(f"  [{scope}]  bettable races: {races}")
            for bt in bet_types:
                s = sc[bt]
                inv, ret = s["inv"], s["ret"]
                roi = (ret - inv) / inv * 100 if inv else 0.0
                hitrate = s["hits"] / s["races"] * 100 if s["races"] else 0.0
                print(
                    f"      {bt:9s} ROI {roi:+7.1f}%  hit {hitrate:5.1f}%  "
                    f"inv {inv:>10,}  ret {ret:>12,.0f}"
                )
        print()


# Thresholds on the RAW (uncalibrated) value score. run_value gates on
# vm._raw_proba, not predict_proba, so these stay valid regardless of whether
# an isotonic calibrator has been attached (calibration would shrink the scale
# to the ~4% base rate and make these thresholds select nothing).
VALUE_THRESHOLDS = [0.3, 0.5, 0.7, 0.9]
UPSET_ODDS_MIN = 5.0  # value_model target = odds > 5 AND wins


def run_value(models: dict, all_df: pd.DataFrame, meta: dict) -> None:
    """Backtest the value model (Approach B): WIN bets on high upset-probability
    longshots (odds >= 5). One bet per qualifying horse (not per race)."""
    features = list(all_df.attrs["features"])

    def _new():
        return {"inv": 0, "ret": 0.0, "hits": 0, "bets": 0, "races": set()}

    stats: dict = defaultdict(lambda: defaultdict(_new))  # [thr][scope]

    # Winner program_number per race from payouts (win payout numbers).
    for race_id, g in all_df.groupby("race_id", sort=False):
        m = meta.get(race_id)
        if m is None or len(g) < 3:
            continue
        track = m["track"]
        model = models.get(track)
        vm = getattr(model, "value_model", None) if model else None
        if vm is None:
            continue
        payouts = m["payouts"]
        win_nums = {p.get("numbers"): p["odds"] for p in payouts.get("win", [])}

        g = g.reset_index(drop=True)
        mfeats = [f for f in features if f in set(getattr(model, "feature_names_", features))]
        try:
            # Raw score (pre-calibration) so VALUE_THRESHOLDS stay meaningful.
            upset = np.asarray(vm._raw_proba(g[mfeats]), dtype=float)
        except Exception:
            continue

        odds = g["morning_odds"].astype(float).values
        for i in range(len(g)):
            if odds[i] < UPSET_ODDS_MIN:
                continue
            num = str(int(g.loc[i, "program_number"]))
            won = num in win_nums
            ret = BET * win_nums[num] if won else 0.0
            for thr in VALUE_THRESHOLDS:
                if upset[i] < thr:
                    continue
                for scope in ("ALL", track):
                    s = stats[thr][scope]
                    s["inv"] += BET
                    s["ret"] += ret
                    s["hits"] += int(won)
                    s["bets"] += 1
                    s["races"].add(race_id)

    print("\n=== VALUE MODEL (upset WIN, odds>=5) ===\n")
    for thr in VALUE_THRESHOLDS:
        print("=" * 66)
        print(f"upset_prob >= {thr:.1f}")
        print("=" * 66)
        for scope in ["ALL"] + TRACKS:
            s = stats[thr].get(scope)
            if not s or s["bets"] == 0:
                print(f"  [{scope}] no qualifying bets")
                continue
            roi = (s["ret"] - s["inv"]) / s["inv"] * 100 if s["inv"] else 0.0
            hr = s["hits"] / s["bets"] * 100 if s["bets"] else 0.0
            print(
                f"  [{scope}]  bets {s['bets']:>4} over {len(s['races']):>4} races  "
                f"WIN ROI {roi:+7.1f}%  hit {hr:5.1f}%  ret {s['ret']:>11,.0f}"
            )
        print()


async def _validate(models: dict, all_df: pd.DataFrame, meta: dict, sample: int) -> None:
    """Cross-check batch top1 + edge against predict_race on a random sample."""
    from app.ml.predict.service import predict_race

    rng = np.random.default_rng(42)
    ids = list({rid for rid in all_df["race_id"].unique() if rid in meta})
    rng.shuffle(ids)
    ids = ids[:sample]

    feats = list(all_df.attrs["features"])
    top1_match = 0
    edge_diffs = []
    checked = 0
    async with async_session_factory() as session:
        for rid in ids:
            g = all_df[all_df["race_id"] == rid].reset_index(drop=True)
            if len(g) < 3:
                continue
            model = models[meta[rid]["track"]]
            probs = _score_race(model, g, feats)
            mkt = _market_probs(g["morning_odds"].values)
            edge = probs - mkt
            b_order = np.argsort(-probs)
            b_top1 = int(g.loc[b_order[0], "program_number"])
            b_edge = float(edge[b_order[0]])

            try:
                preds = await predict_race(session, int(rid))
            except Exception as e:
                print(f"  race {rid}: predict_race failed: {e}")
                continue
            if not preds:
                continue
            p_top1 = preds[0].program_number
            p_edge = preds[0].edge_score
            checked += 1
            if b_top1 == p_top1:
                top1_match += 1
            edge_diffs.append(abs(b_edge - p_edge))

    if checked:
        print("\n--- Validation vs predict_race ---")
        print(f"  races checked      : {checked}")
        print(f"  top-1 pick match   : {top1_match}/{checked} ({top1_match/checked*100:.1f}%)")
        print(f"  mean |edge diff|   : {np.mean(edge_diffs):.4f}")
        print(f"  max  |edge diff|   : {np.max(edge_diffs):.4f}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", type=int, default=0, help="validate against predict_race on N races")
    ap.add_argument("--since", type=str, default="", help="only backtest races on/after YYYY-MM-DD (out-of-sample)")
    ap.add_argument("--value", action="store_true", help="backtest the value model (upset longshot WIN)")
    ap.add_argument("--qgate", action="store_true", help="compare quinella gating strategies")
    args = ap.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL not set")
        sys.exit(1)

    from app.ml.train.dataset import load_dataset_pg
    from app.ml.train.promote import load_production_model

    print("Loading dataset...")
    train_df, val_df, test_df, features, target = load_dataset_pg(db_url)
    all_df = pd.concat([train_df, val_df, test_df], ignore_index=True)

    # Career-start count (0-based prior starts) over the FULL window, matching
    # dataset.py's cumcount, used for cold-start blending. Compute before the
    # payout filter so counts reflect a horse's full history.
    all_df = all_df.sort_values(["horse_id", "race_date", "race_id"])
    all_df["career_starts"] = all_df.groupby("horse_id").cumcount()
    all_df = all_df.sort_values(["race_date", "race_id"]).reset_index(drop=True)

    if args.since:
        cutoff = pd.Timestamp(args.since)
        before = all_df["race_id"].nunique()
        all_df = all_df[all_df["race_date"] >= cutoff].copy()
        print(f"  --since {args.since}: {all_df['race_id'].nunique()}/{before} races")

    print("Loading payouts...")
    meta = await _load_payout_meta()
    all_df = all_df[all_df["race_id"].isin(meta)].copy()
    all_df = _coerce(all_df, features)
    all_df.attrs["features"] = features
    print(f"  {len(all_df)} horse-rows across {all_df['race_id'].nunique()} races")

    models = {}
    for t in TRACKS:
        try:
            models[t] = load_production_model(t)
        except FileNotFoundError:
            print(f"  no production model for {t} — skipping")
    if not models:
        print("No models found")
        sys.exit(1)

    if args.validate:
        await _validate(models, all_df, meta, args.validate)
        return

    if args.value:
        run_value(models, all_df, meta)
        return

    if args.qgate:
        run_quinella_gate(models, all_df, meta)
        return

    run(models, all_df, meta)


if __name__ == "__main__":
    asyncio.run(main())
