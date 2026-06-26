# Web UI + Admin Dashboard v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the predictions API bridge, and add an admin dashboard with ML monitoring and data management pages protected by Caddy Basic Auth.

**Architecture:** The React SPA gains `/admin/*` lazy-loaded routes. Caddy guards both the page routes and the API endpoints with HTTP Basic Auth. The backend exposes three new admin endpoints. The `prediction_service.py` bridge is fixed to pass a DB session instead of entries list to the new predict service interface.

**Tech Stack:** React 18, TypeScript, TanStack Query, Tailwind CSS, Recharts (already a dep), FastAPI, Caddy Basic Auth

## Global Constraints

- No new npm packages beyond what's already in `web/package.json` — use Recharts for charts (already installed)
- Admin pages are lazy-imported via `React.lazy()` — they must not appear in the initial bundle
- All admin API endpoints live at `/api/v1/admin/` and are protected by Caddy Basic Auth
- `ADMIN_USER` and `ADMIN_PASS` are env vars — never hardcoded
- TypeScript strict mode — no `any` except where explicitly typed as `unknown` then narrowed
- Tests run with `pytest` from `backend/` and `npm test` from `web/`

## Dependency Note

**Tasks 1-3 (backend fixes + admin API) can be done independently of ML Pipeline Plan.**
**Tasks 4-6 (admin UI) require Tasks 1-3 to be complete.**
**The ML pipeline plan (separate doc) must be complete before admin metrics show real data.**

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/services/prediction_service.py` | Modify | Pass `session` to `predict_race` (fixes broken API bridge) |
| `backend/app/api/v1/admin.py` | Create | Three admin endpoints: ml/status, data/status, data/retry |
| `backend/app/main.py` | Modify | Register admin router |
| `deploy/Caddyfile` | Modify | Add basicauth block for `/admin/*` and `/api/v1/admin/*` |
| `web/src/api/admin.ts` | Create | Admin API client functions |
| `web/src/pages/admin/MlMonitoringPage.tsx` | Create | ML metrics dashboard |
| `web/src/pages/admin/DataManagementPage.tsx` | Create | Crawl status + failure retry |
| `web/src/App.tsx` | Modify | Add lazy `/admin/*` routes |
| `backend/tests/api/test_admin.py` | Create | Admin endpoint tests |

---

## Task 1: Fix prediction service bridge

**Files:**
- Modify: `backend/app/services/prediction_service.py`
- Modify: `backend/app/api/v1/predictions.py`

**Interfaces:**
- Consumes: `predict_race(race_id: int, session: AsyncSession)` from `app.ml.predict.service` (new signature from ML Plan Task 9)
- Produces: `get_race_predictions(db, race_id) -> list[HorsePrediction]` passing db session

**Context:** The current `prediction_service.py` calls `predict_race(race_id, race.entries)` which was the old stub signature. The new `predict_race` in ML Plan Task 9 takes `(race_id, session)`.

- [ ] **Step 1: Write failing test**

Create `backend/tests/api/test_predictions_endpoint.py`:

```python
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from app.main import app
from app.ml.predict.service import HorsePrediction
import datetime

@pytest.mark.asyncio
async def test_predictions_endpoint_returns_list():
    mock_preds = [
        HorsePrediction(
            horse_id=1, horse_name="천하무적", program_number=1,
            win_probability=0.35, place_probability=0.65,
            model_versions={"track": "SEOUL"},
            features_snapshot={"distance_m": 1200},
            computed_at=datetime.datetime.now(datetime.timezone.utc),
        )
    ]
    with patch("app.services.prediction_service.predict_race",
               new=AsyncMock(return_value=mock_preds)):
        async with AsyncClient(app=app, base_url="http://test") as client:
            resp = await client.get("/api/v1/races/1/predictions")
    assert resp.status_code in (200, 404)  # 404 if no race in test DB
    if resp.status_code == 200:
        assert "items" in resp.json()
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend
pytest tests/api/test_predictions_endpoint.py -v
```

Expected: fails due to signature mismatch or import error.

- [ ] **Step 3: Fix `prediction_service.py`**

Replace `backend/app/services/prediction_service.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.ml.predict.service import predict_race, HorsePrediction
from typing import List


async def get_race_predictions(db: AsyncSession, race_id: int) -> List[HorsePrediction]:
    """
    Get predictions for a race. Calls the real ML predict service.
    Returns empty list if no race found or model not available.
    """
    return await predict_race(race_id=race_id, session=db)
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/api/test_predictions_endpoint.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prediction_service.py backend/tests/api/test_predictions_endpoint.py
git commit -m "fix: pass db session to predict_race (was passing entries list)"
```

---

## Task 2: Create admin API endpoints

**Files:**
- Create: `backend/app/api/v1/admin.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/api/test_admin.py`

**Interfaces:**
- Produces:
  - `GET /api/v1/admin/ml/status` → `AdminMlStatus`
  - `GET /api/v1/admin/data/status` → `AdminDataStatus`
  - `POST /api/v1/admin/data/retry` → `{"ok": true, "track": str, "date": str}`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/api/test_admin.py`:

```python
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_admin_ml_status_returns_json():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/ml/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "tracks" in body
    assert "last_updated" in body


@pytest.mark.asyncio
async def test_admin_data_status_returns_json():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/data/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "crawl_states" in body
    assert "failures" in body
    assert "db_summary" in body


@pytest.mark.asyncio
async def test_admin_data_retry_invalid_date():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/admin/data/retry",
            json={"track": "SEOUL", "date": "not-a-date"}
        )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend
pytest tests/api/test_admin.py -v
```

Expected: `404 Not Found` or `ImportError` since the endpoints don't exist yet.

- [ ] **Step 3: Create `admin.py`**

Create `backend/app/api/v1/admin.py`:

```python
import datetime
import json
import os
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_db
from app.db.models.crawl import Race, Horse, Jockey, CrawlState, CrawlFailure

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


class TrackModelInfo(BaseModel):
    track: str
    model_version: Optional[str]
    log_loss: Optional[float]
    roi: Optional[float]
    promoted_at: Optional[str]


class AdminMlStatus(BaseModel):
    tracks: list[TrackModelInfo]
    last_updated: str


class CrawlStateInfo(BaseModel):
    track: str
    last_crawled_date: Optional[datetime.date]
    last_status: Optional[str]
    next_scheduled: str


class CrawlFailureInfo(BaseModel):
    id: int
    track: str
    failed_date: datetime.date
    error_message: Optional[str]
    retry_count: int


class DbSummary(BaseModel):
    total_races: int
    total_horses: int
    total_jockeys: int
    latest_race_date: Optional[datetime.date]


class AdminDataStatus(BaseModel):
    crawl_states: list[CrawlStateInfo]
    failures: list[CrawlFailureInfo]
    db_summary: DbSummary


class RetryRequest(BaseModel):
    track: str
    date: datetime.date


def _load_production_json() -> dict:
    model_dir = Path(os.environ.get("MODEL_DIR", "models"))
    prod_json = model_dir / "production.json"
    if not prod_json.exists():
        return {}
    with open(prod_json) as f:
        return json.load(f)


@router.get("/ml/status", response_model=AdminMlStatus)
async def get_ml_status():
    """Returns per-track production model info from production.json."""
    data = _load_production_json()
    tracks = []
    for track_name in ["SEOUL", "BUSAN", "JEJU"]:
        info = data.get(track_name)
        tracks.append(TrackModelInfo(
            track=track_name,
            model_version=info.get("version") if info else None,
            log_loss=info.get("log_loss") if info else None,
            roi=info.get("roi") if info else None,
            promoted_at=info.get("promoted_at") if info else None,
        ))
    return AdminMlStatus(
        tracks=tracks,
        last_updated=datetime.datetime.utcnow().isoformat(),
    )


@router.get("/data/status", response_model=AdminDataStatus)
async def get_data_status(db: AsyncSession = Depends(get_db)):
    """Returns crawl state, recent failures, and DB record counts."""
    # Crawl states
    states_result = await db.execute(select(CrawlState))
    states = states_result.scalars().all()
    crawl_states = [
        CrawlStateInfo(
            track=s.track,
            last_crawled_date=s.last_crawled_date,
            last_status=s.last_status,
            next_scheduled="02:00 KST daily",
        )
        for s in states
    ]
    # Also add tracks with no state yet
    tracked = {s.track for s in states}
    for track in ["SEOUL", "BUSAN", "JEJU"]:
        if track not in tracked:
            crawl_states.append(CrawlStateInfo(
                track=track, last_crawled_date=None,
                last_status="never_run", next_scheduled="02:00 KST daily",
            ))

    # Failures (last 50)
    failures_result = await db.execute(
        select(CrawlFailure).order_by(CrawlFailure.created_at.desc()).limit(50)
    )
    failures = [
        CrawlFailureInfo(
            id=f.id, track=f.track, failed_date=f.failed_date,
            error_message=f.error_message, retry_count=f.retry_count,
        )
        for f in failures_result.scalars().all()
    ]

    # DB summary
    total_races = (await db.execute(select(func.count(Race.id)))).scalar() or 0
    total_horses = (await db.execute(select(func.count(Horse.id)))).scalar() or 0
    total_jockeys = (await db.execute(select(func.count(Jockey.id)))).scalar() or 0
    latest_date_row = await db.execute(select(func.max(Race.race_date)))
    latest_race_date = latest_date_row.scalar()

    return AdminDataStatus(
        crawl_states=crawl_states,
        failures=failures,
        db_summary=DbSummary(
            total_races=total_races,
            total_horses=total_horses,
            total_jockeys=total_jockeys,
            latest_race_date=latest_race_date,
        ),
    )


@router.post("/data/retry")
async def retry_crawl(req: RetryRequest):
    """Trigger a re-crawl for a specific track + date."""
    from app.ml.crawl.pipeline import run_crawl
    import asyncio
    result = await run_crawl(start_date=req.date, end_date=req.date)
    return {"ok": True, "track": req.track, "date": str(req.date), "result": result}
```

- [ ] **Step 4: Register admin router in `main.py`**

Open `backend/app/main.py`, find where other v1 routers are registered (e.g. `app.include_router(races.router, prefix="/api/v1")`), and add:

```python
from app.api.v1 import admin
app.include_router(admin.router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests**

```bash
cd backend
pytest tests/api/test_admin.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/admin.py backend/app/main.py backend/tests/api/test_admin.py
git commit -m "feat: add admin API endpoints (ml/status, data/status, data/retry)"
```

---

## Task 3: Configure Caddy Basic Auth

**Files:**
- Modify: `deploy/Caddyfile`

**Context:** The current Caddyfile proxies all traffic to the FastAPI backend. We need to add a `basicauth` directive that protects `/admin/*` and `/api/v1/admin/*`. The password is stored as a Caddy-format bcrypt hash.

- [ ] **Step 1: Read the current Caddyfile**

```bash
cat deploy/Caddyfile
```

Note the current structure (domain name, reverse proxy target, static file serving).

- [ ] **Step 2: Generate a bcrypt hash for the admin password**

Caddy requires passwords as bcrypt hashes. Generate one:

```bash
docker run --rm caddy:2 caddy hash-password --plaintext "changeme"
```

This outputs something like `$2a$14$...`. Copy it.

- [ ] **Step 3: Add basicauth to Caddyfile**

In `deploy/Caddyfile`, before the `reverse_proxy` directive, add a basicauth block for the admin paths. The exact location depends on the current structure, but the pattern is:

```caddyfile
@admin {
    path /admin/*
    path /api/v1/admin/*
}
basicauth @admin {
    {$ADMIN_USER} {$ADMIN_PASS_HASH}
}
```

`ADMIN_USER` and `ADMIN_PASS_HASH` are env vars — the hash is the bcrypt output from Step 2.

Add to `deploy/docker-compose.yml` (caddy service environment, if caddy runs in compose) or to the `.env` file:

```
ADMIN_USER=admin
ADMIN_PASS_HASH=$2a$14$<hash-from-step-2>
```

- [ ] **Step 4: Test locally**

```bash
cd deploy
docker compose up caddy
curl -u admin:changeme http://localhost/api/v1/admin/ml/status
```

Expected: `200 OK` with JSON. Without credentials: `401 Unauthorized`.

- [ ] **Step 5: Commit**

```bash
git add deploy/Caddyfile deploy/docker-compose.yml
git commit -m "feat: add Caddy Basic Auth for /admin/* routes"
```

---

## Task 4: Admin API client

**Files:**
- Create: `web/src/api/admin.ts`

**Interfaces:**
- Produces:
  - `fetchMlStatus() -> Promise<AdminMlStatus>`
  - `fetchDataStatus() -> Promise<AdminDataStatus>`
  - `retryDate(track: string, date: string) -> Promise<RetryResult>`

- [ ] **Step 1: Create `admin.ts`**

Note: no test step here since this is a thin API wrapper. Integration is tested via the admin page components.

Create `web/src/api/admin.ts`:

```typescript
import { apiClient } from "./client";

export interface TrackModelInfo {
  track: string;
  model_version: string | null;
  log_loss: number | null;
  roi: number | null;
  promoted_at: string | null;
}

export interface AdminMlStatus {
  tracks: TrackModelInfo[];
  last_updated: string;
}

export interface CrawlStateInfo {
  track: string;
  last_crawled_date: string | null;
  last_status: string | null;
  next_scheduled: string;
}

export interface CrawlFailureInfo {
  id: number;
  track: string;
  failed_date: string;
  error_message: string | null;
  retry_count: number;
}

export interface DbSummary {
  total_races: number;
  total_horses: number;
  total_jockeys: number;
  latest_race_date: string | null;
}

export interface AdminDataStatus {
  crawl_states: CrawlStateInfo[];
  failures: CrawlFailureInfo[];
  db_summary: DbSummary;
}

export interface RetryResult {
  ok: boolean;
  track: string;
  date: string;
  result: { races_upserted: number; failures: string[] };
}

export async function fetchMlStatus(): Promise<AdminMlStatus> {
  const res = await apiClient.get("/admin/ml/status");
  return res.data;
}

export async function fetchDataStatus(): Promise<AdminDataStatus> {
  const res = await apiClient.get("/admin/data/status");
  return res.data;
}

export async function retryDate(track: string, date: string): Promise<RetryResult> {
  const res = await apiClient.post("/admin/data/retry", { track, date });
  return res.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/api/admin.ts
git commit -m "feat: add admin API client"
```

---

## Task 5: Admin ML Monitoring page

**Files:**
- Create: `web/src/pages/admin/MlMonitoringPage.tsx`

- [ ] **Step 1: Create the page**

Create `web/src/pages/admin/MlMonitoringPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { fetchMlStatus, TrackModelInfo } from "../../api/admin";

function TrackCard({ info }: { info: TrackModelInfo }) {
  const hasModel = info.model_version !== null;
  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
      <div className="flex justify-between items-center mb-3">
        <span className="font-bold text-slate-100 text-lg">{info.track}</span>
        <span
          className={`text-xs px-2 py-1 rounded-full font-medium ${
            hasModel
              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
              : "bg-slate-700 text-slate-400 border border-slate-600"
          }`}
        >
          {hasModel ? info.model_version : "No model"}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="bg-slate-900/50 rounded-xl p-3">
          <div className="text-slate-500 text-xs mb-1">Val Log-Loss</div>
          <div className="font-mono text-slate-200 font-bold">
            {info.log_loss !== null ? info.log_loss.toFixed(4) : "—"}
          </div>
        </div>
        <div className="bg-slate-900/50 rounded-xl p-3">
          <div className="text-slate-500 text-xs mb-1">Val ROI</div>
          <div
            className={`font-mono font-bold ${
              info.roi !== null && info.roi >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {info.roi !== null ? `${(info.roi * 100).toFixed(1)}%` : "—"}
          </div>
        </div>
      </div>
      {info.promoted_at && (
        <div className="text-xs text-slate-500 mt-3">
          Promoted: {new Date(info.promoted_at).toLocaleString("ko-KR")}
        </div>
      )}
    </div>
  );
}

export default function MlMonitoringPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "ml", "status"],
    queryFn: fetchMlStatus,
    refetchInterval: 60_000,
  });

  return (
    <div className="max-w-2xl mx-auto min-h-screen bg-slate-950 text-slate-200 p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-slate-100">ML 모니터링</h1>
        <button
          onClick={() => refetch()}
          className="text-xs bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 hover:bg-white/20 transition-colors"
        >
          새로고침
        </button>
      </div>

      {isLoading && (
        <div className="text-slate-500 text-center mt-10">Loading...</div>
      )}
      {error && (
        <div className="text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl p-4">
          Failed to load ML status. Check that you are logged in as admin.
        </div>
      )}

      {data && (
        <>
          <div className="grid gap-4 mb-6">
            {data.tracks.map((t) => (
              <TrackCard key={t.track} info={t} />
            ))}
          </div>
          <div className="text-xs text-slate-600 text-right">
            Last updated: {new Date(data.last_updated).toLocaleString("ko-KR")}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/pages/admin/MlMonitoringPage.tsx
git commit -m "feat: add admin ML monitoring page"
```

---

## Task 6: Admin Data Management page + wire routes

**Files:**
- Create: `web/src/pages/admin/DataManagementPage.tsx`
- Modify: `web/src/App.tsx`

- [ ] **Step 1: Create Data Management page**

Create `web/src/pages/admin/DataManagementPage.tsx`:

```tsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchDataStatus,
  retryDate,
  CrawlFailureInfo,
  CrawlStateInfo,
} from "../../api/admin";

function CrawlStateRow({ state }: { state: CrawlStateInfo }) {
  const statusColor =
    state.last_status === "ok"
      ? "text-emerald-400"
      : state.last_status === "partial"
      ? "text-yellow-400"
      : "text-slate-500";

  return (
    <div className="flex justify-between items-center py-3 border-b border-white/5 last:border-0">
      <span className="font-medium text-slate-200">{state.track}</span>
      <div className="text-right">
        <div className={`text-sm font-mono ${statusColor}`}>
          {state.last_status || "never run"}
        </div>
        <div className="text-xs text-slate-500">
          {state.last_crawled_date
            ? `최근: ${state.last_crawled_date}`
            : "크롤 이력 없음"}
        </div>
      </div>
    </div>
  );
}

function FailureRow({
  failure,
  onRetry,
  isRetrying,
}: {
  failure: CrawlFailureInfo;
  onRetry: (track: string, date: string) => void;
  isRetrying: boolean;
}) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-3 flex justify-between items-start gap-3">
      <div className="flex-1 min-w-0">
        <div className="font-medium text-slate-200 text-sm">
          {failure.track} — {failure.failed_date}
        </div>
        <div className="text-xs text-slate-500 truncate mt-0.5">
          {failure.error_message || "알 수 없는 오류"}
        </div>
        <div className="text-xs text-slate-600 mt-1">
          재시도 {failure.retry_count}회
        </div>
      </div>
      <button
        onClick={() => onRetry(failure.track, failure.failed_date)}
        disabled={isRetrying}
        className="text-xs bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 rounded-lg px-3 py-1.5 hover:bg-indigo-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
      >
        {isRetrying ? "재시도 중..." : "재시도"}
      </button>
    </div>
  );
}

export default function DataManagementPage() {
  const queryClient = useQueryClient();
  const [retryingId, setRetryingId] = useState<number | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "data", "status"],
    queryFn: fetchDataStatus,
    refetchInterval: 30_000,
  });

  const retryMutation = useMutation({
    mutationFn: ({ track, date }: { track: string; date: string }) =>
      retryDate(track, date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "data", "status"] });
      setRetryingId(null);
    },
    onError: () => setRetryingId(null),
  });

  const handleRetry = (failureId: number, track: string, date: string) => {
    setRetryingId(failureId);
    retryMutation.mutate({ track, date });
  };

  if (isLoading)
    return (
      <div className="text-slate-500 text-center mt-10">Loading...</div>
    );
  if (error)
    return (
      <div className="max-w-2xl mx-auto p-4">
        <div className="text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl p-4">
          Failed to load data status.
        </div>
      </div>
    );

  return (
    <div className="max-w-2xl mx-auto min-h-screen bg-slate-950 text-slate-200 p-4">
      <h1 className="text-2xl font-bold text-slate-100 mb-6">데이터 관리</h1>

      {/* DB Summary */}
      <section className="mb-6">
        <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">
          DB 현황
        </h2>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "레이스", value: data?.db_summary.total_races },
            { label: "말", value: data?.db_summary.total_horses },
            { label: "기수", value: data?.db_summary.total_jockeys },
            {
              label: "최신 데이터",
              value: data?.db_summary.latest_race_date ?? "없음",
            },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="bg-white/5 border border-white/10 rounded-xl p-3"
            >
              <div className="text-slate-500 text-xs mb-1">{label}</div>
              <div className="font-mono text-slate-200 font-bold">
                {value?.toLocaleString() ?? "—"}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Crawl Status */}
      <section className="mb-6">
        <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">
          크롤 상태
        </h2>
        <div className="bg-white/5 border border-white/10 rounded-xl px-4">
          {data?.crawl_states.map((s) => (
            <CrawlStateRow key={s.track} state={s} />
          ))}
        </div>
      </section>

      {/* Failures */}
      <section>
        <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">
          실패 목록{" "}
          {data?.failures.length ? (
            <span className="text-red-400">({data.failures.length})</span>
          ) : (
            <span className="text-emerald-400">(없음)</span>
          )}
        </h2>
        {data?.failures.length === 0 ? (
          <div className="text-slate-500 text-sm text-center py-6">
            실패한 크롤이 없습니다.
          </div>
        ) : (
          <div className="space-y-2">
            {data?.failures.map((f) => (
              <FailureRow
                key={f.id}
                failure={f}
                onRetry={(track, date) => handleRetry(f.id, track, date)}
                isRetrying={retryingId === f.id}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Wire admin routes into `App.tsx`**

Open `web/src/App.tsx`. Find the existing route definitions. Add lazy-loaded admin routes:

```tsx
// At the top of App.tsx, with other imports:
import { lazy, Suspense } from "react";

const MlMonitoringPage = lazy(() => import("./pages/admin/MlMonitoringPage"));
const DataManagementPage = lazy(() => import("./pages/admin/DataManagementPage"));
```

Add routes inside the `<Routes>` block (the exact JSX depends on existing App.tsx structure — read it first):

```tsx
<Route
  path="/admin/ml"
  element={
    <Suspense fallback={<div className="p-4 text-slate-400">Loading...</div>}>
      <MlMonitoringPage />
    </Suspense>
  }
/>
<Route
  path="/admin/data"
  element={
    <Suspense fallback={<div className="p-4 text-slate-400">Loading...</div>}>
      <DataManagementPage />
    </Suspense>
  }
/>
```

Read `web/src/App.tsx` before editing to find the exact `<Routes>` block structure.

- [ ] **Step 3: Start dev server and verify admin pages load**

```bash
cd web
npm run dev
```

Navigate to `http://localhost:5173/admin/ml` — should render the ML monitoring page (data may show empty if no model trained yet).

Navigate to `http://localhost:5173/admin/data` — should render the data management page.

Check browser console for TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/admin/ web/src/App.tsx
git commit -m "feat: add admin data management page and wire admin routes"
```

---

## Self-Review Checklist

After completing all tasks, verify:

- [ ] `GET /api/v1/races/{id}/predictions` returns real probabilities (not `{"mock": true}` in features_snapshot)
- [ ] `GET /api/v1/admin/ml/status` returns 200 with tracks array
- [ ] `GET /api/v1/admin/data/status` returns 200 with crawl_states, failures, db_summary
- [ ] `curl -u admin:changeme http://localhost/api/v1/admin/ml/status` returns 200
- [ ] `curl http://localhost/api/v1/admin/ml/status` (no credentials) returns 401
- [ ] `/admin/ml` renders in browser (data may be empty until ML pipeline is trained)
- [ ] `/admin/data` renders in browser with DB summary
- [ ] No TypeScript errors: `cd web && npx tsc --noEmit`
- [ ] All backend tests pass: `cd backend && pytest`
