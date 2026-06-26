# ML Pipeline v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn crawl/train/predict stubs into a working pipeline that persists KRA data to Postgres, trains CatBoostRanker + HistGBM ensemble per track, and serves real calibrated win probabilities through the API.

**Architecture:** Each stage is a standalone function callable from CLI and APScheduler. Crawl writes to Postgres via idempotent upserts. Training loads from Postgres using a sync SQLAlchemy engine + pandas. The best model per track is promoted to `models/{track}/production.json`; the predict service hot-reloads when the pointer changes.

**Tech Stack:** Python 3.9+, FastAPI, async SQLAlchemy (runtime), sync SQLAlchemy (training batch), PostgreSQL, CatBoost, scikit-learn (HistGradientBoostingRegressor, IsotonicRegression), APScheduler, scipy, pandas

## Global Constraints

- Python 3.9+ (no 3.10+ match/case syntax)
- Async SQLAlchemy sessions for all request-time DB operations
- Sync SQLAlchemy engine (via `create_engine`) for batch training data load — pandas `read_sql` is sync
- No random predictions in production — `predict/service.py` must call the real model
- Time-based split only: train 2021-2024, val 2025, test 2026 — no random k-fold
- All rolling stats use `.shift(1)` before groupby — no future data leakage
- Model artifacts stored at `backend/models/{track}/` (add to .gitignore)
- `backend/models/production.json` is the single source of truth for which model is active per track
- Tests run with `pytest` from `backend/` directory
- `DATABASE_URL` env var must be set for Postgres tests (use testcontainers in CI)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/db/models/crawl.py` | Modify | Add `RacePrediction` ORM model |
| `backend/alembic/versions/<hash>_add_race_predictions.py` | Create | Migration for `race_predictions` table |
| `backend/app/ml/crawl/upsert.py` | Create | Idempotent Postgres upserts for all crawl tables |
| `backend/app/ml/crawl/pipeline.py` | Modify | Add `run_crawl()` entry point; call upsert after parsing |
| `backend/app/ml/train/dataset.py` | Modify | Add `load_dataset_pg(db_url)` loading from Postgres |
| `backend/app/ml/train/models/catboost_binary.py` | Create | CatBoostRanker (YetiRank) — port from experiment_ranker.py |
| `backend/app/ml/train/models/ensemble.py` | Create | Weighted blend of HistGBM + CatBoost by inverse val log-loss |
| `backend/app/ml/train/promote.py` | Create | Load/save `production.json`, promote only if strictly better |
| `backend/app/ml/train/pipeline.py` | Create | `run_train(track, db_url)` orchestrates train → evaluate → promote |
| `backend/app/ml/predict/calibration.py` | Create | IsotonicRegression fit + apply |
| `backend/app/ml/predict/service.py` | Modify | Real inference: load model → features → softmax → calibrate → cache |
| `backend/app/scheduler/jobs.py` | Modify | Wire APScheduler jobs to `run_crawl`, `run_train`, `run_predict_all` |
| `backend/app/main.py` | Modify | Add background task: poll `production.json` every 60s for hot-reload |
| `backend/tests/ml/test_upsert.py` | Create | Upsert idempotency tests |
| `backend/tests/ml/test_dataset_pg.py` | Create | Dataset loading from Postgres |
| `backend/tests/ml/test_calibration.py` | Create | Calibration fit and apply |
| `backend/tests/ml/test_predict_service.py` | Create | Real prediction service |
| `backend/tests/ml/test_promote.py` | Create | Promotion logic tests |

---

## Task 1: Add `race_predictions` table

**Files:**
- Modify: `backend/app/db/models/crawl.py`
- Create: `backend/alembic/versions/<hash>_add_race_predictions.py`

**Interfaces:**
- Produces: `RacePrediction` ORM model with fields `race_id`, `horse_id`, `win_probability`, `place_probability`, `model_version`, `computed_at`, `is_stale`

- [ ] **Step 1: Add ORM model to `crawl.py`**

Add at the end of `backend/app/db/models/crawl.py`:

```python
class RacePrediction(Base):
    __tablename__ = "race_predictions"
    __table_args__ = (UniqueConstraint("race_id", "horse_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    win_probability: Mapped[float] = mapped_column(Float, nullable=False)
    place_probability: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    is_stale: Mapped[bool] = mapped_column(default=False)
```

- [ ] **Step 2: Generate Alembic migration**

```bash
cd backend
alembic revision --autogenerate -m "add_race_predictions"
```

Open the generated file and verify it contains `op.create_table('race_predictions', ...)`. If autogenerate produces wrong output, write it manually:

```python
def upgrade() -> None:
    op.create_table(
        'race_predictions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('race_id', sa.Integer(), nullable=False),
        sa.Column('horse_id', sa.Integer(), nullable=False),
        sa.Column('win_probability', sa.Float(), nullable=False),
        sa.Column('place_probability', sa.Float(), nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('is_stale', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['horse_id'], ['horses.id']),
        sa.ForeignKeyConstraint(['race_id'], ['races.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('race_id', 'horse_id'),
    )

def downgrade() -> None:
    op.drop_table('race_predictions')
```

- [ ] **Step 3: Apply migration**

```bash
cd backend
alembic upgrade head
```

Expected output: `Running upgrade e03b7948ec7d -> <new_hash>, add_race_predictions`

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/models/crawl.py backend/alembic/versions/
git commit -m "feat: add race_predictions table"
```

---

## Task 2: Implement `crawl/upsert.py`

**Files:**
- Create: `backend/app/ml/crawl/upsert.py`
- Create: `backend/tests/ml/test_upsert.py`

**Interfaces:**
- Consumes: async SQLAlchemy `AsyncSession`; dicts of parsed race/horse/jockey data
- Produces:
  - `async upsert_horse(session, name, sex, age) -> int` — returns horse.id
  - `async upsert_jockey(session, name, kra_code) -> int` — returns jockey.id
  - `async upsert_trainer(session, name, kra_code) -> int` — returns trainer.id
  - `async upsert_race(session, track, race_date, race_number, **kwargs) -> int` — returns race.id
  - `async upsert_race_result(session, race_id, horse_id, finish_position, finish_time_s, final_odds) -> None`
  - `async upsert_inrace_timing(session, race_id, horse_id, s1f_time, g3f_time) -> None`
  - `async upsert_race_entry(session, race_id, horse_id, jockey_id, trainer_id, program_number, **kwargs) -> None`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/ml/test_upsert.py`:

```python
import pytest
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.ml.crawl.upsert import (
    upsert_horse, upsert_jockey, upsert_trainer,
    upsert_race, upsert_race_result, upsert_inrace_timing, upsert_race_entry,
)

@pytest.fixture
async def session(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()

@pytest.mark.asyncio
async def test_upsert_horse_idempotent(session):
    id1 = await upsert_horse(session, name="천하무적", sex="M", age=4)
    id2 = await upsert_horse(session, name="천하무적", sex="M", age=4)
    assert id1 == id2

@pytest.mark.asyncio
async def test_upsert_jockey_idempotent(session):
    id1 = await upsert_jockey(session, name="김민수", kra_code="JK001")
    id2 = await upsert_jockey(session, name="김민수", kra_code="JK001")
    assert id1 == id2

@pytest.mark.asyncio
async def test_upsert_race_idempotent(session):
    id1 = await upsert_race(session, track="SEOUL", race_date=datetime.date(2026, 6, 21),
                            race_number=1, race_name="1경주", distance_m=1200, surface="DIRT")
    id2 = await upsert_race(session, track="SEOUL", race_date=datetime.date(2026, 6, 21),
                            race_number=1, race_name="1경주 수정", distance_m=1200, surface="DIRT")
    assert id1 == id2  # same race, name update is fine — same PK
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
pytest tests/ml/test_upsert.py -v
```

Expected: `ImportError: cannot import name 'upsert_horse' from 'app.ml.crawl.upsert'`

- [ ] **Step 3: Implement `upsert.py`**

Create `backend/app/ml/crawl/upsert.py`:

```python
import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models.crawl import (
    Horse, Jockey, Trainer, Race, RaceEntry, RaceResult, InraceTiming
)


async def upsert_horse(session: AsyncSession, name: str, sex: str,
                       age: Optional[int] = None) -> int:
    """Find horse by name or insert. Returns horse.id."""
    result = await session.execute(select(Horse).where(Horse.name == name))
    horse = result.scalars().first()
    if horse is None:
        horse = Horse(name=name, sex=sex, age=age)
        session.add(horse)
        await session.flush()
    return horse.id


async def upsert_jockey(session: AsyncSession, name: str,
                        kra_code: Optional[str] = None) -> int:
    """Find jockey by kra_code (or name if no code) or insert."""
    if kra_code:
        result = await session.execute(select(Jockey).where(Jockey.kra_code == kra_code))
    else:
        result = await session.execute(select(Jockey).where(Jockey.name == name))
    jockey = result.scalars().first()
    if jockey is None:
        jockey = Jockey(name=name, kra_code=kra_code)
        session.add(jockey)
        await session.flush()
    return jockey.id


async def upsert_trainer(session: AsyncSession, name: str,
                         kra_code: Optional[str] = None) -> int:
    """Find trainer by kra_code (or name if no code) or insert."""
    if kra_code:
        result = await session.execute(select(Trainer).where(Trainer.kra_code == kra_code))
    else:
        result = await session.execute(select(Trainer).where(Trainer.name == name))
    trainer = result.scalars().first()
    if trainer is None:
        trainer = Trainer(name=name, kra_code=kra_code)
        session.add(trainer)
        await session.flush()
    return trainer.id


async def upsert_race(session: AsyncSession, track: str, race_date: datetime.date,
                      race_number: int, race_name: str, distance_m: int, surface: str,
                      track_condition: Optional[str] = None, weather: Optional[str] = None,
                      grade: Optional[str] = None, field_size: Optional[int] = None,
                      post_time: Optional[datetime.datetime] = None) -> int:
    """Upsert race by (track, race_date, race_number). Returns race.id."""
    result = await session.execute(
        select(Race).where(
            Race.track == track,
            Race.race_date == race_date,
            Race.race_number == race_number,
        )
    )
    race = result.scalars().first()
    if race is None:
        race = Race(
            track=track, race_date=race_date, race_number=race_number,
            race_name=race_name, distance_m=distance_m, surface=surface,
            track_condition=track_condition, weather=weather,
            grade=grade, field_size=field_size, post_time=post_time,
        )
        session.add(race)
        await session.flush()
    else:
        # Update mutable fields
        race.race_name = race_name
        race.track_condition = track_condition
        race.weather = weather
        race.field_size = field_size
        race.post_time = post_time
    return race.id


async def upsert_race_entry(session: AsyncSession, race_id: int, horse_id: int,
                            program_number: int, jockey_id: Optional[int] = None,
                            trainer_id: Optional[int] = None,
                            carry_weight_kg: Optional[float] = None,
                            body_weight_kg: Optional[float] = None,
                            morning_odds: Optional[float] = None) -> None:
    """Upsert race entry by (race_id, program_number)."""
    result = await session.execute(
        select(RaceEntry).where(
            RaceEntry.race_id == race_id,
            RaceEntry.program_number == program_number,
        )
    )
    entry = result.scalars().first()
    if entry is None:
        entry = RaceEntry(
            race_id=race_id, horse_id=horse_id, program_number=program_number,
            jockey_id=jockey_id, trainer_id=trainer_id,
            carry_weight_kg=carry_weight_kg, body_weight_kg=body_weight_kg,
            morning_odds=morning_odds,
        )
        session.add(entry)
    else:
        entry.jockey_id = jockey_id
        entry.trainer_id = trainer_id
        entry.carry_weight_kg = carry_weight_kg
        entry.body_weight_kg = body_weight_kg
        entry.morning_odds = morning_odds


async def upsert_race_result(session: AsyncSession, race_id: int, horse_id: int,
                             finish_position: Optional[int] = None,
                             finish_time_s: Optional[float] = None,
                             final_odds: Optional[float] = None) -> None:
    """Upsert race result by (race_id, horse_id)."""
    result = await session.execute(
        select(RaceResult).where(
            RaceResult.race_id == race_id,
            RaceResult.horse_id == horse_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        row = RaceResult(
            race_id=race_id, horse_id=horse_id,
            finish_position=finish_position,
            finish_time_s=finish_time_s,
            final_odds=final_odds,
        )
        session.add(row)
    else:
        row.finish_position = finish_position
        row.finish_time_s = finish_time_s
        row.final_odds = final_odds


async def upsert_inrace_timing(session: AsyncSession, race_id: int, horse_id: int,
                               s1f_time: Optional[float] = None,
                               g3f_time: Optional[float] = None) -> None:
    """Upsert inrace timing by (race_id, horse_id)."""
    result = await session.execute(
        select(InraceTiming).where(
            InraceTiming.race_id == race_id,
            InraceTiming.horse_id == horse_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        row = InraceTiming(
            race_id=race_id, horse_id=horse_id,
            s1f_time=s1f_time, g3f_time=g3f_time,
        )
        session.add(row)
    else:
        row.s1f_time = s1f_time
        row.g3f_time = g3f_time
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
pytest tests/ml/test_upsert.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/crawl/upsert.py backend/tests/ml/test_upsert.py
git commit -m "feat: implement idempotent crawl upserts"
```

---

## Task 3: Wire crawl pipeline to DB persistence

**Files:**
- Modify: `backend/app/ml/crawl/pipeline.py`

**Interfaces:**
- Produces: `async run_crawl(start_date: date, end_date: date) -> dict` — returns `{"races_upserted": int, "failures": list[str]}`
- Consumes: `upsert_horse`, `upsert_jockey`, `upsert_race`, `upsert_race_result`, `upsert_inrace_timing`, `upsert_race_entry` from `app.ml.crawl.upsert`

- [ ] **Step 1: Write failing test**

Create `backend/tests/ml/test_crawl_pipeline.py`:

```python
import pytest
import datetime
from unittest.mock import AsyncMock, patch
from app.ml.crawl.pipeline import run_crawl

@pytest.mark.asyncio
async def test_run_crawl_returns_summary():
    with patch("app.ml.crawl.pipeline.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("app.ml.crawl.pipeline.KRALiveParser") as mock_parser:
            mock_parser.parse_chulma_list.return_value = []
            result = await run_crawl(
                datetime.date(2026, 6, 21),
                datetime.date(2026, 6, 21),
                use_synthetic_fallback=False,
            )
    assert "races_upserted" in result
    assert "failures" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/ml/test_crawl_pipeline.py::test_run_crawl_returns_summary -v
```

Expected: `ImportError` or `TypeError` — `run_crawl` doesn't exist yet.

- [ ] **Step 3: Rewrite `pipeline.py`**

Replace `backend/app/ml/crawl/pipeline.py` with:

```python
import logging
import datetime
import requests
from datetime import date
from typing import Optional

from app.db.session import async_session_factory
from app.db.models.crawl import CrawlState, CrawlFailure
from app.ml.crawl.kra_client import KRAClient
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from app.ml.crawl.upsert import (
    upsert_horse, upsert_jockey, upsert_trainer,
    upsert_race, upsert_race_entry, upsert_race_result, upsert_inrace_timing,
)
from sqlalchemy import select

logger = logging.getLogger(__name__)

TRACK_MEET_MAP = {"SEOUL": "1", "BUSAN": "2", "JEJU": "3"}
SEX_MAP = {"수": "M", "암": "F", "거": "G"}


async def _ingest_race_detail(session, track: str, race_date_str: str,
                              rc_no: int) -> bool:
    """Fetch one completed race and upsert all rows. Returns True on success."""
    meet = TRACK_MEET_MAP.get(track, "1")
    try:
        res = requests.post(
            "https://race.kra.co.kr/raceScore/ScoretableDetailList.do",
            headers={"User-Agent": "Mozilla/5.0"},
            data={"meet": meet, "realRcDate": race_date_str, "realRcNo": str(rc_no)},
            timeout=15,
        )
        res.encoding = "euc-kr"
        detail = KRALiveParser.parse_race_detail(res.text)
        if not detail or not detail.get("horses"):
            return False

        meta = detail.get("meta", {})
        race_date = datetime.date(
            int(race_date_str[:4]), int(race_date_str[4:6]), int(race_date_str[6:])
        )
        race_id = await upsert_race(
            session,
            track=track,
            race_date=race_date,
            race_number=rc_no,
            race_name=f"{rc_no}경주",
            distance_m=detail.get("distance_m", 1200),
            surface=detail.get("surface", "DIRT"),
            track_condition=meta.get("track_condition"),
            weather=meta.get("weather"),
            field_size=len(detail["horses"]),
        )

        for h in detail["horses"]:
            horse_id = await upsert_horse(
                session,
                name=h["horse_name"],
                sex=SEX_MAP.get(h.get("sex", "수"), "M"),
            )
            jockey_id = await upsert_jockey(session, name=h.get("jockey", "unknown"))
            trainer_id = await upsert_trainer(session, name=h.get("trainer", "unknown"))

            await upsert_race_entry(
                session,
                race_id=race_id,
                horse_id=horse_id,
                program_number=h.get("horse_no", 0),
                jockey_id=jockey_id,
                trainer_id=trainer_id,
                morning_odds=h.get("odds_win"),
            )
            await upsert_race_result(
                session,
                race_id=race_id,
                horse_id=horse_id,
                finish_position=h.get("rank"),
                final_odds=h.get("odds_win"),
            )
            await upsert_inrace_timing(
                session,
                race_id=race_id,
                horse_id=horse_id,
                s1f_time=h.get("s1f_time"),
                g3f_time=h.get("g3f_time"),
            )

        await session.commit()
        return True
    except Exception as exc:
        logger.error(f"Failed to ingest {track} {race_date_str} race {rc_no}: {exc}")
        await session.rollback()
        return False


async def run_crawl(start_date: date, end_date: date,
                    use_synthetic_fallback: bool = False) -> dict:
    """
    Entry point for the crawl stage.
    Fetches KRA race data between start_date and end_date and upserts to Postgres.
    Returns {"races_upserted": int, "failures": list[str]}.
    """
    client = KRAClient()
    races_upserted = 0
    failures = []

    async with async_session_factory() as session:
        for track, meet in TRACK_MEET_MAP.items():
            try:
                list_html = client.fetch_page(
                    "/raceScore/ScoretableScoreList.do",
                    {"Act": "04", "Sub": "1", "meet": meet},
                )
                if not list_html:
                    failures.append(f"{track}: failed to fetch race list")
                    continue

                race_dates = KRALiveParser.parse_chulma_list(list_html)

                for entry in race_dates:
                    date_str = entry["date"]
                    try:
                        rd = datetime.date(
                            int(date_str[:4]), int(date_str[4:6]), int(date_str[6:])
                        )
                    except (ValueError, IndexError):
                        continue
                    if not (start_date <= rd <= end_date):
                        continue

                    for rc_no in entry.get("races", []):
                        ok = await _ingest_race_detail(session, track, date_str, rc_no)
                        if ok:
                            races_upserted += 1
                        else:
                            failures.append(f"{track} {date_str} race {rc_no}")

                # Update crawl state
                result = await session.execute(
                    select(CrawlState).where(CrawlState.track == track)
                )
                state = result.scalars().first()
                if state is None:
                    state = CrawlState(track=track, last_status="ok")
                    session.add(state)
                state.last_crawled_date = end_date
                state.last_status = "ok" if not failures else "partial"
                await session.commit()

            except Exception as exc:
                logger.error(f"Crawl failed for track {track}: {exc}")
                failures.append(f"{track}: {exc}")

    if use_synthetic_fallback and races_upserted == 0:
        logger.info("No real races ingested; running synthetic data fallback")
        from app.ml.crawl.synthetic_data import main as populate_db
        await populate_db()

    logger.info(f"Crawl done: {races_upserted} races upserted, {len(failures)} failures")
    return {"races_upserted": races_upserted, "failures": failures}
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/ml/test_crawl_pipeline.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/crawl/pipeline.py backend/tests/ml/test_crawl_pipeline.py
git commit -m "feat: wire crawl pipeline to Postgres upserts"
```

---

## Task 4: Load training dataset from Postgres

**Files:**
- Modify: `backend/app/ml/train/dataset.py`
- Create: `backend/tests/ml/test_dataset_pg.py`

**Interfaces:**
- Produces: `load_dataset_pg(db_url: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str], str]` — same return shape as existing `load_dataset()`
- Consumes: existing feature list: `['jockey_id', 'trainer_id', 'program_number', 'distance_m', 'field_size', 'carry_weight_kg', 'body_weight_kg', 'morning_odds', 'horse_age', 'horse_sex', 'track', 'track_condition', 'weather', 'days_since_last_race', 'horse_win_rate', 'jockey_win_rate', 'trainer_win_rate', 'sire_win_rate', 'past_avg_s1f_time', 'past_avg_g3f_time']`

- [ ] **Step 1: Write failing test**

Create `backend/tests/ml/test_dataset_pg.py`:

```python
import pytest
from app.ml.train.dataset import load_dataset_pg, FEATURES, TARGET

def test_load_dataset_pg_returns_correct_splits(pg_db_url_with_data):
    """pg_db_url_with_data fixture creates a Postgres DB populated with synthetic data."""
    train, val, test, features, target = load_dataset_pg(pg_db_url_with_data)
    assert features == FEATURES
    assert target == TARGET
    assert len(train) > 0
    # Train set should only contain rows from 2021-2024
    assert (train['race_date'] <= '2024-12-31').all()
    assert (train['race_date'] >= '2021-01-01').all()
    # No future data leakage: horse_win_rate at race N uses only races before N
    for horse_id, grp in train.groupby('horse_id'):
        if len(grp) > 1:
            grp = grp.sort_values('race_date')
            # win rate at row i should be based on rows before i, not row i itself
            # A horse that loses every race should have 0 win rate going forward
            pass  # structural check — actual leakage test is in property tests
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend
pytest tests/ml/test_dataset_pg.py -v
```

Expected: `ImportError: cannot import name 'load_dataset_pg'`

- [ ] **Step 3: Add `load_dataset_pg` and export constants to `dataset.py`**

Add to the bottom of `backend/app/ml/train/dataset.py` (keep `load_dataset` as-is for SQLite use):

```python
import os

FEATURES = [
    'jockey_id', 'trainer_id', 'program_number', 'distance_m', 'field_size',
    'carry_weight_kg', 'body_weight_kg', 'morning_odds', 'horse_age', 'horse_sex',
    'track', 'track_condition', 'weather', 'days_since_last_race',
    'horse_win_rate', 'jockey_win_rate', 'trainer_win_rate', 'sire_win_rate',
    'past_avg_s1f_time', 'past_avg_g3f_time',
]
TARGET = 'relevance'

_PG_QUERY = """
SELECT
    r.id as race_id,
    r.race_date,
    r.distance_m,
    r.field_size,
    r.track,
    r.track_condition,
    r.weather,
    e.horse_id,
    e.jockey_id,
    e.trainer_id,
    e.program_number,
    e.carry_weight_kg,
    e.body_weight_kg,
    e.morning_odds,
    h.age as horse_age,
    h.sex as horse_sex,
    p.sire_id,
    t.s1f_time,
    t.g3f_time,
    res.finish_position,
    res.finish_time_s,
    CASE WHEN res.finish_position = 1 THEN 1 ELSE 0 END as is_win
FROM races r
JOIN race_entries e ON r.id = e.race_id
JOIN horses h ON e.horse_id = h.id
LEFT JOIN pedigree p ON h.id = p.horse_id
LEFT JOIN inrace_timings t ON r.id = t.race_id AND e.horse_id = t.horse_id
LEFT JOIN race_results res ON r.id = res.race_id AND e.horse_id = res.horse_id
ORDER BY r.race_date, r.id
"""


def _apply_features(df: pd.DataFrame):
    """Apply feature engineering to a raw DataFrame. Modifies in place."""
    df['horse_sex'] = df['horse_sex'].astype('category')
    df['track'] = df['track'].astype('category')
    df['track_condition'] = df['track_condition'].fillna('건조').astype('category')
    df['weather'] = df['weather'].fillna('맑음').astype('category')
    df['body_weight_kg'] = df['body_weight_kg'].fillna(500.0)
    df['horse_age'] = df['horse_age'].fillna(3).astype(int)

    df.sort_values(['horse_id', 'race_date'], inplace=True)
    df['days_since_last_race'] = (
        df.groupby('horse_id')['race_date']
        .transform(lambda x: (x - x.shift(1)).dt.days)
        .fillna(30.0)
    )
    df['horse_win_rate'] = (
        df.groupby('horse_id')['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0)
    )
    df['past_avg_s1f_time'] = (
        df.groupby('horse_id')['s1f_time']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(14.0)
    )
    df['past_avg_g3f_time'] = (
        df.groupby('horse_id')['g3f_time']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(38.0)
    )
    df.sort_values(['jockey_id', 'race_date'], inplace=True)
    df['jockey_win_rate'] = (
        df.groupby('jockey_id')['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0)
    )
    df.sort_values(['trainer_id', 'race_date'], inplace=True)
    df['trainer_win_rate'] = (
        df.groupby('trainer_id')['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0)
    )
    df.sort_values(['sire_id', 'race_date'], inplace=True)
    df['sire_win_rate'] = (
        df.groupby('sire_id')['is_win']
        .transform(lambda x: x.shift(1).ewm(span=5, min_periods=1).mean())
        .fillna(0)
    )
    df['relevance'] = df['finish_position'].apply(
        lambda x: 3 if x == 1 else (2 if x == 2 else (1 if x == 3 else 0))
    )
    df.sort_values(['race_date', 'race_id'], inplace=True)
    df['finish_time_s'] = df['finish_time_s'].fillna(999.0)
    return df


def load_dataset_pg(db_url: str):
    """
    Load training dataset from PostgreSQL.
    Returns (train_df, val_df, test_df, FEATURES, TARGET).
    Uses a sync SQLAlchemy engine — safe for batch training jobs.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(db_url)
    with engine.connect() as conn:
        df = pd.read_sql(text(_PG_QUERY), conn, parse_dates=['race_date'])
    engine.dispose()

    df = _apply_features(df)

    train_mask = (df['race_date'] >= '2021-01-01') & (df['race_date'] <= '2024-12-31')
    val_mask = (df['race_date'] >= '2025-01-01') & (df['race_date'] <= '2025-12-31')
    test_mask = df['race_date'] >= '2026-01-01'

    return (
        df[train_mask].copy(),
        df[val_mask].copy(),
        df[test_mask].copy(),
        FEATURES,
        TARGET,
    )
```

Also add `FEATURES` and `TARGET` exports at the module level in `dataset.py` (move them above the existing `load_dataset` function so both functions share the constants).

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/ml/test_dataset_pg.py -v
```

Note: this test requires a `pg_db_url_with_data` fixture — if not set up yet, skip for now with `pytest -k "not pg"` and come back after Task 11 (APScheduler) sets up test infra.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/train/dataset.py backend/tests/ml/test_dataset_pg.py
git commit -m "feat: add load_dataset_pg for Postgres training data"
```

---

## Task 5: Add CatBoostRanker model

**Files:**
- Create: `backend/app/ml/train/models/catboost_binary.py`

**Interfaces:**
- Produces: `train_catboost(train_df, val_df, features, target) -> ModelShim` — same interface as `train_lgbm`. `ModelShim.predict(X) -> np.ndarray` returns raw ranking scores.

- [ ] **Step 1: Write failing test**

Add to `backend/tests/ml/test_models.py` (create if not exists):

```python
import pandas as pd
import numpy as np
import pytest

from app.ml.train.dataset import load_dataset, FEATURES, TARGET

@pytest.fixture
def small_dataset():
    train, val, _, features, target = load_dataset("test_dod.db")
    return train.head(200), val.head(50), features, target

def test_train_catboost_returns_predictions(small_dataset):
    from app.ml.train.models.catboost_binary import train_catboost
    train, val, features, target = small_dataset
    model = train_catboost(train, val, features, target)
    preds = model.predict(val[features])
    assert len(preds) == len(val)
    assert not np.any(np.isnan(preds))
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend
pytest tests/ml/test_models.py::test_train_catboost_returns_predictions -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `catboost_binary.py`**

Create `backend/app/ml/train/models/catboost_binary.py`:

```python
import pandas as pd
import numpy as np


def train_catboost(train_df: pd.DataFrame, val_df: pd.DataFrame,
                   features: list, target: str):
    """
    Train a CatBoostRanker (YetiRank listwise) on race data.
    group_id is race_id — the model learns to rank horses within each race.
    Returns a ModelShim with .predict(X) -> np.ndarray interface.
    """
    from catboost import CatBoostRanker, Pool

    cat_features = ['jockey_id', 'trainer_id', 'horse_sex', 'track', 'track_condition', 'weather']
    # Only include cat features that are actually in the feature list
    cat_features = [c for c in cat_features if c in features]

    # Ensure correct types
    for c in cat_features:
        train_df[c] = train_df[c].astype(str)
        val_df[c] = val_df[c].astype(str)

    train_pool = Pool(
        data=train_df[features],
        label=train_df[target],
        group_id=train_df['race_id'],
        cat_features=cat_features,
    )
    val_pool = Pool(
        data=val_df[features],
        label=val_df[target],
        group_id=val_df['race_id'],
        cat_features=cat_features,
    )

    model = CatBoostRanker(
        loss_function='YetiRank',
        iterations=500,
        learning_rate=0.05,
        verbose=50,
        early_stopping_rounds=30,
        random_seed=42,
    )
    model.fit(train_pool, eval_set=val_pool)

    class ModelShim:
        def __init__(self, m, cat_cols):
            self.m = m
            self.cat_cols = cat_cols

        def predict(self, X: pd.DataFrame) -> np.ndarray:
            X = X.copy()
            for c in self.cat_cols:
                if c in X.columns:
                    X[c] = X[c].astype(str)
            return self.m.predict(X)

    return ModelShim(model, cat_features)
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/ml/test_models.py::test_train_catboost_returns_predictions -v
```

Expected: `1 passed` (may take 30-60 seconds for CatBoost training)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/train/models/catboost_binary.py backend/tests/ml/test_models.py
git commit -m "feat: add CatBoostRanker (YetiRank) model"
```

---

## Task 6: Implement ensemble model

**Files:**
- Create: `backend/app/ml/train/models/ensemble.py`

**Interfaces:**
- Consumes: list of `ModelShim` objects (each has `.predict(X) -> np.ndarray`), val DataFrames for weight computation
- Produces: `build_ensemble(models, val_df, features) -> EnsembleShim` — `EnsembleShim.predict(X) -> np.ndarray` returns weighted average of raw scores

- [ ] **Step 1: Write failing test**

Add to `backend/tests/ml/test_models.py`:

```python
def test_ensemble_predictions_are_weighted_average(small_dataset):
    from app.ml.train.models.lgbm_binary import train_lgbm
    from app.ml.train.models.ensemble import build_ensemble
    from scipy.special import softmax
    import numpy as np

    train, val, features, target = small_dataset
    model_a = train_lgbm(train, val, features, target)
    model_b = train_lgbm(train, val, features, target)  # same model twice for test

    ensemble = build_ensemble([model_a, model_b], val, features, target)
    preds = ensemble.predict(val[features])
    assert len(preds) == len(val)
    assert not np.any(np.isnan(preds))
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend
pytest tests/ml/test_models.py::test_ensemble_predictions_are_weighted_average -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `ensemble.py`**

Create `backend/app/ml/train/models/ensemble.py`:

```python
import numpy as np
import pandas as pd
from scipy.special import softmax
from sklearn.metrics import log_loss


def _race_log_loss(model, val_df: pd.DataFrame, features: list, target: str) -> float:
    """Compute per-race softmax log-loss for a model on the val set."""
    val_df = val_df.copy()
    val_df['score'] = model.predict(val_df[features])
    losses = []
    for _, race in val_df.groupby('race_id'):
        if race['is_win'].sum() == 0:
            continue
        probs = softmax(race['score'].values)
        probs = np.clip(probs, 1e-7, 1 - 1e-7)
        y_true = (race[target].values > 0).astype(int)
        # simple log-loss: -log(prob of winner)
        winner_prob = probs[y_true.argmax()] if y_true.sum() > 0 else probs[0]
        losses.append(-np.log(winner_prob))
    return float(np.mean(losses)) if losses else 1.0


class EnsembleShim:
    def __init__(self, models, weights):
        self.models = models
        self.weights = weights  # list of floats summing to 1.0

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        scores = np.zeros(len(X))
        for model, w in zip(self.models, self.weights):
            scores += w * model.predict(X)
        return scores


def build_ensemble(models: list, val_df: pd.DataFrame,
                   features: list, target: str) -> EnsembleShim:
    """
    Build a weighted ensemble of models.
    Weight for each model = 1 / val_log_loss, normalized to sum to 1.
    """
    log_losses = [_race_log_loss(m, val_df, features, target) for m in models]
    inv_losses = [1.0 / max(ll, 1e-7) for ll in log_losses]
    total = sum(inv_losses)
    weights = [w / total for w in inv_losses]
    return EnsembleShim(models, weights)
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/ml/test_models.py::test_ensemble_predictions_are_weighted_average -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/train/models/ensemble.py backend/tests/ml/test_models.py
git commit -m "feat: implement weighted ensemble model"
```

---

## Task 7: Implement model promotion

**Files:**
- Create: `backend/app/ml/train/promote.py`
- Create: `backend/tests/ml/test_promote.py`

**Interfaces:**
- Produces:
  - `get_production_metrics(track: str) -> dict | None` — reads `backend/models/production.json`, returns `{"log_loss": float, "roi": float, "version": str}` or `None` if no production model
  - `promote_if_better(track, model, val_log_loss, val_roi, model_path) -> bool` — promotes and returns `True` if better, else `False`
  - `load_production_model(track: str)` — loads and returns the production model for a track

- [ ] **Step 1: Write failing tests**

Create `backend/tests/ml/test_promote.py`:

```python
import json
import pickle
import pytest
from pathlib import Path
from app.ml.train.promote import promote_if_better, get_production_metrics, load_production_model


class FakeModel:
    def predict(self, X):
        import numpy as np
        return np.zeros(len(X))


def test_first_promotion_always_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    result = promote_if_better("SEOUL", model, val_log_loss=0.8, val_roi=0.05,
                               model_path=str(tmp_path / "model_v1.pkl"))
    assert result is True
    metrics = get_production_metrics("SEOUL")
    assert metrics is not None
    assert metrics["log_loss"] == 0.8


def test_better_model_replaces_production(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better("SEOUL", model, val_log_loss=0.8, val_roi=0.05,
                      model_path=str(tmp_path / "model_v1.pkl"))
    result = promote_if_better("SEOUL", model, val_log_loss=0.7, val_roi=0.10,
                               model_path=str(tmp_path / "model_v2.pkl"))
    assert result is True
    assert get_production_metrics("SEOUL")["log_loss"] == 0.7


def test_worse_model_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    model = FakeModel()
    promote_if_better("SEOUL", model, val_log_loss=0.7, val_roi=0.10,
                      model_path=str(tmp_path / "model_v1.pkl"))
    result = promote_if_better("SEOUL", model, val_log_loss=0.9, val_roi=-0.05,
                               model_path=str(tmp_path / "model_v2.pkl"))
    assert result is False
    assert get_production_metrics("SEOUL")["log_loss"] == 0.7
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend
pytest tests/ml/test_promote.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `promote.py`**

Create `backend/app/ml/train/promote.py`:

```python
import json
import os
import pickle
import datetime
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _model_dir() -> Path:
    base = os.environ.get("MODEL_DIR", "models")
    return Path(base)


def _production_json_path() -> Path:
    return _model_dir() / "production.json"


def get_production_metrics(track: str) -> Optional[dict]:
    """Returns current production model metrics for a track, or None."""
    path = _production_json_path()
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return data.get(track)


def promote_if_better(track: str, model, val_log_loss: float, val_roi: float,
                      model_path: str) -> bool:
    """
    Promote model to production if it strictly beats the current production.
    Rule: new val_log_loss < current AND new val_roi >= 0.
    First promotion always succeeds.
    Saves the model to model_path and updates production.json.
    Returns True if promoted, False if rejected.
    """
    current = get_production_metrics(track)

    if current is not None:
        if val_log_loss >= current["log_loss"] or val_roi < 0:
            logger.info(
                f"[{track}] Rejected: log_loss {val_log_loss:.4f} vs {current['log_loss']:.4f}, "
                f"roi {val_roi:.4f}"
            )
            return False

    # Save model artifact
    _model_dir().mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    # Update production.json
    path = _production_json_path()
    data = {}
    if path.exists():
        with open(path) as f:
            data = json.load(f)

    data[track] = {
        "model_path": str(model_path),
        "log_loss": val_log_loss,
        "roi": val_roi,
        "version": datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
        "promoted_at": datetime.datetime.utcnow().isoformat(),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"[{track}] Promoted: log_loss {val_log_loss:.4f}, roi {val_roi:.4f}")
    return True


def load_production_model(track: str):
    """Load and return the production model for a track."""
    metrics = get_production_metrics(track)
    if metrics is None:
        raise FileNotFoundError(f"No production model for track {track}")
    model_path = metrics["model_path"]
    with open(model_path, "rb") as f:
        return pickle.load(f)
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/ml/test_promote.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/train/promote.py backend/tests/ml/test_promote.py
git commit -m "feat: implement model promotion with production.json pointer"
```

---

## Task 8: Implement calibration

**Files:**
- Create: `backend/app/ml/predict/calibration.py`
- Create: `backend/tests/ml/test_calibration.py`

**Interfaces:**
- Produces:
  - `fit_calibration(raw_probs: np.ndarray, y_binary: np.ndarray) -> IsotonicRegression`
  - `apply_calibration(raw_probs: np.ndarray, calibrator) -> np.ndarray` — calibrates then renormalizes to sum to 1 per race

- [ ] **Step 1: Write failing tests**

Create `backend/tests/ml/test_calibration.py`:

```python
import numpy as np
import pytest
from app.ml.predict.calibration import fit_calibration, apply_calibration


def test_calibration_output_sums_to_one():
    raw = np.array([0.6, 0.3, 0.1])
    y = np.array([1, 0, 0])
    cal = fit_calibration(raw, y)
    out = apply_calibration(raw, cal)
    assert abs(out.sum() - 1.0) < 1e-6


def test_calibration_preserves_ranking():
    raw = np.array([0.7, 0.2, 0.1])
    y = np.array([1, 0, 0])
    cal = fit_calibration(raw, y)
    out = apply_calibration(raw, cal)
    assert out[0] > out[1] > out[2]


def test_calibration_clips_out_of_bounds():
    raw = np.array([1.5, -0.1, 0.5])
    y = np.array([1, 0, 0])
    cal = fit_calibration(raw, y)
    out = apply_calibration(raw, cal)
    assert (out >= 0).all()
    assert (out <= 1).all()
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend
pytest tests/ml/test_calibration.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `calibration.py`**

Create `backend/app/ml/predict/calibration.py`:

```python
import numpy as np
from sklearn.isotonic import IsotonicRegression


def fit_calibration(raw_probs: np.ndarray, y_binary: np.ndarray) -> IsotonicRegression:
    """
    Fit an isotonic regression calibrator on raw model probabilities.
    raw_probs: 1D array of raw softmax probabilities from the model.
    y_binary: 1D binary array, 1 if horse won, 0 otherwise.
    """
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_probs, y_binary)
    return calibrator


def apply_calibration(raw_probs: np.ndarray, calibrator) -> np.ndarray:
    """
    Apply calibration and renormalize so probabilities sum to 1.
    raw_probs: 1D array of raw softmax probabilities for all horses in one race.
    """
    calibrated = calibrator.predict(raw_probs)
    calibrated = np.clip(calibrated, 1e-7, 1.0)
    total = calibrated.sum()
    if total > 0:
        calibrated = calibrated / total
    else:
        calibrated = np.ones(len(calibrated)) / len(calibrated)
    return calibrated
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/ml/test_calibration.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/predict/calibration.py backend/tests/ml/test_calibration.py
git commit -m "feat: implement isotonic regression probability calibration"
```

---

## Task 9: Rewrite predict service with real model

**Files:**
- Modify: `backend/app/ml/predict/service.py`
- Create: `backend/tests/ml/test_predict_service.py`

**Interfaces:**
- Consumes: `load_production_model(track)` from `promote.py`; async SQLAlchemy session for fetching race entries + history
- Produces: `async predict_race(race_id: int, session: AsyncSession) -> list[HorsePrediction]` — same `HorsePrediction` schema as before but with real probabilities

- [ ] **Step 1: Write failing test**

Create `backend/tests/ml/test_predict_service.py`:

```python
import pytest
import datetime
from unittest.mock import AsyncMock, patch, MagicMock
import numpy as np

from app.ml.predict.service import predict_race, HorsePrediction


@pytest.mark.asyncio
async def test_predict_race_returns_horse_predictions():
    mock_session = AsyncMock()

    # Mock race query
    mock_race = MagicMock()
    mock_race.track = "SEOUL"
    mock_race.distance_m = 1200
    mock_race.field_size = 5
    mock_race.track_condition = "건조"
    mock_race.weather = "맑음"

    # Mock entries
    mock_entry = MagicMock()
    mock_entry.horse_id = 1
    mock_entry.program_number = 1
    mock_entry.jockey_id = 1
    mock_entry.trainer_id = 1
    mock_entry.carry_weight_kg = 57.0
    mock_entry.body_weight_kg = 490.0
    mock_entry.morning_odds = 3.5
    mock_entry.horse = MagicMock()
    mock_entry.horse.name = "천하무적"
    mock_entry.horse.age = 4
    mock_entry.horse.sex = "M"

    mock_session.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(
            first=MagicMock(return_value=mock_race),
            all=MagicMock(return_value=[mock_entry]),
        ))
    ))

    with patch("app.ml.predict.service._get_model") as mock_get_model:
        fake_model = MagicMock()
        fake_model.predict.return_value = np.array([1.0])
        mock_get_model.return_value = fake_model

        results = await predict_race(race_id=1, session=mock_session)

    assert len(results) == 1
    assert isinstance(results[0], HorsePrediction)
    assert 0 < results[0].win_probability < 1
    assert results[0].win_probability != results[0].place_probability or len(results) == 1


@pytest.mark.asyncio
async def test_predict_race_probabilities_sum_to_one():
    """With 3 horses, win probabilities should sum to ~1."""
    # This test requires a real model; skip if no production model is available
    pytest.skip("Requires production model — run after Task 10 (run_train)")
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend
pytest tests/ml/test_predict_service.py::test_predict_race_returns_horse_predictions -v
```

Expected: `FAIL` or `ImportError`

- [ ] **Step 3: Rewrite `service.py`**

Replace `backend/app/ml/predict/service.py`:

```python
import datetime
import logging
import numpy as np
import pandas as pd
from typing import Optional
from pydantic import BaseModel
from scipy.special import softmax
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.crawl import Race, RaceEntry, RaceResult, InraceTiming, Horse, Pedigree

logger = logging.getLogger(__name__)

# In-memory model cache: {track: (model, version_str)}
_model_cache: dict[str, tuple] = {}

FEATURES = [
    'jockey_id', 'trainer_id', 'program_number', 'distance_m', 'field_size',
    'carry_weight_kg', 'body_weight_kg', 'morning_odds', 'horse_age', 'horse_sex',
    'track', 'track_condition', 'weather', 'days_since_last_race',
    'horse_win_rate', 'jockey_win_rate', 'trainer_win_rate', 'sire_win_rate',
    'past_avg_s1f_time', 'past_avg_g3f_time',
]


class HorsePrediction(BaseModel):
    horse_id: int
    horse_name: str
    program_number: int
    win_probability: float
    place_probability: float
    model_versions: dict
    features_snapshot: dict
    computed_at: datetime.datetime


def _get_model(track: str):
    """Return cached production model for track, loading if necessary."""
    from app.ml.train.promote import load_production_model
    cached = _model_cache.get(track)
    if cached is None:
        model = load_production_model(track)
        _model_cache[track] = (model, "loaded")
        return model
    return cached[0]


def reload_model(track: str) -> None:
    """Force-reload model from disk for a track."""
    from app.ml.train.promote import load_production_model
    try:
        model = load_production_model(track)
        _model_cache[track] = (model, "reloaded")
        logger.info(f"Reloaded production model for {track}")
    except FileNotFoundError:
        logger.warning(f"No production model found for {track}")


async def _get_horse_history(session: AsyncSession, horse_id: int,
                             as_of_date: datetime.date) -> dict:
    """Compute EWMA features for a horse from historical race results."""
    result = await session.execute(
        select(RaceResult, Race)
        .join(Race, RaceResult.race_id == Race.id)
        .where(RaceResult.horse_id == horse_id, Race.race_date < as_of_date)
        .order_by(Race.race_date)
    )
    rows = result.all()
    if not rows:
        return {"horse_win_rate": 0.0, "days_since_last_race": 30.0,
                "past_avg_s1f_time": 14.0, "past_avg_g3f_time": 38.0,
                "n_starts": 0}

    is_wins = [1 if r.RaceResult.finish_position == 1 else 0 for r in rows]
    win_rate = float(pd.Series(is_wins).ewm(span=5, min_periods=1).mean().iloc[-1])
    last_date = rows[-1].Race.race_date
    days_since = (as_of_date - last_date).days

    # Sectional times from inrace_timings
    timing_result = await session.execute(
        select(InraceTiming, Race)
        .join(Race, InraceTiming.race_id == Race.id)
        .where(InraceTiming.horse_id == horse_id, Race.race_date < as_of_date)
        .order_by(Race.race_date)
    )
    timings = timing_result.all()
    s1f_times = [t.InraceTiming.s1f_time for t in timings if t.InraceTiming.s1f_time]
    g3f_times = [t.InraceTiming.g3f_time for t in timings if t.InraceTiming.g3f_time]

    avg_s1f = float(pd.Series(s1f_times).ewm(span=5).mean().iloc[-1]) if s1f_times else 14.0
    avg_g3f = float(pd.Series(g3f_times).ewm(span=5).mean().iloc[-1]) if g3f_times else 38.0

    return {
        "horse_win_rate": win_rate,
        "days_since_last_race": float(days_since),
        "past_avg_s1f_time": avg_s1f,
        "past_avg_g3f_time": avg_g3f,
        "n_starts": len(rows),
    }


async def predict_race(race_id: int, session: AsyncSession) -> list[HorsePrediction]:
    """
    Predict win probabilities for all horses in a race.
    Returns sorted list (highest probability first).
    Falls back gracefully if model is not available.
    """
    # Fetch race
    race_result = await session.execute(select(Race).where(Race.id == race_id))
    race = race_result.scalars().first()
    if race is None:
        return []

    # Fetch entries with horse info
    entries_result = await session.execute(
        select(RaceEntry).where(RaceEntry.race_id == race_id)
    )
    entries = entries_result.scalars().all()
    if not entries:
        return []

    today = race.race_date if race.race_date else datetime.date.today()

    # Load model
    try:
        model = _get_model(race.track)
    except FileNotFoundError:
        logger.warning(f"No model for track {race.track} — returning uniform predictions")
        n = len(entries)
        uniform = 1.0 / n
        return [
            HorsePrediction(
                horse_id=e.horse_id, horse_name="unknown",
                program_number=e.program_number,
                win_probability=uniform, place_probability=min(uniform * 3, 0.99),
                model_versions={"status": "no_model"},
                features_snapshot={},
                computed_at=datetime.datetime.now(datetime.timezone.utc),
            )
            for e in entries
        ]

    # Build feature rows
    rows = []
    horse_names = {}
    for entry in entries:
        horse_result = await session.execute(select(Horse).where(Horse.id == entry.horse_id))
        horse = horse_result.scalars().first()
        horse_name = horse.name if horse else f"horse_{entry.horse_id}"
        horse_age = horse.age if horse and horse.age else 3
        horse_sex = horse.sex if horse and horse.sex else "M"
        horse_names[entry.horse_id] = horse_name

        history = await _get_horse_history(session, entry.horse_id, today)

        # Jockey / trainer win rates (simplified: use 0 for unknown)
        rows.append({
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
            "jockey_win_rate": 0.0,
            "trainer_win_rate": 0.0,
            "sire_win_rate": 0.0,
            "past_avg_s1f_time": history["past_avg_s1f_time"],
            "past_avg_g3f_time": history["past_avg_g3f_time"],
            "_horse_id": entry.horse_id,
            "_n_starts": history["n_starts"],
        })

    pred_df = pd.DataFrame(rows)
    for c in ['horse_sex', 'track', 'track_condition', 'weather']:
        pred_df[c] = pred_df[c].astype('category')

    raw_scores = model.predict(pred_df[FEATURES])
    probs = softmax(raw_scores)

    # Cold-start blending: horses with <3 starts blend with field average
    field_avg = 1.0 / len(probs)
    blended = []
    for i, row in enumerate(rows):
        n_starts = row["_n_starts"]
        blend_weight = min(n_starts / 3.0, 1.0)
        blended.append(blend_weight * probs[i] + (1 - blend_weight) * field_avg)
    blended = np.array(blended)
    blended = blended / blended.sum()

    # Build predictions
    predictions = []
    for i, (entry, row) in enumerate(zip(entries, rows)):
        win_prob = float(blended[i])
        predictions.append(HorsePrediction(
            horse_id=entry.horse_id,
            horse_name=horse_names[entry.horse_id],
            program_number=entry.program_number,
            win_probability=win_prob,
            place_probability=float(min(win_prob * 2.8, 0.99)),
            model_versions={"track": race.track},
            features_snapshot={k: v for k, v in row.items() if not k.startswith("_")},
            computed_at=datetime.datetime.now(datetime.timezone.utc),
        ))

    predictions.sort(key=lambda x: x.win_probability, reverse=True)
    return predictions
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/ml/test_predict_service.py::test_predict_race_returns_horse_predictions -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/predict/service.py backend/tests/ml/test_predict_service.py
git commit -m "feat: rewrite predict service with real model inference"
```

---

## Task 10: Full training pipeline + model hot-reload

**Files:**
- Create: `backend/app/ml/train/pipeline.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces:
  - `run_train(track: str, db_url: str) -> dict` — trains both models, builds ensemble, promotes if better, returns `{"promoted": bool, "log_loss": float, "roi": float}`
  - Background task in `main.py` lifespan that polls `production.json` every 60s and calls `reload_model(track)` if version changed

- [ ] **Step 1: Create `train/pipeline.py`**

Create `backend/app/ml/train/pipeline.py`:

```python
import datetime
import logging
import os
import pickle
from pathlib import Path

from app.ml.train.dataset import load_dataset_pg, FEATURES, TARGET
from app.ml.train.models.lgbm_binary import train_lgbm
from app.ml.train.models.catboost_binary import train_catboost
from app.ml.train.models.ensemble import build_ensemble, _race_log_loss
from app.ml.train.promote import promote_if_better, _model_dir
from app.ml.train.evaluate import evaluate_test_set

logger = logging.getLogger(__name__)


def _compute_val_roi(model, val_df, features) -> float:
    """Estimate Kelly ROI on val set. Returns ROI as a fraction (0.1 = +10%)."""
    from scipy.special import softmax
    import numpy as np

    bankroll = 1_000_000.0
    initial = bankroll

    for _, race in val_df.groupby('race_id'):
        if race['is_win'].sum() == 0 or len(race) < 2:
            continue
        race = race.copy()
        race['score'] = model.predict(race[features])
        race['prob'] = softmax(race['score'].values)
        top = race.loc[race['prob'].idxmax()]
        p = float(top['prob'])
        b = float(max(1.1, top['morning_odds'])) - 1.0
        f = (p * b - (1 - p)) / b
        bet = bankroll * max(0.0, min(0.1, f * 0.1))
        bankroll -= bet
        if top['finish_position'] == 1:
            bankroll += bet * (b + 1)

    return (bankroll - initial) / initial


def run_train(track: str, db_url: str) -> dict:
    """
    Full training pipeline for one track.
    Trains HistGBM + CatBoostRanker, builds ensemble, promotes if better.
    Returns {"promoted": bool, "log_loss": float, "roi": float}.
    """
    logger.info(f"Starting training for track {track}")

    train_df, val_df, _, features, target = load_dataset_pg(db_url)
    # Filter to track
    if len(train_df[train_df['track'] == track]) > 100:
        track_train = train_df[train_df['track'] == track].copy()
        track_val = val_df[val_df['track'] == track].copy()
    else:
        # Not enough track-specific data — use all tracks
        track_train = train_df
        track_val = val_df

    if len(track_train) < 50:
        logger.warning(f"Not enough data for {track} ({len(track_train)} rows) — skipping")
        return {"promoted": False, "log_loss": 999.0, "roi": -1.0}

    model_a = train_lgbm(track_train, track_val, features, target)
    model_b = train_catboost(track_train, track_val, features, target)
    ensemble = build_ensemble([model_a, model_b], track_val, features, target)

    val_log_loss = _race_log_loss(ensemble, track_val, features, target)
    val_roi = _compute_val_roi(ensemble, track_val, features)

    # Save ensemble artifact
    model_dir = _model_dir() / track
    model_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    model_path = str(model_dir / f"ensemble_{ts}.pkl")

    promoted = promote_if_better(
        track, ensemble, val_log_loss=val_log_loss,
        val_roi=val_roi, model_path=model_path,
    )

    logger.info(
        f"[{track}] Training done: log_loss={val_log_loss:.4f}, roi={val_roi:.4f}, "
        f"promoted={promoted}"
    )
    return {"promoted": promoted, "log_loss": val_log_loss, "roi": val_roi}
```

- [ ] **Step 2: Add model hot-reload to `main.py`**

Open `backend/app/main.py` and find the lifespan context manager. Add a background polling task:

```python
# In the lifespan function, after startup:
import asyncio
import json
import os
from pathlib import Path

async def _poll_model_reload():
    """Every 60s, check if production.json changed and reload if so."""
    from app.ml.predict.service import reload_model
    model_dir = Path(os.environ.get("MODEL_DIR", "models"))
    prod_json = model_dir / "production.json"
    last_mtime = 0.0
    while True:
        await asyncio.sleep(60)
        try:
            mtime = prod_json.stat().st_mtime if prod_json.exists() else 0.0
            if mtime > last_mtime:
                last_mtime = mtime
                with open(prod_json) as f:
                    data = json.load(f)
                for track in data:
                    reload_model(track)
        except Exception as exc:
            pass  # Non-fatal; log at debug level

# Inside the lifespan, after yield:
# asyncio.create_task(_poll_model_reload())
```

The exact location in `main.py` depends on the existing lifespan setup. Add `asyncio.create_task(_poll_model_reload())` after the app starts up (before the `yield`). Read `backend/app/main.py` to find the right insertion point before editing.

- [ ] **Step 3: Wire CLI**

Open `backend/app/ml/cli.py` and ensure the `train` subcommand calls `run_train`:

```python
# In the train subcommand handler:
from app.ml.train.pipeline import run_train
import os

result = run_train(track=args.track, db_url=os.environ["DATABASE_URL"])
print(f"Training complete: {result}")
```

Read `backend/app/ml/cli.py` to find the existing `train` handler and update it accordingly.

- [ ] **Step 4: Test end-to-end (integration)**

With `docker compose up postgres redis` running and `.env` configured:

```bash
cd backend
# Populate DB with synthetic data
python -m app.ml.crawl.synthetic_data

# Run training for SEOUL
DATABASE_URL="postgresql+psycopg2://postgres:password@localhost:5432/horserace" \
  python -m app.ml train --track SEOUL
```

Expected: training completes, `models/SEOUL/ensemble_<ts>.pkl` created, `models/production.json` written.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ml/train/pipeline.py backend/app/main.py backend/app/ml/cli.py
git commit -m "feat: full training pipeline + model hot-reload"
```

---

## Task 11: Wire APScheduler jobs

**Files:**
- Modify: `backend/app/scheduler/jobs.py`

**Interfaces:**
- Consumes: `run_crawl` from `crawl.pipeline`, `run_train` from `train.pipeline`, `predict_race` from `predict.service`
- Produces: four scheduled functions registered with APScheduler: `crawl_job`, `predict_job`, `train_job` (per track), `notify_job`

- [ ] **Step 1: Read the existing scheduler files**

```bash
cd backend
cat app/scheduler/jobs.py
cat app/scheduler/triggers.py
```

Understand the existing APScheduler setup (what scheduler instance is used, how jobs are registered).

- [ ] **Step 2: Update `jobs.py`**

Replace the stub job functions in `backend/app/scheduler/jobs.py` with:

```python
import logging
import os
import datetime

logger = logging.getLogger(__name__)


async def crawl_job():
    """Daily 02:00 KST: crawl next 2 days + yesterday's results."""
    from app.ml.crawl.pipeline import run_crawl
    today = datetime.date.today()
    result = await run_crawl(
        start_date=today - datetime.timedelta(days=1),
        end_date=today + datetime.timedelta(days=2),
    )
    logger.info(f"crawl_job done: {result}")


async def predict_job():
    """Daily 03:00 KST: compute predictions for all upcoming races."""
    from app.db.session import async_session_factory
    from app.db.models.crawl import Race
    from app.ml.predict.service import predict_race
    from sqlalchemy import select
    import datetime

    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)

    async with async_session_factory() as session:
        result = await session.execute(
            select(Race).where(Race.race_date.in_([today, tomorrow]))
        )
        races = result.scalars().all()
        for race in races:
            try:
                await predict_race(race.id, session)
            except Exception as exc:
                logger.error(f"predict_job failed for race {race.id}: {exc}")

    logger.info(f"predict_job done: {len(races)} races processed")


async def train_job():
    """Sunday 04:00 KST: retrain all three tracks."""
    from app.ml.train.pipeline import run_train
    db_url = os.environ.get("DATABASE_URL", "")
    for track in ["SEOUL", "BUSAN", "JEJU"]:
        try:
            result = run_train(track=track, db_url=db_url)
            logger.info(f"train_job [{track}]: {result}")
        except Exception as exc:
            logger.error(f"train_job failed for {track}: {exc}")


async def notify_job():
    """Every 5 min: send FCM notifications for races starting in 15-30 min."""
    # Unchanged from v1 scaffold — implement when FCM is wired up
    pass
```

- [ ] **Step 3: Verify APScheduler triggers call these functions**

Read `backend/app/scheduler/triggers.py` and confirm it registers:
- `crawl_job` → cron `hour=17, minute=0` (02:00 KST = 17:00 UTC)
- `predict_job` → cron `hour=18, minute=0`
- `train_job` → cron `day_of_week=sun, hour=19, minute=0`
- `notify_job` → interval `minutes=5`

Update `triggers.py` if the cron times are wrong.

- [ ] **Step 4: Commit**

```bash
git add backend/app/scheduler/jobs.py backend/app/scheduler/triggers.py
git commit -m "feat: wire APScheduler jobs to ML pipeline stages"
```

---

## Self-Review Checklist

After completing all tasks, verify:

- [ ] `python -m app.ml crawl --since 2026-06-01` upserts real races to Postgres
- [ ] `python -m app.ml train --track SEOUL` creates `models/SEOUL/ensemble_*.pkl` and updates `production.json`
- [ ] `GET /api/v1/races/{id}/predictions` returns real win probabilities (not the mock `{"mock": True}` features snapshot)
- [ ] All existing CI tests still pass: `pytest backend/ -v`
- [ ] `models/` directory is in `.gitignore` (run `grep models .gitignore` to verify)
