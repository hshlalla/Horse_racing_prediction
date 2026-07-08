"""Parsers for KRA 출전상세정보 detail tabs + main-page top-3 favorites.

All functions take decoded HTML (EUC-KR already decoded) and return plain
dicts keyed by program_number. Content tables are identified by their header
containing 마명; row values follow the layouts verified live on 2026-07-05
(see tests/fixtures/)."""
from __future__ import annotations

import datetime
import re
from typing import Optional

from bs4 import BeautifulSoup

_DATE_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})")
_TOP3_RE = re.compile(r"^\s*(\d{1,2}),(\d{1,2}),(\d{1,2})\b")
_SESSION_RE = re.compile(r"^(\D*?)(\d+)$")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _content_tables(html: str) -> list:
    """Tables whose header row mentions 마명 (the data tables)."""
    out = []
    for t in _soup(html).find_all("table"):
        first = t.find("tr")
        if first and "마명" in first.get_text():
            out.append(t)
    return out


def _cells(tr) -> list[str]:
    return [td.get_text(" ", strip=True) for td in tr.find_all("td")]


def _date(s: str) -> Optional[datetime.date]:
    m = _DATE_RE.search(s)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _int(s: str) -> Optional[int]:
    s = s.replace(",", "").strip()
    m = re.search(r"-?\d+", s)
    return int(m.group(0)) if m else None


def _parse_program_number(cell: str) -> Optional[int]:
    """Extract integer program number from a cell that may contain &nbsp;."""
    m = re.search(r"\d+", cell)
    return int(m.group(0)) if m else None


def parse_starting_train(html: str) -> list[dict]:
    rows: list[dict] = []
    for table in _content_tables(html):
        for tr in table.find_all("tr")[1:]:
            c = _cells(tr)
            if len(c) < 5:
                continue
            pno = _parse_program_number(c[0])
            if pno is None:
                continue
            d = _date(c[2])
            if d is None:
                continue
            remark = c[4].strip() or None
            passed: Optional[bool] = None
            if remark:
                if "불량" in remark:
                    passed = False
                elif "양호" in remark or "합격" in remark:
                    passed = True
            rows.append({
                "program_number": pno,
                "horse_name": c[1].replace(" ", ""),
                "train_date": d,
                "rider": (c[3].strip() or None),
                "remark": remark,
                "equipment": (c[5].strip() or None) if len(c) > 5 else None,
                "passed": passed,
            })
    return rows


def parse_weight(html: str) -> list[dict]:
    rows: list[dict] = []
    for table in _content_tables(html):
        header = table.find("tr").get_text()
        if "금일체중" not in header:
            continue
        for tr in table.find_all("tr")[1:]:
            c = _cells(tr)
            if len(c) < 10:
                continue
            pno = _parse_program_number(c[0])
            if pno is None:
                continue
            top3 = _int(c[9])
            rows.append({
                "program_number": pno,
                "horse_name": c[1].replace(" ", ""),
                "today_weight": _int(c[2]),
                "weight_delta": _int(c[3]),
                "top3_avg": top3 if top3 else None,   # KRA prints 0 for "no stat"
            })
    return rows


def parse_train_state(html: str) -> list[dict]:
    rows: list[dict] = []
    for table in _content_tables(html):
        trs = table.find_all("tr")
        if len(trs) < 3 or "전주" not in trs[0].get_text():
            continue
        # trs[0]=번호|마명|전주|금주, trs[1]=weekday labels
        day_labels = [th.get_text(strip=True) for th in trs[1].find_all(["th", "td"])]
        half = len(day_labels) // 2
        labels = [f"전주-{d}" for d in day_labels[:half]] + [f"금주-{d}" for d in day_labels[half:]]
        for tr in trs[2:]:
            c = _cells(tr)
            if len(c) < 3:
                continue
            pno = _parse_program_number(c[0])
            if pno is None:
                continue
            sessions = []
            for i, cell in enumerate(c[2:]):
                cell = cell.strip()
                if not cell:
                    continue
                m = _SESSION_RE.match(cell)
                rider = (m.group(1).strip() or None) if m else (cell or None)
                count = int(m.group(2)) if m else None
                label = labels[i] if i < len(labels) else f"d{i}"
                sessions.append({"day_label": label, "rider": rider, "count": count})
            rows.append({
                "program_number": pno,
                "horse_name": c[1].replace(" ", ""),
                "sessions": sessions,
            })
    return rows


def parse_accessory_medical(html: str) -> list[dict]:
    rows: list[dict] = []
    for table in _content_tables(html):
        header = table.find("tr").get_text()
        if "진료" not in header:
            continue
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            c0 = tds[0].get_text(strip=True)
            pno = _parse_program_number(c0)
            if pno is None:
                continue
            med_text = tds[2].get_text("\n", strip=True)
            medical = []
            for line in med_text.split("\n"):
                d = _date(line)
                if d is None:
                    continue
                cond = _DATE_RE.sub("", line).strip()
                if cond:
                    medical.append({"record_date": d, "condition": cond})
            eiph_txt = tds[3].get_text(strip=True) if len(tds) > 3 else ""
            rows.append({
                "program_number": pno,
                "horse_name": tds[1].get_text(strip=True).replace(" ", ""),
                "medical": medical,
                "eiph": bool(eiph_txt),
            })
    return rows


def parse_main_top3(html: str) -> list[dict]:
    out: list[dict] = []
    for tr in _soup(html).find_all("tr"):
        c = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(c) < 6:
            continue
        track = next((x for x in c if x in ("서울", "부경", "제주")), None)
        rno = next((x for x in c if re.fullmatch(r"\d{1,2}R", x)), None)
        if not track or not rno:
            continue
        for cell in c:
            m = _TOP3_RE.match(cell)
            if m:
                out.append({
                    "track_label": track,
                    "race_number": int(rno[:-1]),
                    "fav_nums": [int(m.group(1)), int(m.group(2)), int(m.group(3))],
                })
                break
    return out
