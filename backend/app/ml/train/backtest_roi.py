"""
Batch backtest: loads all race data via load_dataset_pg, predicts offline,
then simulates WIN / QUINELLA / TRIO betting against stored payouts.

Run:
    DATABASE_URL=postgresql+psycopg2://... python -m app.ml.train.backtest_roi
"""
import asyncio
import logging
import os

import numpy as np
from scipy.special import softmax
from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models.crawl import Race

logger = logging.getLogger(__name__)


async def _load_payouts() -> dict[int, dict]:
    """Return {race_id: payouts_dict} for all races that have payouts."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Race.id, Race.payouts).where(Race.payouts.is_not(None))
        )
        return {row.id: row.payouts for row in result.all() if row.payouts}


async def run_backtest() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        logger.error("DATABASE_URL not set — cannot run backtest")
        return

    from app.ml.train.dataset import load_dataset_pg, FEATURES
    from app.ml.train.promote import load_production_model

    # 1. Load payouts
    payouts_by_race = await _load_payouts()
    if not payouts_by_race:
        logger.info("No races with payouts found — nothing to backtest")
        return

    # 2. Load feature matrix from DB in one batch query
    train_df, val_df, test_df, features, target = load_dataset_pg(db_url)
    # Use all available data (union of splits) for backtesting
    import pandas as pd
    all_df = pd.concat([train_df, val_df, test_df], ignore_index=True)
    all_df = all_df[all_df["race_id"].isin(payouts_by_race)].copy()

    if all_df.empty:
        logger.info("No feature rows match races with payouts")
        return

    # 3. Load production model (use SEOUL as default; falls back gracefully)
    try:
        model = load_production_model("SEOUL")
    except FileNotFoundError:
        logger.error("No production model found — run training first")
        return

    # 4. Score all horses in one model call
    cat_cols = ["horse_sex", "track", "track_condition", "weather"]
    for c in cat_cols:
        if c in all_df.columns:
            all_df[c] = all_df[c].astype("category")
    all_df["pred_score"] = model.predict(all_df[FEATURES])

    # 5. Per-race betting simulation
    investments: dict[str, int] = {"WIN": 0, "QUINELLA": 0, "TRIO": 0}
    returns: dict[str, float] = {"WIN": 0.0, "QUINELLA": 0.0, "TRIO": 0.0}

    for race_id, race_df in all_df.groupby("race_id"):
        payouts = payouts_by_race.get(race_id, {})
        if not payouts or len(race_df) < 3:
            continue

        race_df = race_df.copy()
        race_df["prob"] = softmax(race_df["pred_score"].values)
        race_df = race_df.sort_values("prob", ascending=False)

        top1 = str(int(race_df.iloc[0]["program_number"]))
        top2 = {str(int(r["program_number"])) for _, r in race_df.head(2).iterrows()}
        top3 = {str(int(r["program_number"])) for _, r in race_df.head(3).iterrows()}

        # WIN
        investments["WIN"] += 1000
        for p in payouts.get("win", []):
            if p.get("numbers") == top1:
                returns["WIN"] += 1000 * p["odds"]

        # QUINELLA
        investments["QUINELLA"] += 1000
        for p in payouts.get("quinella", []):
            if set(p.get("numbers", "").split("-")) == top2:
                returns["QUINELLA"] += 1000 * p["odds"]

        # TRIO
        investments["TRIO"] += 1000
        for p in payouts.get("trio", []):
            if set(p.get("numbers", "").split("-")) == top3:
                returns["TRIO"] += 1000 * p["odds"]

    print("\n--- Backtest Results ---")
    for strategy in ["WIN", "QUINELLA", "TRIO"]:
        inv = investments[strategy]
        ret = returns[strategy]
        roi = ((ret - inv) / inv * 100) if inv > 0 else 0.0
        print(f"Strategy {strategy}:")
        print(f"  Investment: {inv:,.0f} KRW")
        print(f"  Return:     {ret:,.0f} KRW")
        print(f"  ROI:        {roi:+.2f}%")


if __name__ == "__main__":
    asyncio.run(run_backtest())
