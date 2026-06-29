"""
2025-2026 race_entries.morning_odds 백필

증상: 2025-2026 출주마의 ~72%가 morning_odds NULL.
원인: 출전표 크롤로만 들어와 최종 단승배당이 채워지지 않음 (odds_snapshots도 0건).
해법: payout 백필과 동일한 ScoretableDetailList.do 상세페이지에서 말별 단승배당(odds_win)을
      가져와 program_number로 매칭해 morning_odds NULL인 칸만 채운다.

확인된 일관성: 기존 채워진 28%는 우승마 기준 실제 payout 배당과 비율 1.0 일치 →
같은 소스(최종 단승배당)로 NULL을 채우면 데이터가 일관됨.

Usage:
    uv run python scripts/backfill_morning_odds.py --year 2025
    uv run python scripts/backfill_morning_odds.py --year 2026
    uv run python scripts/backfill_morning_odds.py --year 2025 --limit 5 --dry-run
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
from sqlalchemy import select, update, func
from app.db.models.crawl import Race, RaceEntry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TRACK_TO_MEET = {"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}
KRA_DETAIL_URL = "https://race.kra.co.kr/raceScore/ScoretableDetailList.do"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}


def fetch_horse_odds(meet: str, rc_date: str, rc_no: str) -> dict | None:
    """Return {program_number: odds_win} from the detail page, or None."""
    try:
        res = requests.post(
            KRA_DETAIL_URL, headers=HEADERS,
            data={"meet": meet, "realRcDate": rc_date, "realRcNo": rc_no},
            timeout=15,
        )
        res.encoding = "euc-kr"
        parsed = KRALiveParser.parse_race_detail(res.text)
        if not parsed or not parsed.get("horses"):
            return None
        out = {}
        for h in parsed["horses"]:
            pno = h.get("horse_no")
            ow = h.get("odds_win")
            # odds_win defaults to 1.0 in parser when missing; skip implausible 1.0
            if pno and ow and ow > 1.0:
                out[int(pno)] = float(ow)
        return out or None
    except Exception as exc:
        logger.warning("HTTP error %s %s %s: %s", rc_date, meet, rc_no, exc)
    return None


async def backfill(year: int | None, limit: int | None, dry_run: bool) -> None:
    async with async_session_factory() as s:
        # races that have at least one NULL morning_odds entry
        q = (
            select(Race)
            .where(
                Race.id.in_(
                    select(RaceEntry.race_id)
                    .where(RaceEntry.morning_odds.is_(None))
                    .distinct()
                )
            )
        )
        if year:
            q = q.where(
                Race.race_date >= datetime.date(year, 1, 1),
                Race.race_date <= datetime.date(year, 12, 31),
            )
        q = q.order_by(Race.race_date.desc(), Race.id)
        if limit:
            q = q.limit(limit)
        races = list((await s.execute(q)).scalars().all())

    logger.info("morning_odds NULL 있는 경주: %d개 (year=%s)", len(races), year)

    updated_races = 0
    updated_entries = 0
    skipped = 0
    for i, race in enumerate(races):
        meet = TRACK_TO_MEET.get(race.track, "1")
        rc_date = race.race_date.strftime("%Y%m%d")
        odds_map = fetch_horse_odds(meet, rc_date, str(race.race_number))

        if not odds_map:
            skipped += 1
        else:
            async with async_session_factory() as s2:
                # only fill the NULL ones
                entries = list((await s2.execute(
                    select(RaceEntry).where(
                        RaceEntry.race_id == race.id,
                        RaceEntry.morning_odds.is_(None),
                    )
                )).scalars().all())
                n = 0
                for e in entries:
                    if e.program_number in odds_map:
                        e.morning_odds = odds_map[e.program_number]
                        n += 1
                if n and not dry_run:
                    await s2.commit()
                if n:
                    updated_races += 1
                    updated_entries += n
            if (i + 1) % 20 == 0 or updated_races <= 5:
                logger.info("[%d/%d] %s %s R%s → %d칸 채움 (배당맵 %d마리)",
                            i+1, len(races), race.race_date, race.track,
                            race.race_number, n if odds_map else 0, len(odds_map))
        await asyncio.sleep(0.3)

    tag = "[DRY RUN] " if dry_run else ""
    logger.info("%s완료: %d경주 / %d칸 morning_odds 채움, %d경주 데이터없음",
                tag, updated_races, updated_entries, skipped)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int)
    p.add_argument("--limit", type=int)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(backfill(args.year, args.limit, args.dry_run))
