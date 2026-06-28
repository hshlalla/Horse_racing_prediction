"""
역대 출마표 PDF 백필 — workout_times + health_records

KRA 서버에서 이용 가능한 날짜까지 거슬러 올라가며 PDF를 크롤합니다.
PDF가 없는 날짜(404)는 조용히 넘어갑니다.

Usage:
    uv run python scripts/backfill_pdf_workouts_health.py [start_date] [end_date]

    start_date: YYYY-MM-DD (기본값: 오늘 기준 365일 전)
    end_date:   YYYY-MM-DD (기본값: 어제)
"""
import asyncio
import datetime
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _is_race_day(d: datetime.date) -> bool:
    """KRA 경마는 금/토/일에만 열립니다."""
    return d.weekday() in (4, 5, 6)  # Fri=4, Sat=5, Sun=6


async def backfill(start_date: datetime.date, end_date: datetime.date) -> dict:
    from app.ml.crawl.crawl_pdf_entries import crawl_pdf_entries

    total_races = 0
    total_entries = 0
    dates_with_data = 0
    dates_tried = 0

    current = start_date
    while current <= end_date:
        if not _is_race_day(current):
            current += datetime.timedelta(days=1)
            continue

        dates_tried += 1
        try:
            result = await crawl_pdf_entries(current)
            if result["races_upserted"] > 0:
                total_races += result["races_upserted"]
                total_entries += result["entries_upserted"]
                dates_with_data += 1
                logger.info(
                    "%s: %d경주 %d말 처리",
                    current,
                    result["races_upserted"],
                    result["entries_upserted"],
                )
            else:
                logger.debug("%s: PDF 없음 (서버에서 제공 안 됨)", current)
        except Exception as exc:
            logger.warning("%s: 오류 — %s", current, exc)

        current += datetime.timedelta(days=1)

    logger.info(
        "=== 백필 완료 ===  날짜 시도: %d  데이터 있는 날짜: %d  총 경주: %d  총 말: %d",
        dates_tried,
        dates_with_data,
        total_races,
        total_entries,
    )
    return {
        "dates_tried": dates_tried,
        "dates_with_data": dates_with_data,
        "races": total_races,
        "entries": total_entries,
    }


if __name__ == "__main__":
    today = datetime.date.today()
    default_start = today - datetime.timedelta(days=365)
    default_end = today - datetime.timedelta(days=1)

    if len(sys.argv) >= 3:
        start = datetime.date.fromisoformat(sys.argv[1])
        end = datetime.date.fromisoformat(sys.argv[2])
    elif len(sys.argv) == 2:
        start = datetime.date.fromisoformat(sys.argv[1])
        end = default_end
    else:
        start = default_start
        end = default_end

    logger.info("PDF 백필 시작: %s ~ %s", start, end)
    asyncio.run(backfill(start, end))
