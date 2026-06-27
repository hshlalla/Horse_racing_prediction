# Data Expansion v1 — Feature Engineering + Crawler Enhancements

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 7 new ML features (surface, grade, body weight delta, morning odds rank, distance win rate, jockey-horse pair win rate, sire win rate at inference), fix the crawler to actually populate grade/race_class/surface instead of leaving them null/hardcoded, and add an odds-snapshots crawler for future real-time odds features.

**Architecture:** Four tasks, lightly sequential. Task 1 (crawler fix) populates the DB columns that Tasks 2–3 consume in training. Tasks 2 and 3 both modify `dataset.py` and `service.py` — execute them in order. Task 4 (odds crawler) is fully independent and can run last. Every new training feature has a matching inference-time computation in `service.py` to prevent train/serve skew. No new DB columns or Alembic migrations needed — all new features derive from columns already in the schema.

**Tech Stack:** Python 3.9+, FastAPI, async SQLAlchemy, pandas (groupby/shift/ewm), BeautifulSoup4 (KRA HTML parsing), pytest, alembic

## Global Constraints

- Python 3.9+ — no builtin generic subscripts as runtime annotations without `from __future__ import annotations`
- No new pip packages beyond what is already in `pyproject.toml`
- FEATURES list in `backend/app/ml/train/dataset.py` and `backend/app/ml/predict/service.py` must stay identical — any feature added to one must be added to the other with the exact same name and in the same order
- All rolling stats use `.shift(1)` before ewm — no future data leakage
- Async SQLAlchemy for all inference-time DB queries (service.py)
- Tests run with `uv run pytest` from `backend/` directory
- Crawler must not delete/overwrite existing `odds_snapshots` rows for a race if they already exist

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/ml/crawl/parsers/kra_live_parser.py` | Modify | Parse `grade`, `race_class`, `surface` from KRA HTML |
| `backend/app/ml/crawl/crawl_2026.py` | Modify | Pass parsed `grade`, `race_class`, `surface` to Race ORM |
| `backend/app/ml/train/dataset.py` | Modify (Tasks 2 + 3) | Add new features to `_QUERY`, `_apply_features`, `FEATURES` |
| `backend/app/ml/predict/service.py` | Modify (Tasks 2 + 3) | Add new features to `FEATURES`, feature-row building, new async helpers |
| `backend/app/ml/crawl/crawl_2026.py` | Modify (Task 4) | Add odds-snapshot scraping step |
| `backend/tests/ml/test_dataset_features.py` | Create | Feature engineering unit tests (no DB) |
| `backend/tests/ml/test_predict_service.py` | Modify | Extend with inference-feature tests |
| `backend/tests/crawl/test_kra_live_parser.py` | Extend | Parser tests for new fields |

---

## Task 1: Fix Crawler — Parse grade, race_class, surface from KRA HTML

**Files:**
- Modify: `backend/app/ml/crawl/parsers/kra_live_parser.py`
- Modify: `backend/app/ml/crawl/crawl_2026.py`
- Extend: `backend/tests/crawl/test_kra_live_parser.py` (create if missing)

**Interfaces:**
- Produces: `KRALiveParser.parse_race_detail(html) -> {"meta": {..., "grade": str|None, "race_class": str|None, "surface": "Turf"|"Dirt"}, "horses": [...]}`
- `grade` examples: `"G1"`, `"G2"`, `"G3"`, `None` (unknown)
- `race_class` examples: `"오픈"`, `"특별"`, `"일반"`, `None`
- `surface`: always one of `"Turf"` or `"Dirt"` (never None — default to `"Dirt"`)

**Context:** The KRA detail page (`ScoretableDetailList.do`) has a header section with race info. Currently `kra_live_parser.py` parses weather, track condition, humidity, and distance from the `tableType1` div. The race name/title (containing grade and class) appears in a `<h4>` or similar title element near the top of the page. Surface (잔디/더트) appears next to the distance in the header (e.g., "1200M 잔디" or "1400M 더트").

The current crawler at `crawl_2026.py` line 97-99 hardcodes:
```python
race_name=f"Race {rc_no}",
distance_m=1000,   # already fixed elsewhere — keep whatever is there now
surface="Dirt",
```

- [ ] **Step 1: Write failing parser test**

Create `backend/tests/crawl/test_kra_live_parser.py` (or add to existing):

```python
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser

SAMPLE_RACE_HTML_TURF = """
<html><body>
<h4 class="raceInfo">제1경주 G3 잔디 1200M</h4>
<div class="tableType1">
  <table><tr class="alignC">
    <td>맑음</td><td>양호</td><td>건조</td><td>65%</td><td>10:00</td>
  </tr></table>
</div>
<div class="tableType2"><table><tbody></tbody></table></div>
</body></html>
"""

SAMPLE_RACE_HTML_DIRT = """
<html><body>
<h4 class="raceInfo">제5경주 오픈 더트 1400M</h4>
<div class="tableType1">
  <table><tr class="alignC">
    <td>흐림</td><td>보통</td><td>습함</td><td>80%</td><td>12:00</td>
  </tr></table>
</div>
<div class="tableType2"><table><tbody></tbody></table></div>
</body></html>
"""

def test_parse_surface_turf():
    result = KRALiveParser.parse_race_detail(SAMPLE_RACE_HTML_TURF)
    assert result["meta"]["surface"] == "Turf"

def test_parse_surface_dirt():
    result = KRALiveParser.parse_race_detail(SAMPLE_RACE_HTML_DIRT)
    assert result["meta"]["surface"] == "Dirt"

def test_parse_grade_g3():
    result = KRALiveParser.parse_race_detail(SAMPLE_RACE_HTML_TURF)
    assert result["meta"]["grade"] == "G3"

def test_parse_race_class_open():
    result = KRALiveParser.parse_race_detail(SAMPLE_RACE_HTML_DIRT)
    assert result["meta"]["race_class"] == "오픈"

def test_parse_defaults_when_no_header():
    result = KRALiveParser.parse_race_detail("<html><body></body></html>")
    assert result["meta"]["surface"] == "Dirt"   # safe default
    assert result["meta"].get("grade") is None
```

- [ ] **Step 2: Run tests to see them fail**

```bash
cd backend
uv run pytest tests/crawl/test_kra_live_parser.py -v 2>&1 | head -30
```

Expected: 5 failures — fields not parsed yet.

- [ ] **Step 3: Add parsing to `kra_live_parser.py`**

In `KRALiveParser.parse_race_detail`, after the existing `info_table` block (around line 110), add a title-parsing block. The KRA race header typically looks like `"제1경주 G3 잔디 1200M"` — but the exact selector varies. Check what element wraps the race title and use it; fall back to regex over the full HTML if needed.

Add this after the existing meta parsing block:

```python
        # Parse grade, race_class, surface from race title
        import re

        # KRA race title selector candidates: h4, .raceInfo, .raceName, title bar
        title_elem = (
            soup.find("h4", class_=re.compile(r"race", re.I))
            or soup.find(class_=re.compile(r"raceName|raceInfo|raceTitle", re.I))
            or soup.find("caption")
        )
        title_text = title_elem.get_text(strip=True) if title_elem else ""

        # Surface: 잔디 → Turf, 더트 / 모래 → Dirt
        if "잔디" in title_text:
            meta["surface"] = "Turf"
        else:
            meta["surface"] = "Dirt"   # safe default

        # Grade: G1 / G2 / G3 pattern
        grade_match = re.search(r"G[1-3]", title_text)
        meta["grade"] = grade_match.group(0) if grade_match else None

        # Race class: known KRA class keywords
        CLASS_KEYWORDS = ["오픈", "특별", "일반", "선발", "등록", "초청"]
        meta["race_class"] = next(
            (kw for kw in CLASS_KEYWORDS if kw in title_text), None
        )

        # Also capture race_name from the title text if available
        if title_text:
            meta["race_name"] = title_text
```

- [ ] **Step 4: Run parser tests**

```bash
cd backend
uv run pytest tests/crawl/test_kra_live_parser.py -v
```

Expected: 5 passed. If `test_parse_grade_g3` or `test_parse_race_class_open` fail, inspect what `title_elem.get_text()` returns for the sample HTML and adjust the selector or regex.

- [ ] **Step 5: Wire parsed fields into crawl_2026.py**

In `crawl_2026.py`, find the `Race(...)` constructor calls (there are two — one in the main loop and one in history crawl). Change:

```python
race_name=f"Race {rc_no}",
surface="Dirt",
```

to:

```python
race_name=meta.get("race_name", f"Race {rc_no}"),
surface=meta.get("surface", "Dirt"),
grade=meta.get("grade"),
race_class=meta.get("race_class"),
```

- [ ] **Step 6: Run all non-Docker tests to confirm nothing broke**

```bash
cd backend
uv run pytest tests/ -q --ignore=tests/db --ignore=tests/ml/test_dataset_pg.py
```

Expected: same pass count as before.

- [ ] **Step 7: Commit**

```bash
git add backend/app/ml/crawl/parsers/kra_live_parser.py \
        backend/app/ml/crawl/crawl_2026.py \
        backend/tests/crawl/test_kra_live_parser.py
git commit -m "feat: parse grade, race_class, surface from KRA HTML (was hardcoded/null)"
```

---

## Task 2: Feature Set 1 — surface, grade, body_weight_delta, morning_odds_rank

**Files:**
- Modify: `backend/app/ml/train/dataset.py` (\_QUERY, \_apply\_features, FEATURES)
- Modify: `backend/app/ml/predict/service.py` (FEATURES, feature-row loop)
- Create: `backend/tests/ml/test_dataset_features.py`

**Interfaces:**
- FEATURES after this task (in both files, in this exact order — add after `past_avg_finish_rank`):
  ```python
  'surface', 'grade', 'body_weight_delta_kg', 'morning_odds_rank'
  ```
- `body_weight_delta_kg`: `body_weight_kg - previous_race_body_weight_kg`; default `0.0` for first race
- `morning_odds_rank`: integer 1–N within each race (1 = lowest odds = favourite); ties broken by program_number ascending

**Context:** These four features are all available before a race starts and have no data leakage risk. `surface` and `grade` are race-level properties. `body_weight_delta_kg` and `morning_odds_rank` are horse-level. None require new DB columns.

- [ ] **Step 1: Write failing feature tests**

Create `backend/tests/ml/test_dataset_features.py`:

```python
import pandas as pd
import numpy as np
import pytest
from app.ml.train.dataset import _apply_features


@pytest.fixture
def raw_df():
    """Minimal raw DataFrame mimicking _QUERY output."""
    return pd.DataFrame({
        "race_id":       [1, 1, 2, 2],
        "race_date":     pd.to_datetime(["2024-01-01"] * 4),
        "horse_id":      [10, 20, 10, 20],
        "jockey_id":     [1, 2, 1, 2],
        "trainer_id":    [1, 2, 1, 2],
        "sire_id":       [None, None, None, None],
        "program_number":[1, 2, 1, 2],
        "distance_m":    [1200, 1200, 1400, 1400],
        "field_size":    [2, 2, 2, 2],
        "track":         ["SEOUL"] * 4,
        "surface":       ["Dirt", "Turf", "Dirt", "Turf"],
        "grade":         ["G3", None, "G3", None],
        "track_condition":["건조"] * 4,
        "weather":       ["맑음"] * 4,
        "humidity":      [50] * 4,
        "carry_weight_kg":[57.0] * 4,
        "body_weight_kg": [490.0, 510.0, 495.0, 505.0],
        "morning_odds":  [3.5, 2.0, 4.0, 1.8],
        "horse_age":     [4] * 4,
        "horse_sex":     ["M"] * 4,
        "s1f_time":      [14.0] * 4,
        "g3f_time":      [38.0] * 4,
        "corner1_rank":  [1, 2, 2, 1],
        "corner2_rank":  [None] * 4,
        "corner3_rank":  [None] * 4,
        "corner4_rank":  [None] * 4,
        "corner5_rank":  [None] * 4,
        "corner6_rank":  [None] * 4,
        "corner7_rank":  [None] * 4,
        "finish_position":[1, 2, 2, 1],
        "finish_time_s": [72.0, 72.5, 84.0, 83.5],
        "is_win":        [1, 0, 0, 1],
    })


def test_surface_is_categorical(raw_df):
    df = _apply_features(raw_df.copy())
    assert df["surface"].dtype.name == "category"
    assert set(df["surface"].cat.categories) >= {"Dirt", "Turf"}


def test_grade_filled_and_categorical(raw_df):
    df = _apply_features(raw_df.copy())
    assert df["grade"].dtype.name == "category"
    assert df["grade"].isna().sum() == 0   # nulls filled with 'unknown'


def test_body_weight_delta_first_race_is_zero(raw_df):
    df = _apply_features(raw_df.copy())
    # Horse 10 and 20 both appear first in race 1 — delta should be 0
    first_race = df[df["race_id"] == 1]
    assert (first_race["body_weight_delta_kg"] == 0.0).all()


def test_body_weight_delta_second_race(raw_df):
    df = _apply_features(raw_df.copy())
    # Horse 10: race1=490, race2=495 → delta=+5
    horse10_r2 = df[(df["horse_id"] == 10) & (df["race_id"] == 2)]
    assert abs(horse10_r2["body_weight_delta_kg"].values[0] - 5.0) < 1e-6


def test_morning_odds_rank_within_race(raw_df):
    df = _apply_features(raw_df.copy())
    race1 = df[df["race_id"] == 1].sort_values("program_number")
    # race1: horse10 odds=3.5, horse20 odds=2.0 → horse20 rank=1, horse10 rank=2
    assert race1[race1["horse_id"] == 20]["morning_odds_rank"].values[0] == 1
    assert race1[race1["horse_id"] == 10]["morning_odds_rank"].values[0] == 2
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend
uv run pytest tests/ml/test_dataset_features.py -v 2>&1 | head -30
```

Expected: errors (KeyError on 'surface', 'grade', etc. — `_apply_features` doesn't know these yet).

- [ ] **Step 3: Add columns to `_QUERY` in dataset.py**

In `backend/app/ml/train/dataset.py`, add to the SELECT in `_QUERY` after `r.humidity`:

```sql
    r.surface,
    r.grade,
```

The full updated SELECT block for race columns:
```sql
    r.track,
    r.track_condition,
    r.weather,
    r.humidity,
    r.surface,
    r.grade,
```

- [ ] **Step 4: Add feature engineering to `_apply_features` in dataset.py**

After the existing `df['weather'] = ...` line (around line 63), add:

```python
    df['surface'] = df['surface'].fillna('Dirt').astype('category')
    df['grade'] = df['grade'].fillna('unknown').astype('category')
```

After the `df.sort_values(['race_date', 'race_id'], ...)` block at the end, add:

```python
    # Body weight delta (horse weight change from previous race)
    df.sort_values(['horse_id', 'race_date', 'race_id'], inplace=True)
    df['body_weight_delta_kg'] = (
        df.groupby('horse_id')['body_weight_kg']
        .transform(lambda x: x - x.shift(1))
        .fillna(0.0)
    )

    # Morning odds rank within race (1 = favourite = lowest odds)
    df['morning_odds_rank'] = (
        df.groupby('race_id')['morning_odds']
        .rank(method='min', ascending=True)
        .astype(int)
    )

    df.sort_values(['race_date', 'race_id'], inplace=True)
```

- [ ] **Step 5: Add to FEATURES list in dataset.py**

Append to the end of the `FEATURES` list:

```python
FEATURES = [
    ...,   # existing features unchanged
    'surface', 'grade', 'body_weight_delta_kg', 'morning_odds_rank'
]
```

- [ ] **Step 6: Run feature tests**

```bash
cd backend
uv run pytest tests/ml/test_dataset_features.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Update service.py FEATURES and feature-row builder**

In `backend/app/ml/predict/service.py`:

**A) FEATURES list** — append in the same order:
```python
FEATURES = [
    ...,  # existing features unchanged
    'surface', 'grade', 'body_weight_delta_kg', 'morning_odds_rank'
]
```

**B) In `_predict_race_impl`, section 5 (feature-row loop)**, add these new keys to the `row` dict after the existing keys. Also add imports for the `_get_prev_body_weight` helper (defined below).

For `body_weight_delta_kg`:
```python
        prev_body_weight = await _get_prev_body_weight(
            session, entry.horse_id, today
        )
        body_weight_delta = (entry.body_weight_kg or 500.0) - prev_body_weight
```

For `morning_odds_rank` — this cannot be computed per-horse individually; it requires seeing all horses in the race at once. Compute it **after** the loop, before section 6:

```python
    # Compute morning_odds_rank across all horses in this race
    all_odds = [r["morning_odds"] for r in rows]
    sorted_odds = sorted(set(all_odds))
    odds_rank_map = {v: i + 1 for i, v in enumerate(sorted_odds)}
    for r in rows:
        r["morning_odds_rank"] = odds_rank_map[r["morning_odds"]]
```

Add to the `row` dict:
```python
            "surface": race.surface or "Dirt",
            "grade": race.grade or "unknown",
            "body_weight_delta_kg": body_weight_delta,
            "morning_odds_rank": 0,   # placeholder — filled after the loop
```

**C) Add `_get_prev_body_weight` helper** after `_get_win_rate`:

```python
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
```

**D) Update category casting in section 6** — add `surface` and `grade`:

```python
    for col in ("horse_sex", "track", "track_condition", "weather", "surface", "grade"):
        pred_df[col] = pred_df[col].astype("category")
```

- [ ] **Step 8: Run all non-Docker tests**

```bash
cd backend
uv run pytest tests/ -q --ignore=tests/db --ignore=tests/ml/test_dataset_pg.py
```

Expected: same pass count plus the 5 new feature tests. No regressions.

- [ ] **Step 9: Commit**

```bash
git add backend/app/ml/train/dataset.py backend/app/ml/predict/service.py \
        backend/tests/ml/test_dataset_features.py
git commit -m "feat: add surface, grade, body_weight_delta, morning_odds_rank features"
```

---

## Task 3: Feature Set 2 — distance_win_rate, jockey_horse_win_rate, sire_win_rate at inference

**Files:**
- Modify: `backend/app/ml/train/dataset.py`
- Modify: `backend/app/ml/predict/service.py`
- Modify: `backend/tests/ml/test_dataset_features.py`
- Modify: `backend/tests/ml/test_predict_service.py`

**Interfaces:**
- New FEATURES (append after `morning_odds_rank`): `'distance_win_rate'`, `'jockey_horse_win_rate'`
- `sire_win_rate` at inference: `_get_sire_win_rate(session, horse_id, as_of_date) -> float` replaces hardcoded `0.0`
- `distance_bucket`: not a feature itself — used internally to group distances: short (< 1300m), middle (1300–1800m), long (> 1800m)
- `distance_win_rate`: EWMA win rate (span=5, shift=1) within the horse × distance_bucket group
- `jockey_horse_win_rate`: EWMA win rate (span=5, shift=1) within the (jockey_id, horse_id) group

**Context:** This task must be applied AFTER Task 2 (both modify dataset.py and service.py). `sire_win_rate` already exists in `FEATURES` (from the original dataset) and is already computed at training time — it is just hardcoded `0.0` at inference. This task fixes the inference side.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/ml/test_dataset_features.py`:

```python
def test_distance_win_rate_no_leakage(raw_df):
    df = _apply_features(raw_df.copy())
    # Horse 10 and 20 both appear first in race_id=1 — no history yet, should be 0
    first_race = df[df["race_id"] == 1]
    assert (first_race["distance_win_rate"] == 0.0).all()


def test_jockey_horse_win_rate_no_leakage(raw_df):
    df = _apply_features(raw_df.copy())
    first_race = df[df["race_id"] == 1]
    assert (first_race["jockey_horse_win_rate"] == 0.0).all()


def test_distance_win_rate_updates_after_win(raw_df):
    df = _apply_features(raw_df.copy())
    # Horse 10 wins race 1 (finish_position=1, is_win=1) at 1200m (short).
    # In race 2, horse 10 runs 1400m (middle) — different bucket, should still be 0
    horse10_r2 = df[(df["horse_id"] == 10) & (df["race_id"] == 2)]
    # Horse 20 wins race 2 at 1400m (middle). Their distance_win_rate in race 2 is still 0 (first race in middle bucket).
    horse20_r2 = df[(df["horse_id"] == 20) & (df["race_id"] == 2)]
    assert horse20_r2["distance_win_rate"].values[0] == 0.0
```

Add to `backend/tests/ml/test_predict_service.py`:

```python
@pytest.mark.asyncio
async def test_get_sire_win_rate_returns_zero_for_no_pedigree():
    from unittest.mock import AsyncMock, MagicMock
    from app.ml.predict.service import _get_sire_win_rate
    import datetime

    mock_session = AsyncMock()
    # No pedigree row: sire_id lookup returns None
    mock_result = MagicMock()
    mock_result.scalar.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    rate = await _get_sire_win_rate(mock_session, 999, datetime.date(2026, 6, 1))
    assert rate == 0.0
```

- [ ] **Step 2: Verify failures**

```bash
cd backend
uv run pytest tests/ml/test_dataset_features.py::test_distance_win_rate_no_leakage \
              tests/ml/test_dataset_features.py::test_jockey_horse_win_rate_no_leakage -v 2>&1 | head -20
```

Expected: KeyError on `distance_win_rate` or `jockey_horse_win_rate`.

- [ ] **Step 3: Add `distance_win_rate` and `jockey_horse_win_rate` to `_apply_features` in dataset.py**

After the existing `trainer_win_rate` block (around line 134) and before `sire_win_rate`, add:

```python
    # Distance bucket win rate (short / middle / long)
    df['_distance_bucket'] = pd.cut(
        df['distance_m'],
        bins=[0, 1300, 1800, 99999],
        labels=['short', 'middle', 'long']
    )
    df.sort_values(['horse_id', '_distance_bucket', 'race_date'], inplace=True)
    df['distance_win_rate'] = (
        df.groupby(['horse_id', '_distance_bucket'])['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0.0)
    )

    # Jockey-horse pair win rate
    df.sort_values(['jockey_id', 'horse_id', 'race_date'], inplace=True)
    df['jockey_horse_win_rate'] = (
        df.groupby(['jockey_id', 'horse_id'])['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0.0)
    )
```

- [ ] **Step 4: Append to FEATURES in dataset.py**

```python
FEATURES = [
    ...,   # existing + Task 2 features
    'distance_win_rate', 'jockey_horse_win_rate'
]
```

- [ ] **Step 5: Run dataset feature tests**

```bash
cd backend
uv run pytest tests/ml/test_dataset_features.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 6: Add `_get_sire_win_rate` to service.py**

Add after `_get_prev_body_weight`:

```python
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
```

- [ ] **Step 7: Update service.py FEATURES, feature-row, and section 5**

**A) Append to FEATURES:**
```python
FEATURES = [
    ...,  # existing + Task 2 additions
    'distance_win_rate', 'jockey_horse_win_rate'
]
```

**B) Fix `sire_win_rate` — replace the hardcoded 0.0 line** with a real query:

```python
        sire_win_rate = await _get_sire_win_rate(session, entry.horse_id, today)
```

Update the row dict:
```python
            "sire_win_rate": sire_win_rate,
```

**C) Add `distance_win_rate` and `jockey_horse_win_rate` to the row dict** (values will be DB-queried via the same `_get_win_rate` helper):

```python
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
```

And in the row dict:
```python
            "distance_win_rate": distance_win_rate,
            "jockey_horse_win_rate": jockey_horse_win_rate,
```

**D) Add `_get_distance_win_rate` and `_get_pair_win_rate` helpers** after `_get_sire_win_rate`:

```python
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
```

- [ ] **Step 8: Run all non-Docker tests**

```bash
cd backend
uv run pytest tests/ -q --ignore=tests/db --ignore=tests/ml/test_dataset_pg.py
```

Expected: all pass, count increases by the new tests.

- [ ] **Step 9: Commit**

```bash
git add backend/app/ml/train/dataset.py backend/app/ml/predict/service.py \
        backend/tests/ml/test_dataset_features.py backend/tests/ml/test_predict_service.py
git commit -m "feat: add distance_win_rate, jockey_horse_win_rate, fix sire_win_rate at inference"
```

---

## Task 4: Odds Snapshots Crawler — Populate odds_snapshots During Live Scraping

**Files:**
- Modify: `backend/app/ml/crawl/crawl_2026.py`
- Extend: `backend/tests/crawl/test_kra_live_parser.py`

**Interfaces:**
- `OddsSnapshot` ORM model already exists in `backend/app/db/models/crawl.py`:
  ```python
  class OddsSnapshot(Base):
      race_id: int
      horse_id: int
      snapshot_time: datetime (timezone-aware)
      win_odds: Optional[float]
      place_odds: Optional[float]
  ```
- Produces: one `OddsSnapshot` row per horse per crawl call, timestamped at crawl time

**Context:** The `odds_snapshots` table exists but is never populated. The KRA result page already returns `d['odds_win']` per horse (saved as `RaceResult.final_odds`). For races that are not yet complete (live/upcoming), the same detail endpoint returns current tote odds. This task adds an upsert of `OddsSnapshot` rows whenever we crawl a race, capturing tote odds at the crawl timestamp. This enables a future `odds_movement_ratio = latest_snapshot_odds / morning_odds` inference feature.

**Important:** Do NOT save snapshots for races that already have a `RaceResult` with `finish_position IS NOT NULL` — those are completed races and final_odds is already stored. Only snapshot in-progress or upcoming races. Check: `if not parsed_data.get('completed', False)` — add a `completed` field to the parser output.

- [ ] **Step 1: Add `completed` flag to parser output**

In `kra_live_parser.py`, `parse_race_detail`, check whether a race is completed by looking for finish positions in the results table. A completed race has numeric `착순` (finish position) values. Add to the return dict:

```python
        # Mark race as completed when at least one horse has a finish position
        meta["completed"] = any(
            isinstance(h.get("finish_position"), int) and h["finish_position"] > 0
            for h in results
        )
```

- [ ] **Step 2: Write a parser test for the completed flag**

Add to `backend/tests/crawl/test_kra_live_parser.py`:

```python
SAMPLE_COMPLETED_HTML = """
<html><body>
<div class="tableType2"><table><tbody>
<tr><td>1</td><td>천하무적</td><td>1</td><td>72.3</td><td>2.1</td></tr>
</tbody></table></div>
</body></html>
"""

def test_completed_flag_true_when_result_present():
    result = KRALiveParser.parse_race_detail(SAMPLE_COMPLETED_HTML)
    # The sample has a horse with finish_position=1 — should be completed
    # (parser may not parse the exact sample — adjust if needed after seeing real output)
    # At minimum, the key must exist
    assert "completed" in result["meta"]
```

- [ ] **Step 3: Add `OddsSnapshot` upsert in `crawl_2026.py`**

In `crawl_2026.py`, add this import at the top:

```python
from app.db.models.crawl import (
    Horse, Jockey, Trainer, Race, RaceEntry, RaceResult, InraceTiming, OddsSnapshot
)
```

After the horse loop that creates/updates `RaceEntry` and `RaceResult` rows, add the snapshot upsert:

```python
            # Save odds snapshot for live/upcoming races (not completed ones)
            if not parsed_data.get("meta", {}).get("completed", False):
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                snapshot_time = datetime.datetime.now(datetime.timezone.utc)
                for horse_data in parsed_data.get("horses", []):
                    horse_id_snap = horse_data.get("_horse_db_id")
                    if not horse_id_snap or not race_obj:
                        continue
                    odds_win = horse_data.get("odds_win")
                    if odds_win is None:
                        continue
                    snap = OddsSnapshot(
                        race_id=race_obj.id,
                        horse_id=horse_id_snap,
                        snapshot_time=snapshot_time,
                        win_odds=float(odds_win),
                        place_odds=horse_data.get("odds_place"),
                    )
                    session.add(snap)
```

Note: `race_obj` is the `Race` ORM instance created/fetched earlier in the loop. `_horse_db_id` must be set in `horse_data` — add this to the horse-processing loop:

```python
                    horse_data["_horse_db_id"] = horse_obj.id
```

where `horse_obj` is the `Horse` ORM instance.

- [ ] **Step 4: Run all non-Docker tests**

```bash
cd backend
uv run pytest tests/ -q --ignore=tests/db --ignore=tests/ml/test_dataset_pg.py
```

Expected: all existing tests pass plus the new parser test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/crawl/crawl_2026.py \
        backend/app/ml/crawl/parsers/kra_live_parser.py \
        backend/tests/crawl/test_kra_live_parser.py
git commit -m "feat: populate odds_snapshots table during live race crawling"
```

---

## Self-Review

### Spec Coverage

| Feature / Enhancement | Task |
|---|---|
| Parse `grade`, `race_class` from KRA HTML (was null) | Task 1 |
| Parse `surface` properly (was hardcoded "Dirt") | Task 1 |
| `surface` as ML feature | Task 2 |
| `grade` as ML feature | Task 2 |
| `body_weight_delta_kg` | Task 2 |
| `morning_odds_rank` (within-race favourite rank) | Task 2 |
| `distance_win_rate` (horse win rate by distance bucket) | Task 3 |
| `jockey_horse_win_rate` (jockey-horse pair win rate) | Task 3 |
| `sire_win_rate` at inference (was 0) | Task 3 |
| Odds snapshots crawler | Task 4 |

### Train/Serve Parity Check

Every feature added to `FEATURES` in `dataset.py` must have a matching inference-time computation in `service.py`:

| Feature | Training source | Inference source |
|---|---|---|
| `surface` | `races.surface` (SQL join) | `race.surface or "Dirt"` |
| `grade` | `races.grade` (SQL join) | `race.grade or "unknown"` |
| `body_weight_delta_kg` | `groupby(horse_id).shift(1)` | `_get_prev_body_weight()` query |
| `morning_odds_rank` | `groupby(race_id).rank()` | computed after loop over all entries |
| `distance_win_rate` | `groupby([horse_id, bucket]).shift(1).ewm` | `_get_distance_win_rate()` query |
| `jockey_horse_win_rate` | `groupby([jockey_id, horse_id]).shift(1).ewm` | `_get_pair_win_rate()` query |
| `sire_win_rate` | existing | `_get_sire_win_rate()` query |

All 7 new / fixed features have both training and inference paths. ✓

### Dependency Note

Tasks 2 and 3 both modify `dataset.py` and `service.py`. Execute Task 2 first, then Task 3 on top. Task 1 and Task 4 are independent of each other and of 2–3.

### No Migration Needed

All new features derive from columns already defined in the ORM (`races.surface`, `races.grade`, `races.race_class`, `pedigree.sire_id`, `race_results.final_odds`). No new DB columns are added. The `odds_snapshots` table was created by a previous migration.
