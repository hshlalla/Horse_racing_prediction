"""
출마표 (Pre-Race Entry) Crawler

Fetches upcoming race entries from the KRA website and upserts Race + RaceEntry
rows so the prediction API can serve predictions before races run.

Usage:
    from app.ml.crawl.crawl_entries import crawl_entries
    result = await crawl_entries(datetime.date(2026, 6, 28), ["SEOUL"])
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from app.ml.crawl.upsert import (
    upsert_horse, upsert_jockey, upsert_trainer,
    upsert_race, upsert_race_entry,
)

logger = logging.getLogger(__name__)

TRACK_MEET_MAP = {"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}
KRA_BASE = "https://race.kra.co.kr"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}


async def _fetch_race_list(client: httpx.AsyncClient, rc_date: str, meet: str) -> List[int]:
    """Return list of race numbers for the given date and meet code."""
    try:
        res = await client.post(
            f"{KRA_BASE}/raceScore/ScoretableScoreList.do",
            headers=HEADERS,
            data={"Act": "04", "Sub": "1", "meet": meet, "rcDate": rc_date},
            timeout=15.0,
        )
        html = res.content.decode("euc-kr", errors="replace")
        schedule = KRALiveParser.parse_chulma_list(html)
        for day in schedule:
            if day.get("date") == rc_date:
                return day.get("races", [])
        return []
    except Exception as exc:
        logger.warning("_fetch_race_list failed %s meet=%s: %s", rc_date, meet, exc)
        return []


async def _fetch_race_entries(
    client: httpx.AsyncClient, rc_date: str, meet: str, rc_no: int
) -> List[Dict]:
    """Fetch and parse entry list for one upcoming race."""
    for path in [
        "/chulmaList/ChulmaDetailInfoPrint.do",
        "/chulmaList/ChulmaDetailInfo.do",
    ]:
        try:
            res = await client.post(
                f"{KRA_BASE}{path}",
                headers=HEADERS,
                data={"meet": meet, "rcDate": rc_date, "rcNo": str(rc_no)},
                timeout=15.0,
            )
            html = res.content.decode("euc-kr", errors="replace")
            entries = KRALiveParser.parse_upcoming_race(html)
            if entries:
                return entries
        except Exception as exc:
            logger.warning("_fetch_race_entries %s %s race %s: %s", path, rc_date, rc_no, exc)
    return []


async def _fetch_race_meta(
    client: httpx.AsyncClient, rc_date: str, meet: str, rc_no: int
) -> Dict:
    """Fetch race metadata (distance, surface, weather) from the detail page."""
    try:
        res = await client.post(
            f"{KRA_BASE}/raceScore/ScoretableDetailList.do",
            headers=HEADERS,
            data={"meet": meet, "realRcDate": rc_date, "realRcNo": str(rc_no)},
            timeout=15.0,
        )
        html = res.content.decode("euc-kr", errors="replace")
        parsed = KRALiveParser.parse_race_detail(html)
        return parsed.get("meta", {})
    except Exception as exc:
        logger.warning("_fetch_race_meta failed %s race %s: %s", rc_date, rc_no, exc)
        return {}


async def crawl_entries(
    target_date: datetime.date,
    tracks: Optional[List[str]] = None,
    session: Optional[AsyncSession] = None,
) -> Dict:
    """
    Fetch and store upcoming race entries for target_date.

    Parameters
    ----------
    target_date : the race day to fetch entries for
    tracks      : e.g. ["SEOUL", "BUSAN"]; defaults to all three tracks
    session     : optional AsyncSession; if None, creates its own

    Returns
    -------
    {"races_upserted": int, "entries_upserted": int, "errors": List[str]}
    """
    if tracks is None:
        tracks = ["SEOUL", "BUSAN", "JEJU"]

    rc_date = target_date.strftime("%Y%m%d")
    races_upserted = 0
    entries_upserted = 0
    errors: List[str] = []

    async def _run(sess: AsyncSession) -> None:
        nonlocal races_upserted, entries_upserted

        async with httpx.AsyncClient() as client:
            for track in tracks:
                meet = TRACK_MEET_MAP.get(track, "1")
                race_numbers = await _fetch_race_list(client, rc_date, meet)
                if not race_numbers:
                    logger.info("No races found for %s on %s", track, rc_date)
                    continue

                logger.info("Found %d races for %s on %s", len(race_numbers), track, rc_date)

                for rc_no in race_numbers:
                    await asyncio.sleep(0.5)

                    meta = await _fetch_race_meta(client, rc_date, meet, rc_no)
                    entries = await _fetch_race_entries(client, rc_date, meet, rc_no)

                    if not entries:
                        errors.append(f"{track} race {rc_no}: no entries returned")
                        continue

                    race_id = await upsert_race(
                        sess,
                        track=track,
                        race_date=target_date,
                        race_number=rc_no,
                        race_name=meta.get("race_name", f"{rc_no}경주"),
                        distance_m=meta.get("distance_m", 1200),
                        surface=meta.get("surface", "Dirt"),
                        track_condition=meta.get("track_condition"),
                        weather=meta.get("weather"),
                        humidity=meta.get("humidity"),
                        grade=meta.get("grade"),
                        field_size=len(entries),
                    )
                    races_upserted += 1

                    for e in entries:
                        horse_id = await upsert_horse(
                            sess,
                            name=e["horse_name"],
                            sex=e.get("sex", "M"),
                            age=e.get("age"),
                        )
                        jockey_id = (
                            await upsert_jockey(sess, name=e["jockey"])
                            if e.get("jockey") else None
                        )
                        trainer_id = (
                            await upsert_trainer(sess, name=e["trainer"])
                            if e.get("trainer") else None
                        )

                        await upsert_race_entry(
                            sess,
                            race_id=race_id,
                            horse_id=horse_id,
                            program_number=e["horse_no"],
                            jockey_id=jockey_id,
                            trainer_id=trainer_id,
                            carry_weight_kg=e.get("carry_weight"),
                            body_weight_kg=e.get("weight"),
                            morning_odds=e.get("morning_odds"),
                        )
                        entries_upserted += 1

                    await sess.commit()
                    logger.info(
                        "Upserted %s/%s with %d entries", track, rc_no, len(entries)
                    )

    if session is not None:
        await _run(session)
    else:
        async with async_session_factory() as sess:
            await _run(sess)

    return {
        "races_upserted": races_upserted,
        "entries_upserted": entries_upserted,
        "errors": errors,
    }
