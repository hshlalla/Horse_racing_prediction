import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.crawl import CrawlFailure, CrawlState, Horse, Jockey, Race
from app.ml.crawl.crawl_entries import crawl_entries

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TrackModelInfo(BaseModel):
    track: str
    model_version: Optional[str] = None
    log_loss: Optional[float] = None
    roi: Optional[float] = None
    promoted_at: Optional[str] = None


class AdminMlStatus(BaseModel):
    tracks: list[TrackModelInfo]
    last_updated: str


class CrawlStateInfo(BaseModel):
    track: str
    last_crawled_date: Optional[datetime.date] = None
    last_status: Optional[str] = None
    next_scheduled: str


class CrawlFailureInfo(BaseModel):
    id: int
    track: str
    failed_date: datetime.date
    error_message: Optional[str] = None
    retry_count: int


class DbSummary(BaseModel):
    total_races: int
    total_horses: int
    total_jockeys: int
    latest_race_date: Optional[datetime.date] = None


class AdminDataStatus(BaseModel):
    crawl_states: list[CrawlStateInfo]
    failures: list[CrawlFailureInfo]
    db_summary: DbSummary


class RetryRequest(BaseModel):
    track: str
    date: datetime.date


class CrawlEntriesRequest(BaseModel):
    date: datetime.date
    tracks: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_production_json() -> dict:
    model_dir = Path(os.environ.get("MODEL_DIR", "models"))
    prod_json = model_dir / "production.json"
    if not prod_json.exists():
        return {}
    with open(prod_json) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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
    # Fill in any tracks with no state row yet
    tracked = {s.track for s in states}
    for track in ["SEOUL", "BUSAN", "JEJU"]:
        if track not in tracked:
            crawl_states.append(CrawlStateInfo(
                track=track,
                last_crawled_date=None,
                last_status="never_run",
                next_scheduled="02:00 KST daily",
            ))

    # Failures — last 50 by created_at desc
    failures_result = await db.execute(
        select(CrawlFailure).order_by(CrawlFailure.created_at.desc()).limit(50)
    )
    failures = [
        CrawlFailureInfo(
            id=f.id,
            track=f.track,
            failed_date=f.failed_date,
            error_message=f.error_message,
            retry_count=f.retry_count,
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
    """Trigger a background re-crawl for a specific track + date."""
    from app.ml.crawl.pipeline import run_crawl  # local import to avoid circular dep

    async def _run():
        try:
            await run_crawl(start_date=req.date, end_date=req.date)
        except Exception as exc:  # noqa: BLE001
            logger.error("retry_crawl_failed track=%s date=%s error=%s", req.track, req.date, exc)

    asyncio.create_task(_run())
    return {"ok": True, "track": req.track, "date": str(req.date)}


@router.post("/crawl/entries")
async def crawl_race_entries(req: CrawlEntriesRequest):
    """Trigger 출마표 (pre-race entry) crawl for a target date. Runs in background."""
    tracks = req.tracks or ["SEOUL", "BUSAN", "JEJU"]
    target = req.date

    async def _run():
        try:
            result = await crawl_entries(target_date=target, tracks=tracks)
            logger.info("entry_crawl_done date=%s result=%s", target, result)
        except Exception as exc:
            logger.error("entry_crawl_failed date=%s error=%s", target, exc)

    asyncio.create_task(_run())
    return {
        "ok": True,
        "date": str(target),
        "tracks": tracks,
        "message": "Entry crawl started in background",
    }
