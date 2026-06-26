# Horse Racing Prediction — v2 Design

**Date:** 2026-06-26
**Status:** Approved (brainstorming complete)
**Scope:** v2 — ML pipeline completion + web UI data binding + admin dashboard

## 1. Overview

v1 completed the full scaffolding: auth, DB schema, API routes, React SPA, Android shell, and deployment infrastructure. v2 turns the stubs into a working system and adds an admin dashboard.

### v2 scope

| Area | Goal |
|------|------|
| **ML pipeline** | Fix crawl → DB persistence; implement real training pipeline; connect prediction service to actual models |
| **Web UI** | Bind existing React pages to real API data; show actual predictions |
| **Admin UI** | ML monitoring dashboard + data management — new `/admin/*` routes in the existing SPA |

### What does NOT change in v2

- DB schema for existing tables (v1 as-is; v2 adds 3 new tables — see Section 6)
- API contract (additions only, no breaking changes)
- Auth system (JWT + refresh tokens)
- Deployment structure (single VM, docker-compose)

### Dependency order

```
ML pipeline (Stage 1–4)
        ↓
Web UI data binding     ← Admin UI (parallel, independent)
```

Admin UI can be built in parallel with the ML pipeline — it only needs new admin API endpoints, not the ML pipeline itself.

---

## 2. ML Pipeline

### Current state (from code audit)

| Component | Status | Notes |
|-----------|--------|-------|
| `crawl_2026.py` + `kra_live_parser.py` | ✅ Working | KRA live site scraping with retry, EUC-KR encoding |
| `kra_html_parser.py` | ✅ Working | Local HTML dump fallback |
| `synthetic_data.py` | ✅ Working | 1500-race synthetic dataset for testing |
| `dataset.py` feature engineering | ✅ Working | EWMA win rates, sectional times, physical attributes |
| `HistGradientBoostingRegressor` | ✅ Working | Pointwise regressor + softmax → ranked probabilities |
| `experiment_ranker.py` (CatBoostRanker) | ✅ Experimental | YetiRank listwise ranker, validated in isolation |
| `evaluate.py` / `evaluate_last_week.py` / `evaluate_real_2026.py` | ✅ Working | Kelly criterion ROI simulation on 2026 test data |
| `simulate_today_results.py` | ✅ Working | Live betting simulation with actual odds |
| `check_trio.py` | ✅ Working | Trio prediction accuracy vs. actual 2026 results |
| `crawl/upsert.py` | ❌ Stub | Root cause of crawl → DB persistence failure |
| `predict/service.py` | ❌ Stub | Returns random predictions — API uses this |
| `predict/calibration.py` | ❌ Stub | No probability calibration |
| `train/promote.py` | ❌ Stub | No model promotion logic |
| Feature builder stubs | ❌ Stub | All 6 builders are placeholders (feature logic lives in dataset.py) |

### Stage 1 — Crawl + DB persistence

**Problem:** `crawl/upsert.py` is unimplemented. Scraping works but data is never written to Postgres.

**Fix:** Implement idempotent upserts using identifying keys:

| Table | Identifying key |
|-------|----------------|
| `races` | `(track, race_date, race_number)` |
| `horses` | `(registration_number)` or `(name, foal_year)` |
| `jockeys` | `(name, license_number)` |
| `trainers` | `(name, license_number)` |
| `race_entries` | `(race_id, program_number)` |
| `race_results` | `(race_id, program_number)` |
| `inrace_timings` | `(race_id, horse_id)` |
| `odds_snapshots` | `(race_id, horse_id, snapshot_time)` |

**Crawl strategy (3-layer fallback, unchanged):**
1. Local HTML dumps (`backend/data/kra_dumps/*.html`)
2. Live KRA site scraping (`kra_live_parser.py`)
3. Synthetic data (`synthetic_data.py`) — testing only

**State tracking:**
- `crawl_state` table: `(track, last_crawled_date, last_status)`
- `crawl_failures` table: failed dates with error message + retry count
- Daily job crawls next 2 days + yesterday's results + backfills gaps
- Failed dates retried with exponential backoff on next run

### Stage 2 — Feature engineering

**Keep `dataset.py` inline feature computation as-is.** The feature builder stubs (`features/builders/`) remain as architectural placeholders. Refactoring working inline code into the builder pattern is not a v2 goal.

**Current features (already working):**

| Group | Features |
|-------|---------|
| Horse form | `horse_win_rate` (EWMA span=5, shifted), `past_avg_s1f_time`, `past_avg_g3f_time`, `days_since_last_race` |
| Jockey / trainer | `jockey_win_rate`, `trainer_win_rate` (EWMA, shifted) |
| Pedigree | `sire_win_rate` (EWMA) |
| Physical | `program_number`, `carry_weight_kg`, `body_weight_kg`, `horse_age`, `horse_sex` |
| Race context | `distance_m`, `field_size`, `track`, `track_condition`, `weather`, `morning_odds` |

**v2 additions:**
- Recent N-race rank pattern (last 3 / last 5 finish positions as separate features)
- Per-track win rate split (separate `horse_win_rate_seoul`, `_busan`, `_jeju`)

**Leakage guard (unchanged):** all rolling stats use `.shift(1)` before groupby so no future rows leak into training features.

**Time-based split:**
```
Train: 2021-01-01 → 2024-12-31
Val:   2025-01-01 → 2025-12-31
Test:  2026-01-01 → present (held out for monitoring)
```

### Stage 3 — Training

Three models per track (Seoul / Busan / Jeju):

| Model | Type | Status | v2 action |
|-------|------|--------|-----------|
| `HistGradientBoostingRegressor` | Pointwise regressor | Working | Keep as baseline |
| `CatBoostRanker` (YetiRank) | Listwise ranker | experiment_ranker.py only | Merge into main pipeline |
| Ensemble | Weighted average | Stub | Implement: weights = inverse val log-loss |

**CatBoost hyperparameters (from experiment_ranker.py):**
- Loss: `YetiRank`
- Iterations: 500, learning rate: 0.05
- Categorical features: `jockey_id`, `trainer_id`, `horse_sex`, `track`, `track_condition`, `weather`
- Group column: `race_id` (race-level ranking)

**Promotion rule (per track):** new model replaces production only if val log-loss is strictly better AND Kelly ROI backtest is non-negative. Otherwise logged as rejected, existing model stays.

**Metrics logged per run:**
- Log-loss (primary), Brier score
- Trio hit rate (삼복승 적중률) — already in `check_trio.py`
- Kelly betting ROI on val set — already in `evaluate.py`
- Top-1 / Top-3 accuracy

**Model artifact storage:** `models/{track}/production.json` pointer file + versioned model files. Hot-reload reads the pointer file.

### Stage 4 — Prediction serving

**Problem:** `predict/service.py` returns random predictions. The actual inference logic is in `predict_today.py`.

**Fix:** Port `predict_today.py` inference logic into `service.py`:

```python
# predict/service.py
def predict_race(race_id: int) -> list[HorsePrediction]:
    # 1. Load production model for track (from memory cache)
    # 2. Fetch race entries + horse/jockey/trainer history from DB
    # 3. Compute features (same logic as dataset.py)
    # 4. model.predict() → raw scores
    # 5. softmax → probabilities
    # 6. calibrate (isotonic regression)
    # 7. cold-start blend if horse has <3 starts
    # 8. return sorted list[HorsePrediction]
```

**Calibration (`calibration.py`):** Isotonic regression fit on val set (2025), applied at inference. Probabilities renormalized to sum to 1 across the field.

**Cold-start:** horses with <3 lifetime starts → blend model output with field-average prior, weighted by `n_starts / 3`.

**Model hot-reload:** after retraining, `production.json` pointer is updated. A FastAPI background task polls the pointer file every 60 seconds and reloads the in-memory model if the version changed. No restart required.

**Operational guarantee:** if predict fails, API returns last cached predictions with `stale: true`. Never returns 5xx for missing predictions.

**Prediction cache:** results stored in `race_predictions` table to avoid recomputing for the same race on repeated requests.

---

## 3. Web UI data binding

All React pages and components exist. v2 fills in the data layer.

### Pages to wire up

**HomePage** (`/races/:date`)
- `useQuery` → `GET /api/v1/races?date=&track=`
- Render `RaceCard` list (component exists)
- Date picker + track filter state synced to URL query params

**RaceDetailPage** (`/races/:date/:raceId`)
- Parallel queries: `GET /races/{id}` + `GET /races/{id}/predictions`
- Bind `win_probability` to `ProbabilityBar` (component exists)
- Horse name tap → HorsePage

**HorsePage** (`/horses/:horseId`)
- `GET /horses/{id}` + `GET /horses/{id}/history`
- Recent 10 finishes table

**FavoritesPage** (`/favorites`)
- Auth-gated, `GET /favorites`
- Show each favorited horse's next scheduled race

### API client (`web/src/api/`)

Fill in `races.ts`, `predictions.ts`, `favorites.ts`, `horses.ts` with real fetch logic + TypeScript types hand-mirrored from backend OpenAPI schema (v1 pattern, unchanged).

### What does NOT change

- No new components — prop-binding only
- No new routes
- No state management changes (Zustand as-is)
- No new dependencies

---

## 4. Admin UI

### Access control

Caddy Basic Auth on `/admin/*` and `/api/v1/admin/*` paths using `ADMIN_USER` / `ADMIN_PASS` environment variables. No separate admin account in the DB.

### Routes (added to existing React SPA)

Both pages are lazy-imported so they do not affect the user-facing bundle.

**ML Monitoring** (`/admin/ml`)

| Section | Content |
|---------|---------|
| Model status | Per-track (Seoul / Busan / Jeju) production model version + last training timestamp |
| Performance metrics | Log-loss, trio hit rate, Kelly ROI — weekly trend line chart (Recharts) |
| Recent prediction accuracy | Last week's races: predicted top-3 vs. actual top-3 table |
| Training history | Last 10 training runs: date, metrics, promoted/rejected |

**Data Management** (`/admin/data`)

| Section | Content |
|---------|---------|
| Crawl status | Per-track last successful crawl date + next scheduled crawl |
| Failure list | `crawl_failures` rows — date, error message, retry count, retry button |
| DB summary | Total record counts (races, horses, jockeys), most recent data date |

### New API endpoints

```
GET  /api/v1/admin/ml/status    # model versions + performance metrics
GET  /api/v1/admin/data/status  # crawl state + failure list + DB counts
POST /api/v1/admin/data/retry   # trigger re-crawl for a specific failed date
```

All three endpoints are protected by the same Basic Auth as the frontend routes.

### Charts

Recharts (already a dependency) — no new libraries added.

---

## 5. Orchestration

### Design principle

Each pipeline stage is a single callable function — invocable from both CLI and APScheduler with identical behavior.

```python
from app.ml.crawl.pipeline import run_crawl
from app.ml.train.pipeline import run_train
from app.ml.predict.service import run_predict_all

# CLI:        python -m app.ml crawl --since 2026-01-01
# Scheduler:  scheduler.add_job(run_crawl, ...)
```

### Schedule

| Job | Schedule | Function |
|-----|----------|---------|
| Crawl | Daily 02:00 KST | `run_crawl(since, until)` |
| Predict | Daily 03:00 KST (after crawl) | `run_predict_all(date)` |
| Retrain | Sunday 04:00 KST | `run_train(track)` per track |
| Notify | Every 5 min | `run_notify()` — unchanged from v1 |

### Failure handling

| Failure | Behavior |
|---------|---------|
| Crawl fails | Log to `crawl_failures`, retry on next run with exponential backoff |
| Predict fails | Keep last successful predictions, set `stale: true`, surface in admin UI |
| Retrain fails | Keep current production model, log as rejected run, show warning in admin ML dashboard |

### Model hot-reload

After retraining completes, `models/{track}/production.json` pointer is updated. FastAPI lifespan background task polls the pointer file every 60 seconds and reloads the in-memory model if the version changed. No process restart required.

---

## 6. New tables

Three new tables are needed in v2 (all require Alembic migrations):

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `race_predictions` | Prediction cache per race | `race_id`, `horse_id`, `win_probability`, `place_probability`, `model_version`, `computed_at`, `is_stale` |
| `crawl_failures` | Failed crawl dates for retry | `track`, `race_date`, `error_message`, `retry_count`, `last_attempted_at` |
| `crawl_state` | Per-track crawl progress tracking | `track`, `last_crawled_date`, `last_status` (may already exist from v1 migration — check before adding) |

---

## 7. Definition of done (v2)

- [ ] `python -m app.ml crawl --since 2026-01-01` populates Postgres with real race data idempotently
- [ ] `python -m app.ml train --track SEOUL` produces a promoted model (CatBoostRanker or ensemble beats baseline)
- [ ] `GET /api/v1/races/{id}/predictions` returns real calibrated probabilities (not random)
- [ ] HomePage shows today's races; RaceDetailPage shows prediction bars with real numbers
- [ ] `/admin/ml` shows model version, log-loss, ROI trend chart
- [ ] `/admin/data` shows crawl status and allows manual retry of failed dates
- [ ] All existing CI tests still pass; new admin endpoints have ≥1 happy + 1 error test
- [ ] No regression in auth, favorites, or notification flows

---

## 8. Explicitly out of scope (v2)

- Feature builder refactor (`features/builders/` stubs remain as-is)
- MLflow integration (model artifacts stored as files, not tracked in MLflow)
- iOS app
- Email service (forgot-password, race digest)
- Real-money betting integration
- Horizontal scaling
- English locale
