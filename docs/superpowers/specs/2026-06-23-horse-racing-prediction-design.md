# Horse Racing Prediction — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorming complete)
**Scope:** v1 — full system (ML pipeline + backend API + web app + Android shell)

## 1. System overview

### One-liner
A self-hosted web app + thin Android WebView shell that lets Korean horse-racing fans see **AI-predicted win probabilities** for upcoming races, save favorite horses, and get notified before they run.

### Repository layout
```
horse_racing_prediction/
├── backend/                 # FastAPI app (also hosts ML pipeline + serves web build)
│   ├── app/
│   │   ├── main.py
│   │   ├── api/             # HTTP routes (routers)
│   │   ├── core/            # config, security, deps
│   │   ├── db/              # SQLAlchemy models + session
│   │   ├── ml/              # ML pipeline package (see Section 2)
│   │   ├── scheduler/       # APScheduler jobs (crawl, train, predict, notify)
│   │   └── services/        # business logic
│   ├── tests/
│   ├── pyproject.toml
│   └── alembic/             # DB migrations
├── web/                     # React + Vite SPA
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── android/                 # WebView wrapper app
│   ├── app/
│   │   └── src/main/java/.../MainActivity.kt
│   ├── build.gradle.kts
│   └── settings.gradle.kts
├── deploy/
│   ├── docker-compose.yml   # backend + postgres + redis
│   ├── Dockerfile
│   ├── Caddyfile
│   └── prometheus/alerts.yml
├── docs/
│   └── superpowers/specs/
└── README.md
```

### Runtime components
| Component | Tech | Role |
|---|---|---|
| **API server** | FastAPI (uvicorn) | Serves REST API + static web build from `/` |
| **ML pipeline** | Python package imported by API | Crawl → features → train → predict |
| **Postgres** | 16 | All persistent state (races, horses, predictions, users, favorites) |
| **Redis** | 7 | Session/cache, scheduler locks, lightweight queue for push |
| **Scheduler** | APScheduler in-process | Daily: refresh race data, predict next day, send push (see Section 2 for cadence). Weekly: retrain |
| **Web app** | React + Vite SPA, built into `backend/app/static/` | Served as static files by FastAPI |
| **Android shell** | Kotlin + WebView | Single activity that opens `https://<host>/` |
| **Push** | FCM (Firebase Cloud Messaging) | Notify users T-15min before a favorited horse runs |

### Data ownership / interfaces
- The **backend** is the only component that touches the database or the model.
- The **web app** and **Android shell** are pure consumers; they call the API over HTTPS.
- The **ML pipeline** is *imported* by the backend (`from app.ml import predict`) — no HTTP boundary.
- **Crawler** is a CLI subcommand of the backend (`python -m app.ml.cli crawl --since 1990-01-01`), so cron/docker exec can invoke it. It writes to Postgres; the web app never sees raw scraped HTML.

### What is explicitly out of scope (v1)
- No real-money betting integration
- No live odds streaming (we re-snapshot once per day)
- No iOS app
- No admin web UI (admin actions are CLI subcommands)
- No realtime race commentary
- No "forgot password" / email service
- No i18n beyond Korean

## 2. ML pipeline

The ML pipeline has **four stages**, each a separate module under `backend/app/ml/`. Lessons from the four reference projects (Contest_Horse, Horse-Race-Betting-Recommendation-Algorithm, Horse-Racing-Projections, yema) are baked in as design constraints.

**Operational cadence:**
- **Daily** (run by APScheduler around 02:00 KST): crawl the next 2 days of race cards + yesterday's results + back-fill gaps; compute predictions for all upcoming races whose entries are finalized.
- **Weekly** (run Sundays around 03:00 KST): retrain all three per-track candidate models, evaluate on the val set, promote per the rule below.

```
backend/app/ml/
├── cli.py                  # python -m app.ml <command>
├── config.py               # paths, hyperparameters, env overrides
├── registry.py             # MLflow wrapper (params/metrics/artifacts/dataset hash)
├── crawl/                  # Stage 1: KRA scraping (3 tracks, 1990→present)
│   ├── kra_client.py
│   ├── parsers/            # one parser per page type
│   ├── upsert.py           # idempotent Postgres writes
│   └── pipeline.py         # orchestrate: dates → race cards → results
├── features/               # Stage 2: feature engineering
│   ├── asof.py             # compute_as_of(date) — single chokepoint for time safety
│   ├── builders/           # one builder per feature group
│   ├── horse_form.py       # recent finishes, days_rest, body-weight Δ, distance splits
│   ├── jockey_trainer.py   # rolling win rates (overall / per-track / per-distance)
│   ├── pedigree.py         # sire/dam ASoR, sibling avg
│   ├── inrace.py           # S1F/G3F/corner splits + passing-order ranks
│   ├── market.py           # odds & odds-movement snapshots
│   ├── track_condition.py  # going, distance, weather, field_size
│   └── assemble.py         # join builders → single feature matrix
├── train/                  # Stage 3: model training + per-track models
│   ├── dataset.py          # strict time-based split (no leakage)
│   ├── models/
│   │   ├── lgbm_binary.py  # LightGBM binary (win)
│   │   ├── catboost_binary.py
│   │   ├── plackett_luce.py  # LightGBM lambdarank, 16-way ranking
│   │   └── ensemble.py     # weighted blend, weights from val log-loss
│   ├── evaluate.py         # log-loss, Brier, top-1/3/5, calibration, ROI backtest
│   └── promote.py          # promote only if strictly better; per-track gate
└── predict/                # Stage 4: serve predictions
    ├── service.py          # predict_race(race_id) → list[HorsePrediction]
    └── calibration.py      # isotonic / Platt, applied at inference
```

### What we explicitly improve over the references
| Gap in references | Our fix |
|---|---|
| Contest_Horse: "유의미한 변수 부족", "데이터 더 모으면 정확도 ↑" | Richer crawl + per-horse pedigree, in-race splits, odds movement |
| Horse-Race-Betting-Recommendation-Algorithm: 9 features, ad-hoc normalization | 50+ features, leakage-safe rolling stats, native CatBoost categoricals |
| All references: no time-based split visible, no test discipline | Strict time-based train/val/test |
| All references: only accuracy reported | Log-loss + Brier + calibration plot + Kelly-criterion ROI backtest |
| No version tracking anywhere | MLflow run per training, dataset hash, model promoted via a single rule |
| Single global model for all tracks | **Per-track models** (Seoul / Busan / Jeju) — each track has its own training & promotion |

### Stage 1 — Crawl
- **Tracks & window:** Seoul + Busan + Jeju, **1990-01-01 → present**, idempotent re-runs.
- **Storage:** normalized Postgres tables:
  - `races`, `race_entries`, `race_results`
  - `horses`, `jockeys`, `trainers`
  - `pedigree` (sire_id, dam_id, sire_sire_id, …) — **new**
  - `inrace_timings` (S1F, G3F, corner positions, passing-order rank) — **new**
  - `odds_snapshots` (snapshot_time, win_odds, place_odds) — **new**
  - `scratchings` (declared scratch / late vet scratch / DQ) — **new**
- **Crawl sources:** `race.kra.co.kr`, `studbook.kra.co.kr`, `kra.co.kr`, plus KRA's public odds/Racing Calendar endpoints. Two-pass per race date: (1) race card + entries, (2) results + in-race timings + final odds.
- **Idempotency:** unique keys on every table; upsert, never delete. A `crawl_state` table records (track, last_crawled_date, last_status). The daily job crawls the next 2 days of cards + yesterday's results + back-fills any gaps.
- **Failure mode:** failed dates go to `crawl_failures`; retried with exponential backoff; partial failure of the daily job is acceptable (the API keeps serving the last good snapshot).

### Stage 2 — Features
For each `(race, horse)` row, the model gets ~50+ features:

| Group | Examples | Source |
|---|---|---|
| **Horse form** | wins_last_5, avg_finish_last_5, place_rate_last_5, days_since_last_race, lifetime_starts, body_weight_delta, distance_splits | `race_results`, `race_entries` |
| **Jockey / trainer** | jockey_win_rate_365d, trainer_win_rate_365d, combo_win_rate, jockey_track_win_rate | `race_results` |
| **Pedigree (new)** | sire_avg_earnings_index, dam_avg_earnings_index, sire_win_rate_offspring | `pedigree` |
| **In-race (new)** | avg_S1F_rank_last_5, avg_G3F_rank_last_5, avg_corner1_rank | `inrace_timings` |
| **Market (new)** | morning_win_odds (T-24h), final_win_odds, odds_movement (final/morning), place_odds | `odds_snapshots` |
| **Track / race** | distance_m, surface, track_condition, weather, field_size, grade, race_class | `races` + `race_entries` |
| **Horse identity** | sex, age, breed_origin, import_year | `horses` |

**Leakage chokepoint:** every rolling/leakage-prone builder calls `compute_as_of(target_race_date)`. Tests assert that no builder queries rows where `race_date >= target_race_date`. A pre-commit hook + a CI test inserts a synthetic "future" row and verifies it never appears in any training feature.

### Stage 3 — Train
- **Models trained per track** (Seoul / Busan / Jeju). Each track gets its own training run; promotion is per-track.
- **Three candidate models per track** in v1:
  1. **LightGBM binary** (win = 1) — v1 baseline
  2. **CatBoost binary** — handles high-cardinality categoricals (jockey_id, trainer_id, sire_id)
  3. **LightGBM lambdarank (Plackett–Luce)** — 16-way ranking objective, output is a softmax over the field
- **Ensemble:** weighted average of the two binary models' probabilities (weight = inverse val log-loss). The Plackett–Luce model is kept in the same registry but only promoted if its log-loss beats the best binary model on the val set.
- **Strict time-based split:**
  - Train: 1990–2020
  - Val: 2021–2023
  - Test: 2024–2025 (held out, used **once** for the final reported metric)
  - No random k-fold. A separate `oos_2026_h1.json` is held back for post-launch monitoring.
- **Metrics logged to MLflow per run:**
  - Log-loss (primary), Brier score
  - Top-1 / Top-3 / Top-5 accuracy
  - Calibration: reliability-diagram PNG + expected calibration error (ECE)
  - **Betting backtest**: simulated 1/4-Kelly bets on the top model pick per race using simulated market odds. Logs ROI, max drawdown, hit rate.
- **Promotion rule (per track):** a new run replaces the current `production` model for that track **only if** its val log-loss is strictly better than the current production AND the ROI backtest is non-negative. Otherwise the old model stays and the run is logged as `rejected`. We keep the last 5 rejected runs around for inspection.
- **Dataset version pinning:** each MLflow run records the SHA256 of the training feature matrix file. Recomputing features (e.g., adding a new builder) produces a new dataset hash, so old model artifacts can never be silently mixed with new data.

### Stage 4 — Predict
- `predict_race(race_id) -> list[HorsePrediction]` — returns one row per horse, sorted by predicted probability descending.
- Output schema:
  ```python
  class HorsePrediction(BaseModel):
      horse_id: int
      horse_name: str
      program_number: int
      win_probability: float       # 0..1, calibrated
      place_probability: float     # 0..1, calibrated (top-3)
      model_versions: dict[str, str]  # {"lgbm": "...", "catboost": "...", "ensemble": "..."}
      features_snapshot: dict      # actual values used (debuggability)
      computed_at: datetime
  ```
- **Calibration:** isotonic regression fit on a held-out calibration slice, applied at inference. Probabilities are renormalized across the field so they sum to 1.
- **Cold start:** if a horse has <3 lifetime starts, blend the model output with a Bayesian field-average prior, weighted by `n_starts / 3`.
- **Operational guarantees:**
  - If the scheduled predict run fails, the API serves the **last known** predictions for that race. We never return 500 for a missing prediction.
  - `GET /api/v1/ml/status` exposes: per-track model version, last training date, last successful predict run, ECE drift over the last 4 weeks.

### Observability & reproducibility
- **MLflow** at `mlruns/` (or a remote MLflow server in production) — every training run is queryable.
- A weekly scheduled job runs the **current production model** on the most recent week of completed races (no future leak) and logs the live log-loss + ROI to MLflow. If live performance degrades by more than a threshold vs. backtest, the job raises an alert.
- All model artifacts are content-addressed; rolling back is editing a single `production.json` pointer.

## 3. Backend API (FastAPI)

The FastAPI app is the **only** component that touches Postgres, the model, or the scheduler. It serves the React web build as static files and exposes a versioned JSON API for the SPA / Android shell.

### Layered structure
```
backend/app/
├── main.py                 # FastAPI app factory, lifespan, router mounting, static mount
├── api/                    # HTTP layer — thin, no business logic
│   ├── deps.py             # auth, db session, current_user
│   ├── v1/
│   │   ├── auth.py         # POST /auth/register, /auth/login, /auth/refresh
│   │   ├── races.py        # GET /races?date=, GET /races/{id}
│   │   ├── predictions.py  # GET /races/{id}/predictions
│   │   ├── favorites.py    # CRUD /favorites
│   │   ├── notifications.py# POST /devices (FCM token), preferences
│   │   ├── ml.py           # GET /ml/status (public health)
│   │   └── meta.py         # GET /tracks, /jockeys lookup
├── core/
│   ├── config.py           # pydantic-settings; env-driven
│   ├── security.py         # bcrypt, JWT issue/verify
│   ├── logging.py          # structured JSON logs
│   └── errors.py           # exception → HTTP mapper
├── db/
│   ├── base.py             # SQLAlchemy declarative base
│   ├── session.py          # async engine + session factory
│   ├── models/             # ORM tables (mirror crawl tables + user tables)
│   └── migrations/         # alembic
├── services/               # business logic — pure functions over db + ml
│   ├── race_service.py
│   ├── prediction_service.py
│   ├── favorite_service.py
│   └── notification_service.py
├── ml/                     # Stage 1–4 from Section 2
├── scheduler/
│   ├── jobs.py             # APScheduler definitions
│   └── triggers.py         # cron-like definitions
└── static/                 # built React app (vite build output, copied here in CI)
```

### Data model (new tables beyond the ML crawl tables)
| Table | Purpose | Key columns |
|---|---|---|
| `users` | Account | id, email (uniq), password_hash, created_at |
| `sessions` | Refresh tokens | id, user_id, refresh_token_hash, expires_at, revoked_at |
| `favorites` | User → horse | user_id, horse_id, created_at  (uniq on pair) |
| `devices` | FCM push tokens | id, user_id, fcm_token (uniq), platform, last_seen_at |
| `notification_log` | What was sent | id, user_id, device_id, race_id, kind, sent_at, status |

### API contract (v1)
All endpoints are prefixed `/api/v1`. Auth uses **JWT access tokens (15 min) + refresh tokens (30 days, stored hashed in `sessions`)**.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/register` | — | Create account (email + password) |
| POST | `/auth/login` | — | Issue access + refresh |
| POST | `/auth/refresh` | refresh | Rotate refresh, issue new access |
| POST | `/auth/logout` | refresh | Revoke refresh |
| GET | `/races` | — | List races for a date `?date=YYYY-MM-DD&track=SEOUL` |
| GET | `/races/{race_id}` | — | Race card: horses, jockeys, weights, morning odds |
| GET | `/races/{race_id}/predictions` | — | Per-horse win/place probabilities |
| GET | `/horses/{horse_id}` | — | Horse bio + recent form |
| GET | `/horses/{horse_id}/history` | — | Past finishes |
| GET | `/favorites` | user | List the current user's favorite horses |
| POST | `/favorites` | user | Add a favorite `{horse_id}` |
| DELETE | `/favorites/{horse_id}` | user | Remove |
| POST | `/devices` | user | Register FCM token `{fcm_token, platform}` |
| DELETE | `/devices/{id}` | user | Unregister |
| GET | `/ml/status` | — | Per-track model version + last-train + last-predict timestamps |
| GET | `/tracks` | — | List of tracks (for the date picker) |
| GET | `/healthz` | — | Liveness for orchestrator |
| GET | `/readyz` | — | Readiness: DB reachable, model loaded |

**Public vs authed:** all **read** endpoints are public (no login wall). Only `/favorites/*` and `/devices/*` require auth. Matches the yema model where the schedule and predictions are open.

**Response shape:** every list endpoint returns `{items: [...], next_cursor: null}` even when there's no cursor, so the client code is uniform.

**Errors:** `{error: {code: "RACE_NOT_FOUND", message: "..."}}` with stable error codes the SPA can switch on. Validation errors come from FastAPI's default 422.

### Static file serving & CORS
- `vite build` outputs to `backend/app/static/`. FastAPI mounts it at `/` with `html=True` so client-side routes fall back to `index.html`.
- The SPA and the API share the same origin → **no CORS configuration needed** in production.
- For local dev, Vite runs on `:5173` and proxies `/api/*` to the FastAPI `:8000`. The proxy config is in `web/vite.config.ts`.
- API docs at `/api/docs` (Swagger UI) and `/api/redoc` — gated by `ENVIRONMENT != "production"` unless `ENABLE_DOCS=1`.

### Auth details
- Password hashing: **bcrypt** (passlib), cost factor 12.
- Access token: HS256 JWT, 15-minute lifetime, claims `{sub: user_id, exp, iat}`.
- Refresh token: opaque random 32-byte token, stored hashed (sha256) in `sessions`. Rotation on every use; old token is revoked. Reuse of a revoked token revokes the entire family (theft detection).
- Rate limiting on `/auth/*` via a simple Redis token bucket (10 req/min/IP). Implemented as a FastAPI dependency.

### Push notifications (FCM)
- The Android shell collects an FCM token at first launch and `POST`s it to `/devices` (after login).
- The scheduled job "notify" runs every 5 minutes, finds races starting in the next 15–30 minutes, and for each user with a favorite horse in that race, sends an FCM data message `{type: "race_reminder", race_id, horse_id}`.
- FCM credentials are loaded from `firebase-credentials.json` (path in env). If the file is missing, the scheduler logs a warning and skips push (the rest of the system still works).
- All sends are recorded in `notification_log` for auditing.

### Configuration & secrets
- `pydantic-settings` reads from env + `.env` (gitignored). Keys: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ENVIRONMENT`, `FIREBASE_CREDENTIALS_PATH`, `CRAWL_USER_AGENT`, `LOG_LEVEL`.
- Secrets are never logged. The structured logger redacts known secret fields.
- `.env.example` (committed) lists every key with a dummy value.

### Logging & monitoring
- Structured JSON logs to stdout (one event per line): `{ts, level, request_id, user_id?, route, status, latency_ms, ...}`.
- Request ID middleware: assigns a UUID to every request, includes it in response headers, propagates to scheduler jobs.
- `/metrics` endpoint exposes Prometheus-format counters: `http_requests_total{route,status}`, `http_request_duration_seconds`, `prediction_requests_total`, `ml_inference_seconds`. Matches the prometheus integration in the `HorseRaceBetting` reference, even though our backend is Python instead of Java.

### Error handling philosophy
- Any unhandled exception → 500 with `{error: {code: "INTERNAL", message: "..."}}` and a request_id. The full traceback is logged at ERROR; the client sees only the request_id so they can be supported.
- Predict endpoint never returns 5xx due to missing/old predictions — it returns the last known snapshot with `stale: true` in the response and a `Warning` header.

## 4. Web app (React + Vite SPA)

The web app is what users actually see. It's a single-page React app, built with Vite, served as static files from the FastAPI backend. The Android shell just wraps this same app in a WebView, so we have **one** UI codebase for both surfaces.

### Stack
- **React 18** + **TypeScript** (strict mode)
- **Vite 5** for dev server + build
- **React Router 6** for client-side routing
- **TanStack Query (React Query)** for server state, caching, retries, background refetch
- **Zustand** for the small amount of client state (auth, theme, favorite-filter)
- **Tailwind CSS** for styling (no custom design system in v1; Tailwind keeps the CSS file small and we can migrate to a real design system later if needed)
- **Recharts** for any in-app charts (calibration curve in admin, recent-form sparkline on horse card)
- **react-hook-form + zod** for forms (login, register)
- **Vitest + React Testing Library** for unit/component tests
- **Playwright** for the 5–10 critical E2E paths (login, view race, favorite a horse)

### Folder layout
```
web/src/
├── main.tsx                # React entry, providers
├── App.tsx                 # router
├── api/                    # typed API client (one file per resource)
│   ├── client.ts           # fetch wrapper, auth header, error normalization
│   ├── auth.ts
│   ├── races.ts
│   ├── predictions.ts
│   ├── favorites.ts
│   └── ml.ts
├── components/             # reusable presentational
│   ├── RaceCard.tsx
│   ├── HorseRow.tsx
│   ├── ProbabilityBar.tsx
│   ├── OddsMovement.tsx
│   └── EmptyState.tsx
├── features/               # feature-specific (small)
│   ├── auth/
│   ├── races/
│   ├── horse/
│   └── favorites/
├── pages/                  # one per route
│   ├── HomePage.tsx        # race list for selected date
│   ├── RaceDetailPage.tsx
│   ├── HorsePage.tsx
│   ├── LoginPage.tsx
│   ├── RegisterPage.tsx
│   ├── FavoritesPage.tsx
│   └── NotFoundPage.tsx
├── hooks/                  # useAuth, useFavorites, useRace
├── lib/                    # utils (date formatting, prob → % display)
├── types/                  # generated from backend OpenAPI (or hand-mirrored)
└── styles/                 # tailwind globals
```

### Routing
| Path | Page | Notes |
|---|---|---|
| `/` | redirects to `/races/today` | |
| `/races/:date` | `HomePage` — list of races for a date | date in `YYYY-MM-DD` |
| `/races/:date/:raceId` | `RaceDetailPage` — full card + predictions | |
| `/horses/:horseId` | `HorsePage` — bio + recent form + history link | |
| `/favorites` | `FavoritesPage` — horses I'm tracking, next races for them | requires auth |
| `/login` | `LoginPage` | |
| `/register` | `RegisterPage` | |
| `*` | `NotFoundPage` | |

### Key UI screens (sketched)
- **HomePage** — date picker + track filter at top, then a vertical list of races for that date (race #, race name, post time, field size). Tap → RaceDetailPage.
- **RaceDetailPage** — the workhorse screen. Header (race #, name, post time, distance, surface, track, weather, field size). Table of horses with columns: program #, horse name, age/sex, weight, jockey, trainer, morning odds, final odds, **win probability bar** (calibrated %), **place probability %**, star icon (favorite). Sortable by clicking any probability column header. Tapping a horse row → HorsePage.
- **HorsePage** — hero with name + pedigree (sire × dam), lifetime stats, last 10 finishes, "favorites" star.
- **FavoritesPage** — list of favorited horses; for each, the next race date+time it appears in, with a "Set reminder" toggle.

### Auth flow on the web
- Tokens are stored in **memory only** (Zustand store). On page reload, the access token is gone; we use the refresh token (stored in an **httpOnly, Secure, SameSite=Lax cookie** set by the backend) to silently get a new access token via `/auth/refresh`.
- The cookie approach is critical so the **Android WebView** can also stay logged in across app restarts (the WebView keeps the cookie jar like a browser does).
- Login/register forms are minimal: email + password (≥8 chars, mixed). No "forgot password" in v1.

### Real-time-ish updates without WebSockets
- The race list and predictions are **stale-by-design** (refreshed once a day by the scheduler). The web app uses TanStack Query with a `staleTime` of 5 minutes; the user can pull-to-refresh.
- The "next race" countdown on the favorites page uses a local `setInterval` ticker, not server push. Good enough for a 15-minute reminder window.

### i18n
- v1 is **Korean only** (primary market is KRA). The codebase keeps all UI strings in a single `ko.json` and uses `useTranslation()` so we can add English later without code changes.

### Accessibility & mobile
- Tailwind responsive utilities; primary breakpoints target phones first (the Android shell is the dominant surface).
- All interactive elements keyboard-reachable; probability bars have an `aria-label` like "1번마 승률 18%".
- Color is never the only signal — favorites use both a star icon and color.

### Build & deploy
- `vite build` outputs to `web/dist/`. A script `scripts/copy_web_to_backend.sh` copies it into `backend/app/static/`. CI runs this in the build step.
- The app's `base: '/'` (not relative paths) so it works behind any path.

## 5. Android shell (WebView wrapper)

The Android app is **not** a real Android app. It's a single screen whose only job is to load the web app in a WebView, send the FCM token to the backend, and handle back-button navigation. The yema reference had a real native UI — we are explicitly trading that for a 1–2 day implementation and a single UI codebase.

### What it actually does
1. On launch: open a WebView to `<API_BASE_URL>/` (the same URL the browser would use, served by FastAPI).
2. If the WebView is not yet logged in, the user sees the web app's login page. On successful login, the httpOnly refresh-token cookie is stored in the WebView's cookie jar, so subsequent launches stay logged in.
3. Request FCM token via Firebase SDK and forward it to the web app via the JS bridge (see below); the web app then `POST`s it to `/api/v1/devices`.
4. Handle Android back button: navigate the WebView's history if possible, otherwise exit.
5. Show a splash + a loading state while the WebView initializes.

### Project structure
```
android/
├── app/
│   ├── build.gradle.kts
│   ├── src/main/
│   │   ├── AndroidManifest.xml
│   │   ├── java/com/example/horserace/
│   │   │   ├── MainActivity.kt           # hosts the WebView
│   │   │   ├── WebViewConfig.kt          # cookies, file access, JS settings
│   │   │   ├── FcmBridge.kt              # FirebaseMessagingService → JS bridge
│   │   │   ├── JsApi.kt                  # @JavascriptInterface methods
│   │   │   └── DeepLinkRouter.kt         # handles horserace://race/{id} if used
│   │   └── res/
│   │       ├── layout/activity_main.xml  # <WebView /> + splash overlay
│   │       ├── values/strings.xml
│   │       └── values/colors.xml
│   └── google-services.json               # Firebase config (gitignored, template committed)
├── build.gradle.kts
├── settings.gradle.kts
└── README.md
```

### Key technical decisions

**WebView configuration**
- JavaScript enabled, DOM storage enabled, cookies enabled (default).
- `mixedContentMode = MIXED_CONTENT_NEVER_ALLOW` — we serve over HTTPS in production.
- `setAllowFileAccess(false)`, `setAllowFileAccessFromFileURLs(false)`, `setAllowUniversalAccessFromFileURLs(false)`.
- Caches the page so subsequent launches are instant (default WebView cache, sized 10 MB).
- User-Agent is overridden to `HorseRaceAndroid/1.0` so the backend can log which clients are hitting it.

**JS ↔ Native bridge**
- The bridge is used for **two things only**:
  1. **FCM token delivery** — native calls `window.onFcmToken(token)` after `onNewToken`. The web app's auth-aware code then `POST`s it to `/api/v1/devices`.
  2. **Deep links** — when the user taps a system notification, native navigates the WebView to the right URL via `WebView.loadUrl(...)`.
- **Auth is not bridged.** The backend issues the refresh token as an httpOnly cookie, which the WebView's cookie jar handles automatically. The access token lives in the web app's in-memory store (Zustand), identical to the browser case. This keeps the web app code identical between browser and Android — the bridge surface is narrow and only used for things the web app cannot do itself.

**Push notifications (FCM)**
- Firebase Cloud Messaging is integrated the standard way: `google-services.json` + `FirebaseMessagingService` subclass.
- On `onNewToken(token)`, native calls a JS function `window.onFcmToken(token)` on the web app, which `POST`s to `/api/v1/devices` with the current access token.
- On `onMessageReceived(message)`, native displays a system notification. Tapping the notification deep-links to `https://<host>/races/<date>/<raceId>`.
- If Firebase is not configured (e.g., for local dev), the shell compiles and runs without it; the web app simply never receives a token and the FCM-related code paths are no-ops.

**Splash**
- A simple `windowSplashScreen` (Android 12+) showing the app icon for ≤500 ms, then the WebView fades in. No native splash screen design — the goal is fast, not pretty.

**Permissions**
- `INTERNET` only. No location, no storage, no camera, no contacts. Push notification permission is requested implicitly by Android 13+ at first FCM message.

**Build**
- AGP 8.x, Kotlin 2.x, `compileSdk = 34`, `minSdk = 24` (Android 7.0, covers ~98% of devices).
- Single build type in v1: `release` signed by a debug keystore for sideloading. Real Play Store signing is out of scope.
- Build command: `./gradlew :app:assembleRelease` → `app-release.apk`.

### What is **not** in the Android shell (and why)
- ❌ Native UI screens — the WebView IS the UI.
- ❌ Offline mode — if there's no network, the app shows the web app's "you're offline" page.
- ❌ Biometric login / app lock — defer to v2 if requested.
- ❌ Tablet / landscape layouts — phone portrait only. Tailwind handles small-screen polish.
- ❌ iOS — out of scope.

### Build artifact
- One signed `app-release.apk` (~5 MB).
- Distributed as a direct download from a `/download` page on the web app itself (or sideloaded by the user). No Play Store in v1.

## 6. Deployment, dev workflow, and testing

### Local dev workflow
```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   Postgres 16   │    │  Redis 7         │    │  Backend (uvicorn)│
│   localhost:5432│◀──▶│  localhost:6379  │◀──▶│  localhost:8000   │
└─────────────────┘    └──────────────────┘    └────────┬─────────┘
                                                        │ /api/* + /static/*
                                                        ▼
                                              ┌──────────────────┐
                                              │  Vite dev server │
                                              │  localhost:5173  │
                                              └──────────────────┘
                                                        ▲
                                                        │ npm run dev
                                              (developer browser)
```
- `docker-compose up postgres redis` — bring up the two stateful services.
- `cd backend && uvicorn app.main:app --reload` — FastAPI on `:8000`.
- `cd web && npm run dev` — Vite on `:5173`, proxies `/api/*` → `:8000`.
- Android: open `android/` in Android Studio, run on an emulator. The emulator hits the backend at `http://10.0.2.2:8000` (the host machine) via a debug build flavor with an overrideable `API_BASE_URL`.
- ML pipeline runs locally as CLI: `python -m app.ml crawl --since 1990-01-01`, `... train --track SEOUL`, `... predict --race-id 12345`.

### Production deployment
- **Single VM** (or single container host) for v1 — keep ops simple.
- `deploy/docker-compose.yml` runs three services: `backend`, `postgres`, `redis`. The web build is baked into the backend image.
- **Reverse proxy:** Caddy (auto-HTTPS) in front of the backend container. TLS terminates at Caddy. The `Caddyfile` also handles HTTP→HTTPS redirects.
- **Static assets:** served by FastAPI from `app/static/` (Caddy adds `Cache-Control: public, max-age=3600` for hashed assets, `no-cache` for `index.html`).
- **Backups:** nightly `pg_dump` to a local volume + offsite object storage. The model registry (`mlruns/`) is content-addressed and re-derivable from data, so it doesn't need a separate backup — but we do back it up anyway.
- **Secrets:** `.env` on the VM, never committed. Caddy + the backend read from it. No secret manager in v1.
- **Observability:**
  - Structured JSON logs to stdout, collected by `journald` and shipped by Caddy to a single `app.log` file.
  - `/metrics` scraped by Prometheus (host-side), 15-day retention. No Grafana in v1 — a couple of pre-built alert rules in `deploy/prometheus/alerts.yml` are enough.
  - Uptime check: a 5-minute `curl /healthz` cron from an external monitor (UptimeRobot, free tier) with email alerts.
- **Migrations:** Alembic. `alembic upgrade head` runs as part of the backend container's `entrypoint.sh` before uvicorn starts. Migrations are forward-only in production; rollbacks are done by writing a new migration.
- **Schema versioning:** MLflow + dataset hash means a model artifact is always tied to the feature schema it was trained on. Predictions always use a model trained on a feature schema version that the current `assemble.py` can reproduce.

### CI/CD
- **GitHub Actions** on every push to `main`:
  - `backend` job: `ruff`, `mypy`, `pytest` (unit + integration with testcontainers for Postgres/Redis).
  - `web` job: `tsc --noEmit`, `eslint`, `vitest`, `vite build`, Playwright E2E against a docker-compose stack.
  - `android` job: `./gradlew :app:assembleRelease :app:lint :app:test`.
  - If all green: build a `backend` Docker image tagged with the git SHA, push to GitHub Container Registry.
- **Deploy:** a manual `workflow_dispatch` action on the `deploy` workflow pulls the new image, runs `docker compose up -d` on the VM via SSH, and waits for `/readyz`. No blue/green in v1 — a brief ~10s downtime on redeploy is acceptable.

### Test strategy
| Layer | Tool | Scope | Target coverage |
|---|---|---|---|
| **ML unit tests** | `pytest` | Feature builders, time-leakage guards, dataset splitter, model serialization round-trip, calibration | 80%+ on `app/ml/features/**` and `app/ml/train/**` |
| **ML property tests** | `hypothesis` | "given any target date, no feature includes rows with `race_date >= target`" | 100% on the leakage chokepoint |
| **ML evaluation** | `pytest` (slow, weekly) | Full backtest on 2024–2025 held-out; checks log-loss within bound of last known run | N/A — produces a JSON report |
| **Backend unit** | `pytest` | Services, security, deps | 80%+ on `app/services/**` and `app/core/**` |
| **Backend integration** | `pytest` + testcontainers | Real Postgres + Redis; tests API endpoints + auth flows | All endpoints have ≥1 happy + 1 error test |
| **Backend contract** | `pytest` + `schemathesis` | Fuzzes the OpenAPI schema; catches 500s and shape regressions | Runs on every PR |
| **Web unit** | `vitest` + RTL | Components, hooks, form validation | 70%+ on `components/**` and `hooks/**` |
| **Web E2E** | Playwright | Login, register, view race, see prediction, favorite a horse, get to favorites page | 5–10 critical paths |
| **Android** | `espresso` + unit | MainActivity WebView loads URL, back button navigates, FCM bridge sets `window.__FCM_TOKEN__` | Smoke tests; no full E2E in v1 |

### Definition of done (v1)
- [ ] `docker compose up` brings the whole stack up on a fresh VM in <5 minutes.
- [ ] The first end-to-end happy path works in a browser: visit `/`, see today's races, click a race, see predictions, register, log in, favorite a horse, see it in `/favorites`.
- [ ] The same happy path works inside the Android WebView on an emulator.
- [ ] `python -m app.ml train --track SEOUL` produces a new model in MLflow and, if better, promotes it to `production.json`.
- [ ] `python -m app.ml crawl --since 1990-01-01` populates Postgres idempotently without manual intervention.
- [ ] `/metrics` shows traffic; Prometheus alerts wired.
- [ ] `/api/docs` shows a complete OpenAPI schema; no 500s from schemathesis fuzzing.
- [ ] The full test suite runs in CI in <10 minutes; all green on `main`.

### What we explicitly defer
- **Horizontal scaling** — single VM, single backend process. If we hit it, we split ML and API.
- **Real Play Store / App Store** — direct APK download only.
- **A/B testing the model** — promote-only-if-better is enough for v1; an A/B framework is overkill.
- **Admin web UI** — admin actions are CLI subcommands.
- **Multi-tenant / multi-user-org** — single consumer audience.
- **Real-money betting integration** — explicitly out of scope.
- **Email transactional (forgot-password, race digest)** — not in v1; we have no email service.
- **iOS app** — not in v1.
- **A second locale** — Korean only in v1, strings in `ko.json` so adding English is mechanical.
