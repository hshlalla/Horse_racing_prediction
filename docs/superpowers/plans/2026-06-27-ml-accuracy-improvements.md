# ML Accuracy Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix train/serve feature skew, wire isotonic calibration end-to-end, replace the HistGBM pointwise model with a proper LGBMRanker, enable cold-start blending, fix the backtest N+1 query pattern, and remove dead code.

**Architecture:** Five independent or lightly-chained tasks. Tasks 1, 4, and 5 are fully independent. Task 2 (calibration wiring) and Task 3 (inference feature fix + cold-start) both modify `service.py` — run Task 2 first, then Task 3 applies its edits on top. All changes are backward-compatible: if no production model exists, inference degrades gracefully.

**Tech Stack:** Python 3.9+, FastAPI, async SQLAlchemy, scikit-learn (IsotonicRegression), lightgbm (LGBMRanker), CatBoost (YetiRank), scipy, pandas, pytest

## Global Constraints

- Python 3.9+ — no 3.10+ match/case syntax
- `lightgbm>=4.0.0` is already in `pyproject.toml` — do NOT add it again
- Tests run with `uv run pytest` from `backend/` directory
- Async SQLAlchemy sessions for all request-time DB operations
- All rolling stats use `.shift(1)` before groupby — no future data leakage
- No new pip packages beyond what is already in `pyproject.toml`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/ml/train/models/lgbm_binary.py` | Modify | Replace HistGBM with LGBMRanker (lambdarank) |
| `backend/app/ml/train/pipeline.py` | Modify | Fit calibrator on val set, attach to ensemble before promote |
| `backend/app/ml/predict/service.py` | Modify (Task 2) | Load + apply calibrator per race after softmax |
| `backend/app/ml/predict/service.py` | Modify (Task 3) | Add `_get_win_rate()`, replace hardcoded 0.0 values, enable cold-start |
| `backend/app/ml/train/backtest_roi.py` | Modify | Batch predict via dataset + model instead of per-race async queries |
| `backend/app/ml/train/evaluate.py` | Modify | Raise fractional Kelly from 0.1 to 0.25 |
| `backend/app/ml/predict/feature_extractor.py` | Delete | Dead code — never imported, old model path |
| `backend/tests/ml/test_models.py` | Modify | Add LGBMRanker test |
| `backend/tests/ml/test_calibration.py` | Extend | Add pipeline integration test |
| `backend/tests/ml/test_predict_service.py` | Extend | Add win-rate query test |

---

## Task 1: Replace HistGBM with LGBMRanker

**Files:**
- Modify: `backend/app/ml/train/models/lgbm_binary.py`
- Modify: `backend/tests/ml/test_models.py`

**Interfaces:**
- Produces: `train_lgbm(train_df, val_df, features, target) -> ModelShim` — same signature as before. `ModelShim.predict(X: pd.DataFrame) -> np.ndarray` returns ranking scores (higher = better). `race_id` column must be present in both DataFrames.

**Context:** The file is misleadingly named `lgbm_binary.py` but currently uses `sklearn.ensemble.HistGradientBoostingRegressor` with `loss='squared_error'` — a pointwise regression, not a ranking model. LightGBM is already installed (`lightgbm>=4.0.0` in `pyproject.toml`). Replacing with `LGBMRanker(objective='lambdarank')` makes this a proper listwise ranker like the CatBoostRanker counterpart.

- [ ] **Step 1: Extend the test file with a failing LGBMRanker test**

Open `backend/tests/ml/test_models.py`. The `small_dataset` fixture and existing tests are already there. Add:

```python
def test_train_lgbm_is_ranker(small_dataset):
    """LGBMRanker must produce per-horse scores, one per row."""
    from app.ml.train.models.lgbm_binary import train_lgbm
    import numpy as np
    train, val, features, target = small_dataset
    # Verify race_id is present (required for group construction)
    assert 'race_id' in train.columns
    model = train_lgbm(train, val, features, target)
    preds = model.predict(val[features])
    assert len(preds) == len(val)
    assert not np.any(np.isnan(preds))
    # Scores must not all be identical (a pointwise model can produce all-same scores)
    assert preds.std() > 0
```

- [ ] **Step 2: Run to verify it fails (or the existing test fails after the replacement)**

```bash
cd backend
uv run pytest tests/ml/test_models.py::test_train_lgbm_is_ranker -v
```

Expected: `ImportError` or `AssertionError` (std > 0 may pass on current HistGBM, but we're establishing the spec).

- [ ] **Step 3: Replace `lgbm_binary.py`**

Overwrite `backend/app/ml/train/models/lgbm_binary.py` with:

```python
import lightgbm as lgb
import numpy as np
import pandas as pd


class ModelShim:
    def __init__(self, m):
        self.m = m
        self.calibrator = None  # attached by training pipeline after calibration fit

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.m.predict(X)


def train_lgbm(train_df: pd.DataFrame, val_df: pd.DataFrame,
               features: list, target: str) -> ModelShim:
    """
    Train a LGBMRanker (LambdaRank) on race data.
    group_id is race_id — the model learns to rank horses within each race.
    Returns a ModelShim with .predict(X) -> np.ndarray of ranking scores.
    """
    # Sort by race so groups are contiguous
    train_df = train_df.sort_values("race_id").copy()
    val_df = val_df.sort_values("race_id").copy()

    cat_features = ["jockey_id", "trainer_id", "horse_sex", "track",
                    "track_condition", "weather"]
    cat_in_use = [c for c in cat_features if c in features]

    X_train = train_df[features].copy()
    y_train = train_df[target].values
    # group = number of horses per race, in race order
    train_groups = (
        train_df.groupby("race_id", sort=False)["race_id"].count().values
    )

    X_val = val_df[features].copy()
    y_val = val_df[target].values
    val_groups = (
        val_df.groupby("race_id", sort=False)["race_id"].count().values
    )

    for c in cat_in_use:
        X_train[c] = X_train[c].astype("category")
        X_val[c] = X_val[c].astype("category")

    model = lgb.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=5,
        random_state=42,
        verbose=-1,
    )
    model.fit(
        X_train, y_train,
        group=train_groups,
        eval_set=[(X_val, y_val)],
        eval_group=[val_groups],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=-1),
        ],
    )
    return ModelShim(model)
```

- [ ] **Step 4: Run all model tests**

```bash
cd backend
uv run pytest tests/ml/test_models.py -v
```

Expected: all tests pass (including the new `test_train_lgbm_is_ranker`). Training is fast (small dataset).

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/train/models/lgbm_binary.py backend/tests/ml/test_models.py
git commit -m "feat: replace HistGBM pointwise with LGBMRanker (lambdarank)"
```

---

## Task 2: Wire Calibration — Training Pipeline Saves Calibrator, Service Applies It

**Files:**
- Modify: `backend/app/ml/train/pipeline.py`
- Modify: `backend/app/ml/predict/service.py`
- Extend: `backend/tests/ml/test_calibration.py`

**Interfaces:**
- `calibration.fit_calibration(raw_probs: np.ndarray, y_binary: np.ndarray) -> IsotonicRegression` — already exists in `backend/app/ml/predict/calibration.py`
- `calibration.apply_calibration(raw_probs: np.ndarray, calibrator) -> np.ndarray` — already exists
- After this task: any `ModelShim` or `EnsembleShim` returned by `promote.load_production_model()` may have a `.calibrator` attribute (IsotonicRegression or None). Service code must handle both.

**Context:** `calibration.py` is fully implemented and tested but nothing calls it. The training pipeline in `pipeline.py` builds an ensemble, computes val metrics, and calls `promote_if_better`. We need to fit a calibrator on the val set right after the ensemble is built, then attach it as `ensemble.calibrator` before saving the pickle. In `service.py`, after `probs = softmax(raw_scores)`, check for the attached calibrator and apply it.

- [ ] **Step 1: Add a calibration integration test**

Add to `backend/tests/ml/test_calibration.py`:

```python
def test_calibrator_round_trips_through_pickle():
    """Calibrator attached to a model survives pickle serialize/deserialize."""
    import pickle, numpy as np
    from app.ml.predict.calibration import fit_calibration, apply_calibration

    class FakeModel:
        calibrator = None
        def predict(self, X):
            return np.ones(len(X))

    raw = np.array([0.7, 0.2, 0.1])
    y   = np.array([1, 0, 0])
    cal = fit_calibration(raw, y)

    m = FakeModel()
    m.calibrator = cal

    m2 = pickle.loads(pickle.dumps(m))
    assert m2.calibrator is not None
    out = apply_calibration(raw, m2.calibrator)
    assert abs(out.sum() - 1.0) < 1e-6
```

- [ ] **Step 2: Run to verify it passes (calibrator is already serializable)**

```bash
cd backend
uv run pytest tests/ml/test_calibration.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 3: Modify `pipeline.py` to fit and attach calibrator**

Read `backend/app/ml/train/pipeline.py`. Find the block that calls `build_ensemble(...)` and `promote_if_better(...)`. Insert the calibration block **between** them:

```python
# After: ensemble = build_ensemble([model_a, model_b], track_val, features, target)
# Insert before promote_if_better:

from app.ml.predict.calibration import fit_calibration
from scipy.special import softmax as _softmax

_val_probs: list[float] = []
_val_wins: list[int] = []
for _, _race in track_val.groupby("race_id"):
    _scores = ensemble.predict(_race[features])
    _p = _softmax(_scores)
    _val_probs.extend(_p.tolist())
    _val_wins.extend(
        (_race["finish_position"] == 1).astype(int).tolist()
    )

if len(set(_val_wins)) == 2:   # need both classes to fit isotonic
    ensemble.calibrator = fit_calibration(
        np.array(_val_probs), np.array(_val_wins)
    )
else:
    ensemble.calibrator = None
```

Note: `ensemble` here is the `EnsembleShim` returned by `build_ensemble`. `EnsembleShim` does not define `__slots__`, so Python allows setting arbitrary attributes on it.

- [ ] **Step 4: Modify `service.py` to apply calibrator**

In `backend/app/ml/predict/service.py`, find section **6. Model inference** (around line 453). After the `probs = softmax(raw_scores)` block, insert:

```python
    # Apply isotonic calibration if the model has one
    if getattr(model, "calibrator", None) is not None:
        from app.ml.predict.calibration import apply_calibration
        probs = apply_calibration(probs, model.calibrator)
```

The full block should become (replace the existing section 6):

```python
    # ------------------------------------------------------------------
    # 6. Model inference
    # ------------------------------------------------------------------
    pred_df = pd.DataFrame(rows)
    for col in ("horse_sex", "track", "track_condition", "weather"):
        pred_df[col] = pred_df[col].astype("category")

    raw_scores = model.predict(pred_df[FEATURES])

    if np.isclose(np.sum(raw_scores), 1.0, atol=0.1):
        probs = raw_scores
    else:
        probs = softmax(raw_scores)

    if getattr(model, "calibrator", None) is not None:
        from app.ml.predict.calibration import apply_calibration
        probs = apply_calibration(probs, model.calibrator)
```

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/ml/test_calibration.py tests/ml/test_predict_service.py -v
```

Expected: all pass. (The predict_service test mocks `_get_model` so calibrator is None — the `getattr` guard handles that silently.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/ml/train/pipeline.py backend/app/ml/predict/service.py \
        backend/tests/ml/test_calibration.py
git commit -m "feat: fit calibrator on val set in training, apply in predict service"
```

---

## Task 3: Fix Inference Feature Skew + Enable Cold-Start Blending

**Files:**
- Modify: `backend/app/ml/predict/service.py`
- Extend: `backend/tests/ml/test_predict_service.py`

**Interfaces:**
- New helper: `async _get_win_rate(session: AsyncSession, entity_id: int, entity_col: Literal["jockey_id", "trainer_id"], as_of_date: date) -> float`
- Replaces hardcoded `jockey_win_rate=0.0`, `trainer_win_rate=0.0` with real DB-computed EWMA values.
- `sire_win_rate` stays at `0.0` (requires pedigree join not covered here).

**Context:** This task modifies `service.py` which Task 2 already edited. Apply this task AFTER Task 2 is committed. The cold-start blending block at section 7 is currently disabled with a "DISABLED FOR POC" comment — we re-enable it.

- [ ] **Step 1: Add a failing test for win rate lookup**

Add to `backend/tests/ml/test_predict_service.py`:

```python
@pytest.mark.asyncio
async def test_get_win_rate_returns_zero_for_unknown():
    """Unknown jockey with no history should return 0.0."""
    from unittest.mock import AsyncMock, MagicMock
    from app.ml.predict.service import _get_win_rate
    import datetime

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    rate = await _get_win_rate(mock_session, 9999, "jockey_id",
                               datetime.date(2026, 6, 1))
    assert rate == 0.0


@pytest.mark.asyncio
async def test_get_win_rate_returns_float():
    """A jockey with a win should return a positive float."""
    from unittest.mock import AsyncMock, MagicMock
    from app.ml.predict.service import _get_win_rate
    import datetime

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 0.15
    mock_session.execute = AsyncMock(return_value=mock_result)

    rate = await _get_win_rate(mock_session, 1, "jockey_id",
                               datetime.date(2026, 6, 1))
    assert abs(rate - 0.15) < 1e-9
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend
uv run pytest tests/ml/test_predict_service.py -k "win_rate" -v
```

Expected: `ImportError: cannot import name '_get_win_rate'`

- [ ] **Step 3: Add `_get_win_rate` to `service.py`**

In `backend/app/ml/predict/service.py`, add this function after `_get_horse_history` (around line 229):

```python
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
    from app.db.models.crawl import RaceEntry

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
```

- [ ] **Step 4: Replace hardcoded 0.0 win rates and enable cold-start**

In `service.py` section 5 (Build feature rows, around line 412), change the per-entry loop body. Replace:

```python
        row: dict = {
            ...
            "jockey_win_rate": 0.0,
            "trainer_win_rate": 0.0,
            "sire_win_rate": 0.0,
            ...
```

with:

```python
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

        row: dict = {
            ...
            "jockey_win_rate": jockey_win_rate,
            "trainer_win_rate": trainer_win_rate,
            "sire_win_rate": 0.0,   # requires pedigree join; kept at 0
            ...
```

(Keep every other key in `row` exactly as is — only the three win_rate lines change.)

Then in section 7 (Cold-start blending), **replace the disabled block** with the active version:

```python
    # ------------------------------------------------------------------
    # 7. Cold-start blending
    # ------------------------------------------------------------------
    # Horses with fewer than 3 lifetime starts are blended toward the
    # field-average probability to avoid over-confident predictions.
    field_avg = 1.0 / len(probs)
    blended = np.array([
        min(row["_n_starts"] / 3.0, 1.0) * probs[i]
        + (1 - min(row["_n_starts"] / 3.0, 1.0)) * field_avg
        for i, row in enumerate(rows)
    ])
    blended = blended / blended.sum()
```

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/ml/test_predict_service.py -v
```

Expected: all tests pass. The existing `test_predict_race_returns_horse_predictions` mocks `_get_model` and `session.execute`, so the new win-rate calls hit the same mock and return the configured value.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ml/predict/service.py backend/tests/ml/test_predict_service.py
git commit -m "feat: compute real jockey/trainer win rates at inference, enable cold-start blending"
```

---

## Task 4: Fix Backtest N+1 Queries + Kelly Parameters

**Files:**
- Modify: `backend/app/ml/train/backtest_roi.py`
- Modify: `backend/app/ml/train/evaluate.py`

**Interfaces:**
- `backtest_roi.run_backtest(db_url: str) -> None` — now takes a sync Postgres URL, loads data in one batch query, applies model offline. No longer requires an async session.
- `evaluate.evaluate_test_set(model, test_df, features)` — fractional Kelly factor raised from 0.1 to 0.25.

**Context:** `backtest_roi.py` currently calls `await predict_race(session, race.id)` inside a `for` loop over hundreds of races, each call doing N async queries per horse. This is extremely slow. The fix loads the full feature matrix via `load_dataset_pg` and calls `model.predict()` once per race in pandas — same result, hundreds of times faster. `evaluate.py` uses `kelly_f_win * 0.1` (tenth-Kelly) which is overly conservative; quarter-Kelly (`* 0.25`) is standard.

- [ ] **Step 1: Fix Kelly parameters in `evaluate.py`**

In `backend/app/ml/train/evaluate.py`, find lines:

```python
        bet_frac_win = max(0, min(0.1, kelly_f_win * 0.1))
```

and

```python
        bet_frac_place = max(0, min(0.1, kelly_f_place * 0.1))
```

Replace both with quarter-Kelly (25% of full Kelly, capped at 25% of bankroll):

```python
        bet_frac_win = max(0, min(0.25, kelly_f_win * 0.25))
```

```python
        bet_frac_place = max(0, min(0.25, kelly_f_place * 0.25))
```

- [ ] **Step 2: Rewrite `backtest_roi.py` with batch prediction**

Replace the entire contents of `backend/app/ml/train/backtest_roi.py`:

```python
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
```

- [ ] **Step 3: Run existing tests to confirm nothing is broken**

```bash
cd backend
uv run pytest tests/ml/ -q
```

Expected: all non-Docker tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/ml/train/backtest_roi.py backend/app/ml/train/evaluate.py
git commit -m "fix: batch backtest prediction, raise Kelly fraction from 0.1 to 0.25"
```

---

## Task 5: Remove Dead Code

**Files:**
- Delete: `backend/app/ml/predict/feature_extractor.py`

**Context:** `feature_extractor.py` is the old pre-v2 prediction approach. It hard-codes the model path to `models/catboost_ranker.cbm` (the old single-file format), uses simple averages instead of EWMA, and is not imported anywhere. Keeping it confuses future developers.

- [ ] **Step 1: Verify nothing imports it**

```bash
cd backend
grep -r "feature_extractor" . --include="*.py" | grep -v "__pycache__"
```

Expected: zero results (the file imports itself, but no other file does).

- [ ] **Step 2: Delete the file**

```bash
rm backend/app/ml/predict/feature_extractor.py
```

- [ ] **Step 3: Run tests to confirm nothing broke**

```bash
cd backend
uv run pytest tests/ -q --ignore=tests/api/test_auth.py --ignore=tests/api/test_contract.py \
    --ignore=tests/db/ --ignore=tests/ml/test_dataset_pg.py
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove dead feature_extractor.py (old pre-v2 inference code)"
```

---

## Self-Review

### Spec Coverage

| Improvement | Task |
|---|---|
| Replace HistGBM with LGBMRanker | Task 1 |
| Wire calibration end-to-end | Task 2 |
| Fix jockey/trainer win rate skew | Task 3 |
| Enable cold-start blending | Task 3 |
| Fix backtest N+1 queries | Task 4 |
| Fix Kelly fraction (0.1→0.25) | Task 4 |
| Remove dead `feature_extractor.py` | Task 5 |

All seven improvements are covered. `sire_win_rate` is explicitly left at 0.0 with a note (requires pedigree join not in scope).

### Dependency Note

Tasks 2 and 3 both modify `service.py`. They must be executed **in order**: Task 2 first, then Task 3. All other tasks are independent of each other and of Tasks 2–3.

### Type Consistency Check

- `train_lgbm` still returns `ModelShim` with `.predict(X: pd.DataFrame) -> np.ndarray` ✓
- `ModelShim` gains a `calibrator = None` attribute — backward compatible ✓
- `EnsembleShim` gains `ensemble.calibrator` dynamically — Python allows this on instances without `__slots__` ✓
- `_get_win_rate(session, entity_id, entity_col, as_of_date) -> float` — all three call sites in Task 3 match ✓
- `run_backtest()` changes signature to require `DATABASE_URL` env var instead of no args — no callers to update ✓
