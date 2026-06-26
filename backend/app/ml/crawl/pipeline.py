import logging
import os
import glob
import datetime
import httpx
import requests
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models.crawl import CrawlState
from app.ml.crawl.kra_client import KRAClient
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from app.ml.crawl.upsert import (
    upsert_horse, upsert_jockey, upsert_trainer,
    upsert_race, upsert_race_entry, upsert_race_result, upsert_inrace_timing,
)

logger = logging.getLogger(__name__)

TRACK_MEET_MAP = {"SEOUL": "1", "BUSAN": "2", "JEJU": "3"}
SEX_MAP = {"수": "M", "암": "F", "거": "G"}


# ---------------------------------------------------------------------------
# New module-level async function (Task ML-3)
# ---------------------------------------------------------------------------

async def _ingest_race_detail(session, track: str, race_date_str: str,
                              rc_no: int) -> bool:
    """Fetch one completed race and upsert all rows. Returns True on success."""
    meet = TRACK_MEET_MAP.get(track, "1")
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://race.kra.co.kr/raceScore/ScoretableDetailList.do",
                headers={"User-Agent": "Mozilla/5.0"},
                data={"meet": meet, "realRcDate": race_date_str, "realRcNo": str(rc_no)},
                timeout=15.0,
            )
        detail = KRALiveParser.parse_race_detail(res.content.decode("euc-kr"))
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
            failures_before = len(failures)
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
                track_had_failures = len(failures) > failures_before
                state.last_status = "partial" if track_had_failures else "ok"
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


# ---------------------------------------------------------------------------
# Legacy class and function — kept for backwards compatibility
# ---------------------------------------------------------------------------

try:
    from app.ml.crawl.kra_openapi import KRAOpenAPIClient
    from app.ml.crawl.parsers.kra_html_parser import parse_race_list_html
    from app.ml.crawl.synthetic_data import main as populate_db
except ImportError:
    KRAOpenAPIClient = None  # type: ignore
    parse_race_list_html = None  # type: ignore
    populate_db = None  # type: ignore


class CrawlingPipeline:
    """
    Hybrid Crawling Pipeline:
    1. Attempts to use KRA OpenAPI (API187) if key is active.
    2. Uses local HTML dumps (backend/data/kra_dumps/*.html) if provided to bypass web blocks.
    3. Falls back to synthetic data populator if requested.
    """
    def __init__(self, db_session: Session, api_key: str = None):
        self.db = db_session
        self.client = KRAClient()
        self.openapi_client = KRAOpenAPIClient(api_key) if (KRAOpenAPIClient and api_key) else None
        self.dump_dir = os.path.join(os.getcwd(), "data", "kra_dumps")

    async def run(self, start_date: date, end_date: date, use_synthetic_fallback: bool = True):
        logger.info(f"Starting KRA crawl pipeline from {start_date} to {end_date}")

        # 1. Process local HTML dumps first (to bypass IP blocks securely)
        if os.path.exists(self.dump_dir):
            html_files = glob.glob(os.path.join(self.dump_dir, "*.html"))
            for file_path in html_files:
                logger.info(f"Parsing local HTML dump: {file_path}")
                if parse_race_list_html:
                    with open(file_path, "r", encoding="euc-kr", errors="ignore") as f:
                        html_content = f.read()
                        parsed_races = parse_race_list_html(html_content)
                        if parsed_races:
                            logger.info(f"Found {len(parsed_races)} dates in dump {os.path.basename(file_path)}")

        # 2. Live Web Crawling (Chulma / Score Detail)
        logger.info("Attempting Live Web Crawling from race.kra.co.kr...")
        try:
            list_html = self.client.fetch_page("/raceScore/ScoretableScoreList.do", {"Act": "04", "Sub": "1", "meet": "1"})

            if list_html:
                logger.info("Successfully fetched ScoretableScoreList.do")
                live_races = KRALiveParser.parse_chulma_list(list_html)

                if live_races:
                    logger.info(f"Found {len(live_races)} race dates on live site.")
                    # Fetch detailed results for the first race of the first date to verify
                    first_date = live_races[0]
                    rc_date = first_date['date']
                    rc_no = first_date['races'][0] if first_date['races'] else 1

                    logger.info(f"Fetching detailed race results for {rc_date} Race {rc_no}...")
                    res = requests.post(
                        "https://race.kra.co.kr/raceScore/ScoretableDetailList.do",
                        headers={"User-Agent": "Mozilla/5.0"},
                        data={"meet": "1", "realRcDate": rc_date, "realRcNo": str(rc_no)},
                        timeout=10
                    )
                    res.encoding = 'euc-kr'
                    detail_results = KRALiveParser.parse_race_detail(res.text)
                    if detail_results and detail_results.get("horses"):
                        horses = detail_results["horses"]
                        logger.info(f"Successfully scraped {len(horses)} horses for Race {rc_no}!")
                        for h in horses[:3]:
                            logger.info(f"  -> Rank {h['rank']}: {h['horse_name']} (Odds: {h['odds_win']})")
                    else:
                        logger.warning("Could not extract detailed horse info.")
        except Exception as e:
            logger.error(f"Live crawling failed: {e}")

        # 3. Synthetic Fallback
        if use_synthetic_fallback and populate_db:
            logger.info("Using synthetic data generator to populate database as fallback")
            await populate_db()

        logger.info("Crawl pipeline finished successfully.")


def execute():
    import asyncio

    # User's provided decoding key
    api_key = "7d7Y9lSLZvt//+HmnwT8W7vbC5JsoY4ZvQ4WJGfl33ZUC5KJ+/lUhsP9hSulAgPMcvlLocZ1BIzzVaaX9Hqbtg=="

    async def _execute():
        async with async_session_factory() as db:
            pipeline = CrawlingPipeline(db, api_key=api_key)
            await pipeline.run(date(1990, 1, 1), date.today(), use_synthetic_fallback=True)

    asyncio.run(_execute())
