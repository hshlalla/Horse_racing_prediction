"""
KRA 게시판 출전표 PDF 백필 (2021-01-08 ~ 현재)

세 boardNo를 순차 스캔하여 출전표·run_hr_all PDF를 파싱,
건강기록·조교시간을 DB에 upsert합니다.

boardNo 매핑:
  68 = 서울  시작 fileNo: 98201
  84 = 부산  시작 fileNo: 98197
  75 = 제주  시작 fileNo: 98194

Usage:
    uv run python scripts/backfill_board_pdfs.py
    uv run python scripts/backfill_board_pdfs.py 98201 160000   # 서울만
"""
from __future__ import annotations

import asyncio
import datetime
import io
import logging
import re
import sys
from typing import Optional

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DOWNLOAD_URL = "https://board.kra.co.kr/board/downloadFile.do"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}

# 스캔할 boardNo 목록: (boardNo, 트랙명, 시작 fileNo)
BOARDS = [
    (68, "SEOUL", 98201),
    (84, "BUSAN", 98197),
    (75, "JEJU",  98194),
]
END_FILE_NO = 160000

# 출전표 PDF 여부 판단 (파일명 기준)
# EUC-KR 깨진 '출전표' = ÃâÀüÇ¥
_ENTRY_PDF_NAMES = re.compile(
    r"(ÃâÀüÇ¥|출전표|run_hr_\d+_all|[sbj]_run_hr_\d+_all)",
    re.IGNORECASE,
)
DATE8_RE = re.compile(r"(\d{4})(\d{2})(\d{2})")   # YYYYMMDD
DATE6_RE = re.compile(r"(\d{2})(\d{2})(\d{2})")   # YYMMDD


def _is_entry_pdf(filename: str) -> bool:
    return bool(_ENTRY_PDF_NAMES.search(filename))


def _date_from_filename(filename: str) -> Optional[datetime.date]:
    # run_hr_YYMMDD_all or YYYYMMDD 출전표
    m8 = DATE8_RE.search(filename)
    if m8:
        try:
            return datetime.date(int(m8.group(1)), int(m8.group(2)), int(m8.group(3)))
        except ValueError:
            pass
    m6 = DATE6_RE.search(filename)
    if m6:
        try:
            return datetime.date(2000 + int(m6.group(1)), int(m6.group(2)), int(m6.group(3)))
        except ValueError:
            pass
    return None


async def _fetch(client: httpx.AsyncClient, board_no: int, file_no: int) -> tuple[bytes, str]:
    for attempt in range(3):
        try:
            r = await client.get(
                DOWNLOAD_URL,
                params={"boardNo": board_no, "fileNo": file_no},
                headers=HEADERS,
                timeout=25,
            )
            if len(r.content) < 200:
                return b"", ""
            cd = r.headers.get("content-disposition", "")
            m = re.search(r"filename[^;=\n]*=([^;\n]+)", cd)
            fname = m.group(1).strip().strip('"') if m else ""
            return r.content, fname
        except Exception as exc:
            if attempt == 2:
                logger.debug("boardNo=%d fileNo=%d fetch failed: %s", board_no, file_no, exc)
            await asyncio.sleep(1.5 ** attempt)
    return b"", ""


async def _process_pdf(session, pdf_bytes: bytes, filename: str) -> dict:
    from app.ml.crawl.crawl_pdf_entries import (
        _parse_entry_pdf_pages, _parse_pdf_pages, _yymmdd_to_date,
    )
    from app.ml.crawl.upsert import upsert_horse, upsert_workout_time, upsert_health_record

    # 출전표 형식 파서 우선, 결과 없으면 개별경주 파서 fallback
    entries = _parse_entry_pdf_pages(pdf_bytes)
    if not entries:
        entries = _parse_pdf_pages(pdf_bytes)
    if not entries:
        return {"horses": 0, "workouts": 0, "health": 0}

    horses_saved = workouts_saved = health_saved = 0
    for entry in entries:
        st = entry.get("start_training")
        st_date = _yymmdd_to_date(st["date"]) if st else None
        st_passed = st["passed"] if st else None
        swim_count = entry.get("swim_count", 0) or 0

        horse_id = await upsert_horse(
            session,
            name=entry["horse_name"],
            age=entry.get("horse_age") or 3,
            sex=entry.get("horse_sex") or "M",
            last_start_training_date=st_date,
            last_start_training_passed=st_passed,
        )
        horses_saved += 1

        for wk in entry.get("workout_records") or []:
            await upsert_workout_time(
                session,
                horse_id=horse_id,
                workout_date=wk["workout_date"],
                workout_type=wk.get("workout_type"),
                distance_m=wk.get("distance_m", 1000),
                time_s=wk.get("time_s"),
                rank=wk.get("rank"),
                group_size=None,
                start_training_passed=st_passed,
                swim_count_recent=swim_count if swim_count > 0 else None,
            )
            workouts_saved += 1

        for hr in entry.get("health_records") or []:
            await upsert_health_record(
                session,
                horse_id=horse_id,
                record_date=hr["record_date"],
                condition=hr["condition"],
                count=hr["count"],
            )
            health_saved += 1

    return {"horses": horses_saved, "workouts": workouts_saved, "health": health_saved}


async def scan_board(board_no: int, track: str, start_file_no: int, end_file_no: int) -> dict:
    from app.db.session import async_session_factory

    total_pdfs = total_horses = total_workouts = total_health = 0
    scanned = 0
    consecutive_miss = 0

    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        async with async_session_factory() as session:
            fno = start_file_no
            while fno <= end_file_no:
                scanned += 1
                content, fname = await _fetch(client, board_no, fno)

                if content and fname and _is_entry_pdf(fname):
                    consecutive_miss = 0
                    result = await _process_pdf(session, content, fname)
                    if result["horses"] > 0:
                        total_pdfs += 1
                        total_horses  += result["horses"]
                        total_workouts += result["workouts"]
                        total_health  += result["health"]
                        logger.info(
                            "[%s] fileNo=%d %s → 말%d 조교%d 건강%d",
                            track, fno, fname,
                            result["horses"], result["workouts"], result["health"],
                        )
                    fno += 1
                elif content:
                    # 파일 있지만 출전표 아님 (zip, A3 pdf 등)
                    consecutive_miss = 0
                    fno += 1
                else:
                    consecutive_miss += 1
                    # 연속 빈 구간은 크게 뛰기
                    fno += 5 if consecutive_miss >= 3 else 1

                if scanned % 200 == 0:
                    await session.commit()
                    logger.info(
                        "[%s] 진행 fileNo=%d 스캔=%d PDF=%d 건강=%d",
                        track, fno, scanned, total_pdfs, total_health,
                    )

                await asyncio.sleep(0.15)

            await session.commit()

    logger.info(
        "[%s] 완료: 스캔=%d PDF=%d 말=%d 조교=%d 건강=%d",
        track, scanned, total_pdfs, total_horses, total_workouts, total_health,
    )
    return {
        "track": track,
        "scanned": scanned,
        "pdfs": total_pdfs,
        "horses": total_horses,
        "workouts": total_workouts,
        "health": total_health,
    }


async def backfill_all(end_file_no: int = END_FILE_NO) -> list:
    results = []
    for board_no, track, start_fno in BOARDS:
        logger.info("=== %s (boardNo=%d) fileNo %d ~ %d ===", track, board_no, start_fno, end_file_no)
        result = await scan_board(board_no, track, start_fno, end_file_no)
        results.append(result)
    return results


if __name__ == "__main__":
    if len(sys.argv) == 3:
        # 단일 범위 스캔 (서울만)
        start = int(sys.argv[1])
        end = int(sys.argv[2])
        logger.info("단일 스캔: boardNo=68(서울) fileNo %d ~ %d", start, end)
        asyncio.run(scan_board(68, "SEOUL", start, end))
    else:
        end = int(sys.argv[1]) if len(sys.argv) == 2 else END_FILE_NO
        logger.info("전체 백필 시작: 서울/부산/제주 ~ fileNo %d", end)
        asyncio.run(backfill_all(end))
