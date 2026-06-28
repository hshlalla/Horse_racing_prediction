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
from app.ml.crawl.upsert import upsert_horse, upsert_jockey, upsert_trainer, upsert_race, upsert_race_entry

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
    jockey_seen = False

    for line in lines:
        m = HORSE_LINE_RE.match(line)
        if m:
            if current:
                entries.append(current)
            prog = int(m.group(1))
            name = _clean_name(m.group(2))
            carry = float(m.group(3))
            # body weight: look ahead — format "462 468 471" near body weight delta
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
            }
            jockey_seen = False
            continue

        if current is None:
            continue

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

                    logger.info("Saved %s %d경주 (%d말)", track_name, rc_no, len(horse_entries))

            await session.commit()

    return {"races_upserted": races_saved, "entries_upserted": entries_saved}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    date_arg = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today()
    result = asyncio.run(crawl_pdf_entries(date_arg))
    print(result)
