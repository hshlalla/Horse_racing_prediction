"""
KRA 출마표 PDF 크롤러

PDF URL 패턴:
  https://race.kra.co.kr/down/pdf/{folder}/chulma/{prefix}_run_hr_{YYMMDD}_{RR:02d}.pdf
  서울: folder=seoul, prefix=s
  부산: folder=busan, prefix=b
  제주: folder=jeju,  prefix=j

Usage:
    from app.ml.crawl.crawl_pdf_entries import crawl_pdf_entries
    result = await crawl_pdf_entries(datetime.date(2026, 6, 28))
"""
from __future__ import annotations

import asyncio
import datetime
import io
import logging
import re
from typing import Dict, List, Optional, Tuple

import httpx
import pdfplumber

from app.db.session import async_session_factory
from app.ml.crawl.upsert import upsert_horse, upsert_jockey, upsert_trainer, upsert_race, upsert_race_entry, upsert_workout_time, upsert_health_record

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}

TRACKS = [
    ("SEOUL", "seoul", "s"),
    ("BUSAN", "busan", "b"),
    ("JEJU",  "jeju",  "j"),
]

DISTANCE_RE = re.compile(r"(\d{3,4})m|(\d{3,4})미터|거리[^\d]*(\d{3,4})")
RACE_HEADER_RE = re.compile(r"(서울|부산|제주)\s*(\d{1,2})경주")
# 마번 마명 부담중량(체중변화)
HORSE_LINE_RE = re.compile(
    r"^(\d{1,2})\s+([가-힣A-Za-z·\s]{2,25}?)\s{0,3}(\d{2,3}\.\d)\s*\("
)
# 조교사: (50조)박재우 형태
TRAINER_RE = re.compile(r"\((\d+)조\)([가-힣]{2,5})")
# 등록번호에서 성별·나이 추출: 3수(230823) → 나이=3, 성=수
AGE_SEX_RE = re.compile(r"^(\d+)(수|암|거)\((\d{6})\)")

# 조교 날짜 헤더: 260521-2R 주행심사 1000 비18%
WORKOUT_DATE_RE = re.compile(r"(\d{6})[-–](\d+)R\s*(주행심사|실기심사|장해심사|조교|경주)")
# 건강 이상 기록: YYMMDD + (부위) + 질환명 + N회
_HEALTH_CONDITIONS = (
    "근육통|찰과상|각막염|교돌상|복대상|감기|염증|구내염|낭치|피로|부종|골절|타박|열상"
    "|탈구|마비|파행|출혈|농양|건염|관절염|요통|과호흡|통증|상처|종창|타임상|지절부상"
    "|피부염|비염|폐렴|위궤양|경련|식욕부진|빈혈"
)
HEALTH_RE = re.compile(
    r"(\d{6})"                  # date YYMMDD
    r"[가-힣A-Za-z\s]{0,20}?"  # optional body part (lazy)
    r"(" + _HEALTH_CONDITIONS + r")"  # condition keyword
    r"(\d+)회"                  # count
)
# 출발훈련: 210106(승,양호) — 승/합격 = passed, 불합격/불량 = failed
START_TRAIN_RE = re.compile(r"출발훈련:(\d{6})\(([^)]+)\)")
# 수영: N회 N바퀴
SWIM_RE = re.compile(r"수영\s*:\s*(\d+)회")
# 조교 파트너 라인: ⑤ 1엠파이어1:05.2 54.0 코지
# ①–⑮ 원형숫자
_CIRCLE = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
WORKOUT_ENTRY_RE = re.compile(
    rf"([{_CIRCLE}])\s*(\d{{1,2}})([가-힣A-Za-z]{{2,7}})\s*(\d):(\d{{2}})\.(\d)"
)


def _parse_workout_time(time_str_parts: tuple) -> float:
    """Convert (minutes, seconds, tenths) to total seconds."""
    m, s, t = int(time_str_parts[0]), int(time_str_parts[1]), int(time_str_parts[2])
    return m * 60 + s + t / 10


def _circle_to_rank(circle: str) -> int:
    return _CIRCLE.index(circle) + 1


def _yymmdd_to_date(yymmdd: str) -> Optional[datetime.date]:
    try:
        y = int(yymmdd[:2]) + 2000
        return datetime.date(y, int(yymmdd[2:4]), int(yymmdd[4:6]))
    except Exception:
        return None


def _extract_health_records(lines: List[str]) -> List[Dict]:
    """Extract health incident records from a horse's text block."""
    combined = "\n".join(lines)
    results: List[Dict] = []
    seen: set = set()
    for m in HEALTH_RE.finditer(combined):
        d = _yymmdd_to_date(m.group(1))
        if d is None:
            continue
        condition = m.group(2)
        count = int(m.group(3))
        key = (d, condition)
        if key in seen:
            continue
        seen.add(key)
        results.append({"record_date": d, "condition": condition, "count": count})
    return results


def _extract_workouts(lines: List[str], prog_number: int, horse_name: str) -> List[Dict]:
    """
    From a horse's text block, extract workout sessions for this horse
    identified by name abbreviation (PDF truncates name to ~4 chars).
    Returns list of dicts, one per session (newest first).
    """
    # Find workout date headers: YYMMDD-NR 주행심사 1000 ...
    workout_dates: List[datetime.date] = []
    workout_types: List[str] = []
    for line in lines:
        for m in WORKOUT_DATE_RE.finditer(line):
            d = _yymmdd_to_date(m.group(1))
            if d:
                workout_dates.append(d)
                workout_types.append(m.group(3))

    if not workout_dates:
        return []

    # Match by name abbreviation: PDF uses the first ~4 chars of the full name
    combined = "\n".join(lines)
    results: List[Dict] = []
    for m in WORKOUT_ENTRY_RE.finditer(combined):
        abbrev = m.group(3)  # e.g. "엠파이어", "마호", "슈프림다"
        # Check if the horse's name starts with the abbreviation
        if horse_name.startswith(abbrev) or abbrev == horse_name:
            rank = _circle_to_rank(m.group(1))
            time_s = _parse_workout_time((m.group(4), m.group(5), m.group(6)))
            idx = len(results)
            if idx < len(workout_dates):
                results.append({
                    "workout_date": workout_dates[idx],
                    "workout_type": workout_types[idx] if idx < len(workout_types) else "주행심사",
                    "distance_m": 1000,
                    "time_s": time_s,
                    "rank": rank,
                })

    return results


def _extract_start_training(lines: List[str]) -> Optional[Dict]:
    """출발훈련 최근 결과 추출. passed=True(승/합격), False(불합격/불량)."""
    combined = "\n".join(lines)
    m = START_TRAIN_RE.search(combined)
    if not m:
        return None
    result_str = m.group(2)
    # Check failure keywords first (불합격 contains 합격, so order matters)
    if "불합격" in result_str or "불량" in result_str:
        passed = False
    else:
        passed = "승" in result_str or "합격" in result_str
    return {"date": m.group(1), "passed": passed}


def _extract_swim(lines: List[str]) -> int:
    """수영 훈련 횟수 추출. 없으면 0."""
    combined = "\n".join(lines)
    m = SWIM_RE.search(combined)
    return int(m.group(1)) if m else 0


def _clean_name(name: str) -> str:
    """Remove spaces inserted by PDF renderer between Korean characters."""
    return re.sub(r"\s+", "", name)


def _extract_distance(text: str) -> Optional[int]:
    """Try to extract race distance in metres from header text."""
    for pattern in [
        r"(\d{3,4})m\b",
        r"(\d{3,4})미터",
        r"출발[^\n]{0,30}(\d{3,4})",
    ]:
        m = re.search(pattern, text)
        if m:
            d = int(m.group(1))
            if 700 <= d <= 3000:
                return d
    # common KRA distances extracted from "기록" column header context
    for d_str in re.findall(r"\b(1000|1200|1300|1400|1600|1700|1800|2000|2300|900|1100|1110)\b", text):
        return int(d_str)
    return None


# 출전표 형식: 마번+마명이 붙어있는 줄 (예: "3아이언머스킷", "10인디라이트")
ENTRY_HORSE_LINE_RE = re.compile(r"^(\d{1,2})([가-힣A-Za-z·]{2,15})\s*$")


def _parse_entry_pdf_pages(pdf_bytes: bytes) -> List[Dict]:
    """
    출전표 형식 PDF 파서 (마번+마명 붙어있는 형식, 2021~2022년 게시판 파일).
    건강기록·조교시간만 추출한다 (race 연결 없이 horse 단위).
    pdfminer 사용 — pdfplumber와 달리 이 형식에서 줄 구분이 정확함.
    """
    import io as _io
    import pdfminer.high_level as _pdfminer
    full_text = _pdfminer.extract_text(_io.BytesIO(pdf_bytes))

    lines = full_text.splitlines()
    entries: List[Dict] = []
    current: Optional[Dict] = None
    current_lines: List[str] = []

    def _finalize(entry: Dict, block_lines: List[str]) -> None:
        entry["workout_records"] = _extract_workouts(
            block_lines, entry["program_number"], entry["horse_name"]
        )
        entry["health_records"] = _extract_health_records(block_lines)
        entry["start_training"] = _extract_start_training(block_lines)
        entry["swim_count"] = _extract_swim(block_lines)

    for line in lines:
        m = ENTRY_HORSE_LINE_RE.match(line.strip())
        if m:
            if current:
                _finalize(current, current_lines)
                entries.append(current)
            prog = int(m.group(1))
            name = _clean_name(m.group(2))
            current = {
                "program_number": prog,
                "horse_name": name,
                "carry_weight_kg": None,
                "body_weight_kg": None,
                "jockey_name": None,
                "trainer_name": None,
                "horse_age": None,
                "horse_sex": None,
                "distance_m": None,
                "grade": None,
                "workout_records": [],
            }
            current_lines = [line]
            continue

        if current is None:
            continue

        current_lines.append(line)

        if not current["horse_age"]:
            am = AGE_SEX_RE.match(line.strip())
            if am:
                current["horse_age"] = int(am.group(1))
                sex_map = {"수": "M", "암": "F", "거": "G"}
                current["horse_sex"] = sex_map.get(am.group(2), "M")

        if not current["trainer_name"]:
            tm = TRAINER_RE.search(line)
            if tm:
                current["trainer_name"] = tm.group(2)

    if current:
        _finalize(current, current_lines)
        entries.append(current)

    return entries


def _parse_pdf_pages(pdf_bytes: bytes) -> List[Dict]:
    """
    Parse all pages of a single race PDF.
    Returns list of horse-entry dicts.
    """
    entries = []
    full_text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            full_text += (page.extract_text() or "") + "\n"

    lines = full_text.splitlines()

    # --- race meta ---
    race_info = {"distance_m": None, "grade": None}
    for line in lines[:10]:
        if not race_info["distance_m"]:
            race_info["distance_m"] = _extract_distance(line)
        grade_m = re.search(r"(혼\d등급|\d등급|오픈|루키)", line)
        if grade_m and not race_info["grade"]:
            race_info["grade"] = grade_m.group(1)

    # --- parse horses ---
    # We look for lines matching HORSE_LINE_RE
    current: Optional[Dict] = None
    current_lines: List[str] = []
    jockey_seen = False

    def _finalize(entry: Dict, block_lines: List[str]) -> None:
        entry["workout_records"] = _extract_workouts(
            block_lines, entry["program_number"], entry["horse_name"]
        )
        entry["health_records"] = _extract_health_records(block_lines)
        entry["start_training"] = _extract_start_training(block_lines)
        entry["swim_count"] = _extract_swim(block_lines)

    for line in lines:
        m = HORSE_LINE_RE.match(line)
        if m:
            if current:
                _finalize(current, current_lines)
                entries.append(current)
            prog = int(m.group(1))
            name = _clean_name(m.group(2))
            carry = float(m.group(3))
            current = {
                "program_number": prog,
                "horse_name": name,
                "carry_weight_kg": carry,
                "body_weight_kg": None,
                "jockey_name": None,
                "trainer_name": None,
                "horse_age": None,
                "horse_sex": None,
                "distance_m": race_info["distance_m"],
                "grade": race_info["grade"],
                "workout_records": [],
            }
            current_lines = [line]
            jockey_seen = False
            continue

        if current is None:
            continue

        current_lines.append(line)

        # Age/sex from registration line: e.g. "3수(230823)갈색"
        if not current["horse_age"]:
            am = AGE_SEX_RE.match(line.strip())
            if am:
                current["horse_age"] = int(am.group(1))
                sex_map = {"수": "M", "암": "F", "거": "G"}
                current["horse_sex"] = sex_map.get(am.group(2), "M")

        # Trainer: (50조)박재우
        if not current["trainer_name"]:
            tm = TRAINER_RE.search(line)
            if tm:
                current["trainer_name"] = tm.group(2)

        # Body weight: three consecutive numbers like "462 468 471"
        if not current["body_weight_kg"]:
            bw = re.search(r"\b(4\d{2}|5\d{2})\s+(4\d{2}|5\d{2})\s+(4\d{2}|5\d{2})\b", line)
            if bw:
                current["body_weight_kg"] = float(bw.group(3))  # most recent

        # Jockey: standalone Korean name line (2-4 chars, no digits)
        stripped = line.strip()
        if (
            not jockey_seen
            and not current["jockey_name"]
            and re.fullmatch(r"[가-힣]{2,4}", stripped)
            and not re.search(r"\d", stripped)
        ):
            current["jockey_name"] = stripped
            jockey_seen = True

    if current:
        _finalize(current, current_lines)
        entries.append(current)

    return entries


async def _fetch_pdf(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    for attempt in range(3):
        try:
            res = await client.get(url, headers=HEADERS, timeout=20.0)
            if res.status_code == 200 and res.headers.get("content-type", "").startswith("application/pdf"):
                return res.content
            return None
        except Exception as exc:
            logger.warning("PDF fetch attempt %d failed %s: %s", attempt + 1, url, exc)
            await asyncio.sleep(2 ** attempt)
    return None


async def crawl_pdf_entries(
    target_date: datetime.date,
    tracks: Optional[List[str]] = None,
) -> Dict:
    date_str = target_date.strftime("%y%m%d")   # YYMMDD
    track_filter = set(tracks) if tracks else {"SEOUL", "BUSAN", "JEJU"}

    races_saved = 0
    entries_saved = 0

    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        async with async_session_factory() as session:
            for track_name, folder, prefix in TRACKS:
                if track_name not in track_filter:
                    continue

                for rc_no in range(1, 15):
                    url = (
                        f"https://race.kra.co.kr/down/pdf/{folder}/chulma/"
                        f"{prefix}_run_hr_{date_str}_{rc_no:02d}.pdf"
                    )
                    await asyncio.sleep(0.5)  # rate limit
                    pdf_bytes = await _fetch_pdf(client, url)
                    if not pdf_bytes:
                        break   # no more races for this track

                    horse_entries = _parse_pdf_pages(pdf_bytes)
                    if not horse_entries:
                        logger.warning("No entries parsed from %s", url)
                        continue

                    distance = horse_entries[0].get("distance_m") or 1400
                    grade = horse_entries[0].get("grade") or "unknown"

                    # Upsert Race
                    race_id = await upsert_race(
                        session,
                        track=track_name,
                        race_date=target_date,
                        race_number=rc_no,
                        race_name=f"{rc_no}경주",
                        distance_m=distance,
                        surface="Dirt",
                        grade=grade,
                        field_size=len(horse_entries),
                    )
                    races_saved += 1

                    for entry in horse_entries:
                        horse_id = await upsert_horse(
                            session,
                            name=entry["horse_name"],
                            age=entry.get("horse_age") or 3,
                            sex=entry.get("horse_sex") or "M",
                        )
                        jockey_id = None
                        if entry.get("jockey_name"):
                            jockey_id = await upsert_jockey(session, name=entry["jockey_name"])
                        trainer_id = None
                        if entry.get("trainer_name"):
                            trainer_id = await upsert_trainer(session, name=entry["trainer_name"])

                        await upsert_race_entry(
                            session,
                            race_id=race_id,
                            horse_id=horse_id,
                            program_number=entry["program_number"],
                            jockey_id=jockey_id,
                            trainer_id=trainer_id,
                            carry_weight_kg=entry.get("carry_weight_kg"),
                            body_weight_kg=entry.get("body_weight_kg"),
                            morning_odds=None,
                        )
                        entries_saved += 1

                        # Save workout times
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
                            )

                        # Save health records
                        for hr in entry.get("health_records") or []:
                            await upsert_health_record(
                                session,
                                horse_id=horse_id,
                                record_date=hr["record_date"],
                                condition=hr["condition"],
                                count=hr["count"],
                            )

                    logger.info("Saved %s %d경주 (%d말)", track_name, rc_no, len(horse_entries))

            await session.commit()

    return {"races_upserted": races_saved, "entries_upserted": entries_saved}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    date_arg = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today()
    result = asyncio.run(crawl_pdf_entries(date_arg))
    print(result)
