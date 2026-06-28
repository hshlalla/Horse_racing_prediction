"""
기존 races 테이블에 video_url 백필

video_url이 없는 경기를 KRA ScoretableDetailList에서 다시 가져와서 채웁니다.
YouTube URL이 있는 경기만 업데이트합니다.

Usage:
    uv run python scripts/backfill_video_urls.py                    # 전체
    uv run python scripts/backfill_video_urls.py --year 2025        # 특정 연도
    uv run python scripts/backfill_video_urls.py --year 2025 --limit 100  # 테스트
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import async_session_factory
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from sqlalchemy import select, update, and_
from app.db.models.crawl import Race
import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TRACK_TO_MEET = {"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}
KRA_DETAIL_URL = "https://race.kra.co.kr/raceScore/ScoretableDetailList.do"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}


async def backfill(year: int | None = None, limit: int | None = None) -> None:
    async with async_session_factory() as s:
        q = select(Race).where(Race.video_url.is_(None))
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

    logger.info("video_url 없는 경주: %d개 (year=%s, limit=%s)", len(races), year, limit)

    updated = 0
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i, race in enumerate(races):
            meet = TRACK_TO_MEET.get(race.track, "1")
            rc_date = race.race_date.strftime("%Y%m%d")
            rc_no = str(race.race_number)

            try:
                res = await client.post(
                    KRA_DETAIL_URL,
                    headers=HEADERS,
                    data={"meet": meet, "realRcDate": rc_date, "realRcNo": rc_no},
                )
                html = res.content.decode("euc-kr", errors="replace")
                yt = re.findall(r"youtube\.com/watch\?v=([^\'\"\s&<>]+)", html)
                if yt:
                    video_url = f"https://www.youtube.com/watch?v={yt[0]}"
                    async with async_session_factory() as s:
                        await s.execute(
                            update(Race)
                            .where(Race.id == race.id)
                            .values(video_url=video_url)
                        )
                        await s.commit()
                    updated += 1
                    logger.info("[%d/%d] ✅ %s %s %s경주 → %s",
                                i+1, len(races), race.race_date, race.track, rc_no, video_url)
                else:
                    if (i+1) % 50 == 0:
                        logger.info("[%d/%d] %s %s %s경주 — 영상없음",
                                    i+1, len(races), race.race_date, race.track, rc_no)

            except Exception as exc:
                logger.warning("[%d/%d] 실패 %s %s %s: %s",
                               i+1, len(races), rc_date, race.track, rc_no, exc)

            await asyncio.sleep(0.3)

    logger.info("완료: %d/%d 경주에 영상 URL 추가", updated, len(races))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    asyncio.run(backfill(year=args.year, limit=args.limit))
