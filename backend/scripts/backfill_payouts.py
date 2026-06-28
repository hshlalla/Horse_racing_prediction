"""
기존 races 테이블에 payouts 백필

payouts가 없는 경기를 KRA ScoretableDetailList에서 다시 가져와서 채웁니다.

Usage:
    uv run python scripts/backfill_payouts.py                    # 전체
    uv run python scripts/backfill_payouts.py --year 2025        # 특정 연도
    uv run python scripts/backfill_payouts.py --year 2025 --limit 50  # 테스트
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import async_session_factory
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from sqlalchemy import select, update
from app.db.models.crawl import Race

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TRACK_TO_MEET = {"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}
KRA_DETAIL_URL = "https://race.kra.co.kr/raceScore/ScoretableDetailList.do"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}


def fetch_payouts(meet: str, rc_date: str, rc_no: str) -> dict | None:
    try:
        res = requests.post(
            KRA_DETAIL_URL,
            headers=HEADERS,
            data={"meet": meet, "realRcDate": rc_date, "realRcNo": rc_no},
            timeout=10,
        )
        res.encoding = "euc-kr"
        parsed = KRALiveParser.parse_race_detail(res.text)
        if parsed and parsed.get("payouts"):
            return parsed["payouts"]
    except Exception as exc:
        logger.warning("HTTP error %s %s %s: %s", rc_date, meet, rc_no, exc)
    return None


async def backfill(year: int | None = None, limit: int | None = None) -> None:
    async with async_session_factory() as s:
        q = select(Race).where(Race.payouts.is_(None))
        if year:
            q = q.where(
                Race.race_date >= datetime.date(year, 1, 1),
                Race.race_date <= datetime.date(year, 12, 31),
            )
        q = q.order_by(Race.race_date.desc(), Race.id)
        if limit:
            q = q.limit(limit)
        result = await s.execute(q)
        races = list(result.scalars().all())

    logger.info("payouts 없는 경주: %d개 (year=%s, limit=%s)", len(races), year, limit)

    updated = 0
    skipped = 0
    for i, race in enumerate(races):
        meet = TRACK_TO_MEET.get(race.track, "1")
        rc_date = race.race_date.strftime("%Y%m%d")
        rc_no = str(race.race_number)

        payouts = fetch_payouts(meet, rc_date, rc_no)
        if payouts:
            async with async_session_factory() as s:
                await s.execute(
                    update(Race)
                    .where(Race.id == race.id)
                    .values(payouts=payouts)
                )
                await s.commit()
            updated += 1
            if (i + 1) % 20 == 0 or updated <= 5:
                logger.info("[%d/%d] ✅ %s %s %s경주 — win=%s",
                            i+1, len(races), race.race_date, race.track, rc_no,
                            payouts.get("win", [])[:1])
        else:
            skipped += 1
            if (i + 1) % 100 == 0:
                logger.info("[%d/%d] %s %s %s경주 — payouts 없음",
                            i+1, len(races), race.race_date, race.track, rc_no)

        await asyncio.sleep(0.3)

    logger.info("완료: %d/%d 경주에 payouts 추가, %d개 데이터 없음",
                updated, len(races), skipped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    asyncio.run(backfill(year=args.year, limit=args.limit))
