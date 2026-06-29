"""
2025-2026 races.track_condition / weather / humidity 백필

morning_odds와 동일한 근본원인: 최근 레이스가 출전표/결과만 크롤되어 race 메타가 비어있음.
ScoretableDetailList.do 상세페이지 meta(weather, track_condition, humidity)로 채운다.

Usage:
    uv run python scripts/backfill_race_meta.py --year 2025
    uv run python scripts/backfill_race_meta.py --year 2026
"""
from __future__ import annotations
import argparse, asyncio, datetime, logging, sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.db.session import async_session_factory
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from sqlalchemy import select, or_
from app.db.models.crawl import Race

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TRACK_TO_MEET = {"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}
URL = "https://race.kra.co.kr/raceScore/ScoretableDetailList.do"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}


def fetch_meta(meet, rc_date, rc_no):
    try:
        res = requests.post(URL, headers=HEADERS,
                            data={"meet": meet, "realRcDate": rc_date, "realRcNo": rc_no}, timeout=15)
        res.encoding = "euc-kr"
        parsed = KRALiveParser.parse_race_detail(res.text)
        if parsed and parsed.get("meta"):
            return parsed["meta"]
    except Exception as exc:
        logger.warning("HTTP %s %s %s: %s", rc_date, meet, rc_no, exc)
    return None


async def backfill(year, limit):
    async with async_session_factory() as s:
        q = select(Race).where(
            or_(Race.track_condition.is_(None), Race.weather.is_(None))
        )
        if year:
            q = q.where(Race.race_date >= datetime.date(year, 1, 1),
                        Race.race_date <= datetime.date(year, 12, 31))
        q = q.order_by(Race.race_date.desc())
        if limit:
            q = q.limit(limit)
        races = list((await s.execute(q)).scalars().all())
    logger.info("메타 비어있는 경주: %d개 (year=%s)", len(races), year)

    updated = skipped = 0
    for i, race in enumerate(races):
        meta = fetch_meta(TRACK_TO_MEET.get(race.track, "1"),
                          race.race_date.strftime("%Y%m%d"), str(race.race_number))
        if not meta:
            skipped += 1
        else:
            async with async_session_factory() as s2:
                r = (await s2.execute(select(Race).where(Race.id == race.id))).scalar_one()
                if r.track_condition is None and meta.get("track_condition"):
                    r.track_condition = meta["track_condition"]
                if r.weather is None and meta.get("weather"):
                    r.weather = meta["weather"]
                if r.humidity is None and meta.get("humidity") is not None:
                    r.humidity = meta["humidity"]
                await s2.commit()
            updated += 1
            if (i + 1) % 50 == 0 or updated <= 3:
                logger.info("[%d/%d] %s %s R%s → %s/%s",
                            i+1, len(races), race.race_date, race.track,
                            race.race_number, meta.get("weather"), meta.get("track_condition"))
        await asyncio.sleep(0.3)
    logger.info("완료: %d경주 메타 채움, %d경주 데이터없음", updated, skipped)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int)
    p.add_argument("--limit", type=int)
    a = p.parse_args()
    asyncio.run(backfill(a.year, a.limit))
