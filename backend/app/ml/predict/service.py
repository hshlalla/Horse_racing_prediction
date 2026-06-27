"""
Prediction service — returns real calibrated predictions from the production model.

Hot-reload: checks production.json mtime on every call and reloads the model
if the file has changed since the last load.

Cold-start: horses with fewer than 3 lifetime starts are blended with the
field-average probability to prevent over-confident predictions.

Stale fallback: if model inference fails, the service returns any cached
RacePrediction rows from the database with is_stale=True.
"""

import datetime
import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy.special import softmax
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.crawl import (
    Horse,
    InraceTiming,
    Race,
    RaceEntry,
    RacePrediction,
    RaceResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature list — must match the column order used during training
# ---------------------------------------------------------------------------

FEATURES = [
    "jockey_id",
    "trainer_id",
    "program_number",
    "distance_m",
    "field_size",
    "carry_weight_kg",
    "body_weight_kg",
    "morning_odds",
    "horse_age",
    "horse_sex",
    "track",
    "track_condition",
    "weather",
    "days_since_last_race",
    "horse_win_rate",
    "jockey_win_rate",
    "trainer_win_rate",
    "sire_win_rate",
    "past_avg_s1f_time",
    "past_avg_g3f_time",
    "humidity",
    "past_avg_start_rank",
    "past_avg_mid_rank",
    "past_avg_finish_rank",
    "surface",
    "grade",
    "body_weight_delta_kg",
    "morning_odds_rank",
    "distance_win_rate",
    "jockey_horse_win_rate",
]

# ---------------------------------------------------------------------------
# In-memory model cache: {track: (model, mtime_float)}
# ---------------------------------------------------------------------------

_model_cache: dict[str, tuple] = {}


def _production_json_path() -> Path:
    base = os.environ.get("MODEL_DIR", "models")
    return Path(base) / "production.json"


def _current_mtime() -> float:
    """Return mtime of production.json, or -1 if it doesn't exist."""
    p = _production_json_path()
    try:
        return p.stat().st_mtime
    except FileNotFoundError:
        return -1.0


def _get_model(track: str):
    """
    Return the production model for *track*, reloading from disk if
    production.json has been updated since the last load.
    """
    from app.ml.train.promote import load_production_model

    mtime = _current_mtime()
    cached = _model_cache.get(track)
    if cached is not None and cached[1] == mtime:
        return cached[0]

    model = load_production_model(track)
    _model_cache[track] = (model, mtime)
    logger.info("Loaded production model for track=%s (mtime=%s)", track, mtime)
    return model


def _get_model_version(track: str) -> str:
    """Read the version string from production.json for *track*."""
    p = _production_json_path()
    try:
        with open(p) as f:
            data = json.load(f)
        return data.get(track, {}).get("version", "unknown")
    except Exception:
        return "unknown"


def reload_model(track: str) -> None:
    """Force-evict the cache entry for *track* so the next call reloads."""
    _model_cache.pop(track, None)
    logger.info("Evicted model cache for track=%s", track)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class HorsePrediction(BaseModel):
    horse_id: int
    horse_name: str
    program_number: int
    win_probability: float
    place_probability: float
    model_versions: dict
    features_snapshot: dict
    computed_at: datetime.datetime


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------


async def _get_horse_history(
    session: AsyncSession, horse_id: int, as_of_date: datetime.date
) -> dict:
    """Compute EWMA-based features for a horse from historical race results."""
    result = await session.execute(
        select(RaceResult, Race)
        .join(Race, RaceResult.race_id == Race.id)
        .where(RaceResult.horse_id == horse_id, Race.race_date < as_of_date)
        .order_by(Race.race_date)
    )
    rows = list(result.all())
    if not rows:
        return {
            "horse_win_rate": 0.0,
            "days_since_last_race": 30.0,
            "past_avg_s1f_time": 14.0,
            "past_avg_g3f_time": 38.0,
            "past_avg_start_rank": 7.0,
            "past_avg_mid_rank": 7.0,
            "past_avg_finish_rank": 7.0,
            "n_starts": 0,
        }

    is_wins = [1 if r.RaceResult.finish_position == 1 else 0 for r in rows]
    finish_ranks = [r.RaceResult.finish_position or 7 for r in rows]
    
    if not is_wins:
        return {
            "horse_win_rate": 0.0,
            "days_since_last_race": 30.0,
            "past_avg_s1f_time": 14.0,
            "past_avg_g3f_time": 38.0,
            "past_avg_start_rank": 7.0,
            "past_avg_mid_rank": 7.0,
            "past_avg_finish_rank": 7.0,
            "n_starts": 0,
        }

    win_rate = float(
        pd.Series(is_wins).ewm(span=5, min_periods=1).mean().iloc[-1]
    )
    last_date = rows[-1].Race.race_date
    try:
        days_since = float((as_of_date - last_date).days)
    except (TypeError, AttributeError):
        days_since = 30.0

    timing_result = await session.execute(
        select(InraceTiming, Race)
        .join(Race, InraceTiming.race_id == Race.id)
        .where(InraceTiming.horse_id == horse_id, Race.race_date < as_of_date)
        .order_by(Race.race_date)
    )
    timings = list(timing_result.all())
    s1f_times = [t.InraceTiming.s1f_time for t in timings if t.InraceTiming.s1f_time]
    g3f_times = [t.InraceTiming.g3f_time for t in timings if t.InraceTiming.g3f_time]
    
    start_ranks = [t.InraceTiming.corner1_rank or 7 for t in timings]
    # Mid-rank calculation: average of available corner ranks
    mid_ranks = []
    for t in timings:
        c_ranks = [c for c in [t.InraceTiming.corner2_rank, t.InraceTiming.corner3_rank, t.InraceTiming.corner4_rank] if c is not None]
        mid_ranks.append(sum(c_ranks) / len(c_ranks) if c_ranks else 7.0)

    avg_s1f = (
        float(pd.Series(s1f_times).ewm(span=5).mean().iloc[-1]) if s1f_times else 14.0
    )
    avg_g3f = (
        float(pd.Series(g3f_times).ewm(span=5).mean().iloc[-1]) if g3f_times else 38.0
    )
    avg_start_rank = float(pd.Series(start_ranks).ewm(span=5).mean().iloc[-1]) if start_ranks else 7.0
    avg_mid_rank = float(pd.Series(mid_ranks).ewm(span=5).mean().iloc[-1]) if mid_ranks else 7.0
    avg_finish_rank = float(pd.Series(finish_ranks).ewm(span=5).mean().iloc[-1]) if finish_ranks else 7.0

    return {
        "horse_win_rate": win_rate,
        "days_since_last_race": days_since,
        "past_avg_s1f_time": avg_s1f,
        "past_avg_g3f_time": avg_g3f,
        "past_avg_start_rank": avg_start_rank,
        "past_avg_mid_rank": avg_mid_rank,
        "past_avg_finish_rank": avg_finish_rank,
        "n_starts": len(rows),
    }


async def _get_win_rate(
    session: AsyncSession,
    entity_id: int,
    entity_col: str,
    as_of_date: datetime.date,
) -> float:
    """
    Compute historical win rate for a jockey or trainer as of a given date.
    entity_col must be 'jockey_id' or 'trainer_id'.
    Returns 0.0 if no history.
    """
    from sqlalchemy import func, case

    stmt = (
        select(
            func.avg(case((RaceResult.finish_position == 1, 1), else_=0))
        )
        .select_from(RaceResult)
        .join(Race, RaceResult.race_id == Race.id)
        .join(
            RaceEntry,
            (RaceEntry.race_id == RaceResult.race_id)
            & (RaceEntry.horse_id == RaceResult.horse_id),
        )
        .where(Race.race_date < as_of_date)
    )
    if entity_col == "jockey_id":
        stmt = stmt.where(RaceEntry.jockey_id == entity_id)
    else:
        stmt = stmt.where(RaceEntry.trainer_id == entity_id)

    result = await session.execute(stmt)
    rate = result.scalar()
    return float(rate) if rate is not None else 0.0


async def _get_prev_body_weight(
    session: AsyncSession,
    horse_id: int,
    as_of_date: datetime.date,
) -> float:
    """Return the horse's body weight from its most recent race before as_of_date."""
    stmt = (
        select(RaceEntry.body_weight_kg)
        .join(Race, RaceEntry.race_id == Race.id)
        .where(RaceEntry.horse_id == horse_id)
        .where(Race.race_date < as_of_date)
        .order_by(Race.race_date.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    weight = result.scalar()
    return float(weight) if weight else 500.0


async def _get_sire_win_rate(
    session: AsyncSession,
    horse_id: int,
    as_of_date: datetime.date,
) -> float:
    """
    Compute historical win rate of this horse's sire (father).
    Looks up pedigree first; if no pedigree, returns 0.0.
    """
    from sqlalchemy import func, case
    from app.db.models.crawl import Pedigree

    # Step 1: get sire_id
    pedigree_stmt = select(Pedigree.sire_id).where(Pedigree.horse_id == horse_id)
    pedigree_result = await session.execute(pedigree_stmt)
    sire_id = pedigree_result.scalar()
    if not sire_id:
        return 0.0

    # Step 2: compute sire's own historical win rate (as a racing horse) as proxy
    stmt = (
        select(
            func.avg(case((RaceResult.finish_position == 1, 1), else_=0))
        )
        .select_from(RaceResult)
        .join(Race, RaceResult.race_id == Race.id)
        .where(RaceResult.horse_id == sire_id)
        .where(Race.race_date < as_of_date)
    )
    result = await session.execute(stmt)
    rate = result.scalar()
    return float(rate) if rate is not None else 0.0


async def _get_distance_win_rate(
    session: AsyncSession,
    horse_id: int,
    distance_bucket: str,
    as_of_date: datetime.date,
) -> float:
    """Win rate for this horse in the given distance bucket (short/middle/long)."""
    from sqlalchemy import func, case
    bucket_filter = {
        'short':  (Race.distance_m < 1300),
        'middle': (Race.distance_m >= 1300) & (Race.distance_m <= 1800),
        'long':   (Race.distance_m > 1800),
    }[distance_bucket]

    stmt = (
        select(func.avg(case((RaceResult.finish_position == 1, 1), else_=0)))
        .select_from(RaceResult)
        .join(Race, RaceResult.race_id == Race.id)
        .where(RaceResult.horse_id == horse_id)
        .where(bucket_filter)
        .where(Race.race_date < as_of_date)
    )
    result = await session.execute(stmt)
    rate = result.scalar()
    return float(rate) if rate is not None else 0.0


async def _get_pair_win_rate(
    session: AsyncSession,
    jockey_id: int,
    horse_id: int,
    as_of_date: datetime.date,
) -> float:
    """Historical win rate when this specific jockey rode this specific horse."""
    from sqlalchemy import func, case
    stmt = (
        select(func.avg(case((RaceResult.finish_position == 1, 1), else_=0)))
        .select_from(RaceResult)
        .join(Race, RaceResult.race_id == Race.id)
        .join(
            RaceEntry,
            (RaceEntry.race_id == RaceResult.race_id)
            & (RaceEntry.horse_id == RaceResult.horse_id),
        )
        .where(RaceResult.horse_id == horse_id)
        .where(RaceEntry.jockey_id == jockey_id)
        .where(Race.race_date < as_of_date)
    )
    result = await session.execute(stmt)
    rate = result.scalar()
    return float(rate) if rate is not None else 0.0


# ---------------------------------------------------------------------------
# Stale-cache helpers
# ---------------------------------------------------------------------------


async def _load_stale_predictions(
    session: AsyncSession, race_id: int
) -> list[HorsePrediction]:
    """Return cached RacePrediction rows for *race_id* with is_stale=True."""
    result = await session.execute(
        select(RacePrediction).where(RacePrediction.race_id == race_id)
    )
    cached_rows = result.scalars().all()
    if not cached_rows:
        return []

    # Mark each cached row as stale in the DB before returning
    try:
        for row in cached_rows:
            row.is_stale = True
        await session.commit()
    except Exception as exc:
        logger.warning("Failed to mark predictions stale for race_id=%s: %s", race_id, exc)

    # Fetch horse names for the stale predictions
    horse_ids = [r.horse_id for r in cached_rows]
    horse_result = await session.execute(
        select(Horse).where(Horse.id.in_(horse_ids))
    )
    horses = {h.id: h.name for h in horse_result.scalars().all()}

    return [
        HorsePrediction(
            horse_id=r.horse_id,
            horse_name=horses.get(r.horse_id, f"horse_{r.horse_id}"),
            program_number=0,  # not stored in RacePrediction
            win_probability=r.win_probability,
            place_probability=r.place_probability,
            model_versions={"version": r.model_version, "status": "stale"},
            features_snapshot={},
            computed_at=r.computed_at,
        )
        for r in cached_rows
    ]


async def _upsert_predictions(
    session: AsyncSession,
    race_id: int,
    predictions: list[HorsePrediction],
    model_version: str,
) -> None:
    """Upsert predictions into the race_predictions table."""
    now = datetime.datetime.now(datetime.timezone.utc)
    for pred in predictions:
        # Check for existing row
        result = await session.execute(
            select(RacePrediction).where(
                RacePrediction.race_id == race_id,
                RacePrediction.horse_id == pred.horse_id,
            )
        )
        existing = result.scalars().first()
        if existing is not None:
            existing.win_probability = pred.win_probability
            existing.place_probability = pred.place_probability
            existing.model_version = model_version
            existing.computed_at = now
            existing.is_stale = False
        else:
            session.add(
                RacePrediction(
                    race_id=race_id,
                    horse_id=pred.horse_id,
                    win_probability=pred.win_probability,
                    place_probability=pred.place_probability,
                    model_version=model_version,
                    computed_at=now,
                    is_stale=False,
                )
            )
    await session.flush()
    try:
        await session.commit()
    except Exception as exc:
        logger.warning("Failed to commit predictions for race_id=%s: %s", race_id, exc)
        await session.rollback()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def predict_race(
    db: AsyncSession, race_id: int
) -> list[HorsePrediction]:
    """
    Predict win probabilities for all horses in a race.

    Returns a list sorted by win_probability descending.
    Falls back to stale cached predictions (or []) if the model is unavailable.
    """
    try:
        return await _predict_race_impl(race_id, db)
    except Exception as exc:
        logger.warning(
            "predict_race failed for race_id=%s: %s — trying stale cache",
            race_id,
            exc,
        )
        stale = await _load_stale_predictions(db, race_id)
        return stale


async def _predict_race_impl(
    race_id: int, session: AsyncSession
) -> list[HorsePrediction]:
    # ------------------------------------------------------------------
    # 1. Fetch race
    # ------------------------------------------------------------------
    race_result = await session.execute(select(Race).where(Race.id == race_id))
    race = race_result.scalars().first()
    if race is None:
        return []

    # ------------------------------------------------------------------
    # 2. Fetch entries
    # ------------------------------------------------------------------
    entries_result = await session.execute(
        select(RaceEntry).where(RaceEntry.race_id == race_id)
    )
    entries = list(entries_result.scalars().all())
    if not entries:
        return []

    today: datetime.date = (
        race.race_date if race.race_date else datetime.date.today()
    )

    # ------------------------------------------------------------------
    # 3. Load production model (with hot-reload)
    # ------------------------------------------------------------------
    try:
        model = _get_model(race.track)
    except FileNotFoundError:
        logger.warning(
            "No production model for track=%s — returning uniform predictions",
            race.track,
        )
        n = len(entries)
        uniform = 1.0 / n
        return [
            HorsePrediction(
                horse_id=e.horse_id,
                horse_name="unknown",
                program_number=e.program_number,
                win_probability=uniform,
                place_probability=min(uniform * 3.0, 0.99),
                model_versions={"status": "no_model"},
                features_snapshot={},
                computed_at=datetime.datetime.now(datetime.timezone.utc),
            )
            for e in entries
        ]

    model_version = _get_model_version(race.track)

    # ------------------------------------------------------------------
    # 4. Fetch horse names (bulk query)
    # ------------------------------------------------------------------
    horse_ids = [e.horse_id for e in entries]
    horse_result = await session.execute(
        select(Horse).where(Horse.id.in_(horse_ids))
    )
    horses: dict[int, Horse] = {h.id: h for h in horse_result.scalars().all()}

    # ------------------------------------------------------------------
    # 5. Build feature rows
    # ------------------------------------------------------------------
    rows: list[dict] = []
    for entry in entries:
        horse = horses.get(entry.horse_id)
        horse_age = horse.age if horse and horse.age else 3
        horse_sex = horse.sex if horse and horse.sex else "M"

        history = await _get_horse_history(session, entry.horse_id, today)

        jockey_win_rate = (
            await _get_win_rate(session, entry.jockey_id, "jockey_id", today)
            if entry.jockey_id
            else 0.0
        )
        trainer_win_rate = (
            await _get_win_rate(session, entry.trainer_id, "trainer_id", today)
            if entry.trainer_id
            else 0.0
        )

        sire_win_rate = await _get_sire_win_rate(session, entry.horse_id, today)

        prev_body_weight = await _get_prev_body_weight(
            session, entry.horse_id, today
        )
        body_weight_delta = (entry.body_weight_kg or 500.0) - prev_body_weight

        distance_bucket = (
            'short' if race.distance_m < 1300
            else 'middle' if race.distance_m <= 1800
            else 'long'
        )
        distance_win_rate = await _get_distance_win_rate(
            session, entry.horse_id, distance_bucket, today
        )
        jockey_horse_win_rate = await _get_pair_win_rate(
            session, entry.jockey_id or 0, entry.horse_id, today
        )

        row: dict = {
            "jockey_id": entry.jockey_id or 0,
            "trainer_id": entry.trainer_id or 0,
            "program_number": entry.program_number,
            "distance_m": race.distance_m,
            "field_size": race.field_size or len(entries),
            "carry_weight_kg": entry.carry_weight_kg or 57.0,
            "body_weight_kg": entry.body_weight_kg or 500.0,
            "morning_odds": entry.morning_odds or 10.0,
            "horse_age": horse_age,
            "horse_sex": horse_sex,
            "track": race.track,
            "track_condition": race.track_condition or "건조",
            "weather": race.weather or "맑음",
            "days_since_last_race": history["days_since_last_race"],
            "horse_win_rate": history["horse_win_rate"],
            "jockey_win_rate": jockey_win_rate,
            "trainer_win_rate": trainer_win_rate,
            "sire_win_rate": sire_win_rate,
            "past_avg_s1f_time": history["past_avg_s1f_time"],
            "past_avg_g3f_time": history["past_avg_g3f_time"],
            "humidity": race.humidity or 50,
            "past_avg_start_rank": history["past_avg_start_rank"],
            "past_avg_mid_rank": history["past_avg_mid_rank"],
            "past_avg_finish_rank": history["past_avg_finish_rank"],
            "surface": race.surface or "Dirt",
            "grade": race.grade or "unknown",
            "body_weight_delta_kg": body_weight_delta,
            "morning_odds_rank": 0,   # placeholder — filled after the loop
            "distance_win_rate": distance_win_rate,
            "jockey_horse_win_rate": jockey_horse_win_rate,
            # Private columns used for cold-start logic (not passed to model)
            "_horse_id": entry.horse_id,
            "_n_starts": history["n_starts"],
        }
        rows.append(row)

    # Compute morning_odds_rank across all horses in this race
    all_odds = [r["morning_odds"] for r in rows]
    sorted_odds = sorted(set(all_odds))
    odds_rank_map = {v: i + 1 for i, v in enumerate(sorted_odds)}
    for r in rows:
        r["morning_odds_rank"] = odds_rank_map[r["morning_odds"]]

    # ------------------------------------------------------------------
    # 6. Model inference
    # ------------------------------------------------------------------
    pred_df = pd.DataFrame(rows)
    for col in ("horse_sex", "track", "track_condition", "weather", "surface", "grade"):
        pred_df[col] = pred_df[col].astype("category")

    raw_scores = model.predict(pred_df[FEATURES])

    # EnsembleShim returns probabilities directly (summing to 1 or close to it)
    if np.isclose(np.sum(raw_scores), 1.0, atol=0.1):
        probs = raw_scores
    else:
        probs = softmax(raw_scores)

    # Apply isotonic calibration if the model has one
    if getattr(model, "calibrator", None) is not None:
        from app.ml.predict.calibration import apply_calibration
        probs = apply_calibration(probs, model.calibrator)

    # ------------------------------------------------------------------
    # 7. Cold-start blending
    # ------------------------------------------------------------------
    # Horses with fewer than 3 lifetime starts are blended toward an
    # inverse-odds anchor (1/morning_odds normalised) so that market
    # information is preserved when horse history is absent.
    # If no odds are available the anchor degrades to field average.
    raw_odds = np.array([max(r["morning_odds"], 1.0) for r in rows])
    inv_odds = 1.0 / raw_odds
    anchor = inv_odds / inv_odds.sum()   # normalised inverse-odds

    blended = np.array([
        min(row["_n_starts"] / 3.0, 1.0) * probs[i]
        + (1 - min(row["_n_starts"] / 3.0, 1.0)) * anchor[i]
        for i, row in enumerate(rows)
    ])
    blended = blended / blended.sum()

    # ------------------------------------------------------------------
    # 8. Build HorsePrediction list
    # ------------------------------------------------------------------
    horse_name_map = {
        hid: h.name for hid, h in horses.items()
    }

    predictions: list[HorsePrediction] = []
    for i, (entry, row) in enumerate(zip(entries, rows)):
        win_prob = float(blended[i])
        place_prob = float(min(win_prob * 3.0, 0.99))
        predictions.append(
            HorsePrediction(
                horse_id=entry.horse_id,
                horse_name=horse_name_map.get(
                    entry.horse_id, f"horse_{entry.horse_id}"
                ),
                program_number=entry.program_number,
                win_probability=win_prob,
                place_probability=place_prob,
                model_versions={"track": race.track, "version": model_version},
                features_snapshot={
                    k: v for k, v in row.items() if not k.startswith("_")
                },
                computed_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )

    predictions.sort(key=lambda x: x.win_probability, reverse=True)

    # ------------------------------------------------------------------
    # 9. Persist to race_predictions (best-effort; don't fail on error)
    # ------------------------------------------------------------------
    try:
        await _upsert_predictions(session, race_id, predictions, model_version)
    except Exception as exc:
        logger.warning("Failed to upsert predictions for race_id=%s: %s", race_id, exc)

    return predictions
