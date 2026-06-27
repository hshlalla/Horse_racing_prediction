import asyncio
import datetime
import logging
import sys

import requests

from app.db.session import async_session_factory
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from app.ml.crawl.upsert import (
    upsert_horse,
    upsert_inrace_timing,
    upsert_jockey,
    upsert_race,
    upsert_race_entry,
    upsert_race_result,
    upsert_trainer,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

TRACK_MAP = {"1": "SEOUL", "2": "JEJU", "3": "BUSAN"}
KRA_DETAIL_URL = "https://race.kra.co.kr/raceScore/ScoretableDetailList.do"
HEADERS = {"User-Agent": "Mozilla/5.0"}


async def _ingest_race(session, rc_date: str, meet: str, rc_no: int) -> bool:
    """Fetch + parse one race and upsert to DB. Returns True if race data was found."""
    try:
        res = requests.post(
            KRA_DETAIL_URL,
            headers=HEADERS,
            data={"meet": meet, "realRcDate": rc_date, "realRcNo": str(rc_no)},
            timeout=10,
        )
        res.encoding = "euc-kr"
    except Exception as exc:
        logger.error("HTTP error %s meet=%s rc_no=%s: %s", rc_date, meet, rc_no, exc)
        return False

    parsed = KRALiveParser.parse_race_detail(res.text)
    if not parsed or not parsed.get("horses"):
        return False

    meta = parsed["meta"]
    details = parsed["horses"]
    track = TRACK_MAP.get(meet, "SEOUL")
    d_obj = datetime.datetime.strptime(rc_date, "%Y%m%d").date()

    pt_str = meta.get("post_time_str")
    post_time_dt = None
    if pt_str:
        try:
            post_time_dt = datetime.datetime.combine(
                d_obj, datetime.datetime.strptime(pt_str, "%H:%M").time()
            )
        except Exception:
            pass

    race_id = await upsert_race(
        session,
        track=track,
        race_date=d_obj,
        race_number=rc_no,
        race_name=meta.get("race_name", f"Race {rc_no}"),
        distance_m=meta.get("distance_m", 1200),
        surface=meta.get("surface", "Dirt"),
        track_condition=meta.get("track_condition"),
        weather=meta.get("weather"),
        grade=meta.get("grade"),
        field_size=len(details),
        post_time=post_time_dt,
    )

    for d in details:
        horse_id = await upsert_horse(session, name=d["horse_name"], sex="M")
        jockey_id = await upsert_jockey(session, name=d["jockey"])
        trainer_id = await upsert_trainer(session, name=d["trainer"])

        await upsert_race_entry(
            session,
            race_id=race_id,
            horse_id=horse_id,
            program_number=d["horse_no"],
            jockey_id=jockey_id,
            trainer_id=trainer_id,
            carry_weight_kg=d.get("carry_weight", 53.0),
            body_weight_kg=d.get("weight"),
            morning_odds=d.get("odds_win"),
        )
        await upsert_race_result(
            session,
            race_id=race_id,
            horse_id=horse_id,
            finish_position=d.get("rank"),
            final_odds=d.get("odds_win"),
        )
        await upsert_inrace_timing(
            session,
            race_id=race_id,
            horse_id=horse_id,
            s1f_time=d.get("s1f_time"),
            g3f_time=d.get("g3f_time"),
            corner1_rank=d.get("corner1_rank"),
            corner2_rank=d.get("corner2_rank"),
            corner3_rank=d.get("corner3_rank"),
            corner4_rank=d.get("corner4_rank"),
        )

    await session.commit()
    logger.info("Saved %s meet=%s race=%d entries=%d", rc_date, track, rc_no, len(details))
    return True


async def _ingest_date(session, rc_date: str, meet: str) -> int:
    """Brute-force race numbers 1-15 for a given date+meet. Returns count of races saved."""
    track = TRACK_MAP.get(meet, "SEOUL")
    logger.info("Crawling %s at %s...", rc_date, track)
    saved = 0
    found_any = False

    for rc_no in range(1, 16):
        await asyncio.sleep(0.5)
        ok = await _ingest_race(session, rc_date, meet, rc_no)
        if ok:
            found_any = True
            saved += 1
        elif rc_no >= 5 and not found_any:
            break  # no races on this date for this track

    if not found_any:
        logger.info("No races found for %s at %s", rc_date, track)
    return saved


async def crawl_history(start_year: int, end_year: int) -> None:
    dates = []
    curr = datetime.date(start_year, 1, 1)
    end = datetime.date(end_year, 12, 31)
    while curr <= end:
        if curr.weekday() in [4, 5, 6]:  # Fri, Sat, Sun
            dates.append(curr.strftime("%Y%m%d"))
        curr += datetime.timedelta(days=1)

    logger.info("Generated %d dates to crawl from %d to %d.", len(dates), start_year, end_year)
    total = 0

    async with async_session_factory() as session:
        for rc_date in dates:
            for meet in ["1", "2", "3"]:  # SEOUL, JEJU, BUSAN
                try:
                    n = await _ingest_date(session, rc_date, meet)
                    total += n
                except Exception as exc:
                    logger.error("Error on %s meet %s: %s", rc_date, meet, exc)
                    await session.rollback()

    logger.info("History crawl complete. Total races saved: %d", total)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m app.ml.crawl.crawl_history <start_year> <end_year>")
        sys.exit(1)

    asyncio.run(crawl_history(int(sys.argv[1]), int(sys.argv[2])))
