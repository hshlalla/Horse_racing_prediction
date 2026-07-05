# Odds-Free Prediction (Public Data Expansion, Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make race-morning predictions work without per-horse odds by (a) replacing odds features with a crawlable top-3 favorites proxy and (b) adding four new public per-horse signals (start training, weight, weekly workouts, medical/EIPH), each ablation-gated.

**Architecture:** New KRA detail-tab crawler (`chulmainfo/chulmaDetailInfo*.do`, POST meet/rcDate/rcNo, EUC-KR) feeds typed tables via existing upsert patterns; `dataset.py` derives FEATURES v3 (odds features removed); `service.py` swaps the inverse-odds anchor/market-prob for a rank-prior artifact; the SEOUL edge strategy is re-validated with a rank-prior backtest mode.

**Tech Stack:** Python 3.9 (`from __future__ import annotations`), httpx, BeautifulSoup+lxml, SQLAlchemy async + alembic, LightGBM/CatBoost, pytest. Run everything via `uv run` from `backend/`.

**Spec:** `docs/superpowers/specs/2026-07-05-odds-free-prediction-design.md`

## Global Constraints

- Working dir for all commands: `backend/` ; env: `export $(grep -E '^DATABASE_URL=' .env | head -1 | xargs)`
- Python 3.9: add `from __future__ import annotations` to every new module.
- KRA responses are EUC-KR: decode with `content.decode("euc-kr", errors="replace")`.
- Detect KRA's soft error page: response text containing `정상적인 접근` ⇒ treat as failure.
- All KRA requests: `headers={'User-Agent':'Mozilla/5.0','Referer':'https://race.kra.co.kr/chulmainfo/ChulmaDetailInfoList.do?Act=02&Sub=1&meet=1'}`, retry ≤3 with `asyncio.sleep(1.5**attempt)`, rate-limit `await asyncio.sleep(0.4)` between races.
- meet codes: `{"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}`.
- Never touch the betting (발매/todayrace) system.
- Existing test suite has 39 pre-existing failures + 7 errors (environment baseline). A task passes if **its own new tests pass and the baseline does not grow**.
- Commit after every task with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Schema — new tables + market_fav_rank column

**Files:**
- Modify: `backend/app/db/models/crawl.py` (add 2 models; add 1 column to `RaceEntry`)
- Create: `backend/alembic/versions/a7f8e9d0c1b2_add_detail_tab_tables.py`

**Interfaces:**
- Produces: ORM models `StartTrainingRecord` (table `start_training_records`: horse_id, train_date, rider, remark, passed, equipment; unique (horse_id, train_date)), `PreRaceWorkout` (table `pre_race_workouts`: race_id, horse_id, day_label, rider, count; unique (race_id, horse_id, day_label)); `RaceEntry.market_fav_rank: Optional[int]`.

- [ ] **Step 1: Confirm alembic head**

Run: `uv run alembic heads`
Expected: single head `f1a2b3c4d5e6` (if different, use that id as `down_revision` in Step 3).

- [ ] **Step 2: Add ORM models and column**

In `backend/app/db/models/crawl.py`, add to `RaceEntry` (after `morning_odds`):

```python
    market_fav_rank: Mapped[Optional[int]] = mapped_column(Integer)  # 당일 인기순위 1/2/3, else NULL
```

Append after `HealthRecord`:

```python
class StartTrainingRecord(Base):
    __tablename__ = "start_training_records"
    __table_args__ = (UniqueConstraint("horse_id", "train_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    train_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    rider: Mapped[Optional[str]] = mapped_column(String(30))
    remark: Mapped[Optional[str]] = mapped_column(String(50))     # 양호/진입불량/출발자세불량 …
    passed: Mapped[Optional[bool]] = mapped_column(Boolean)       # 양호→True, *불량→False
    equipment: Mapped[Optional[str]] = mapped_column(String(50))  # 출발장구
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class PreRaceWorkout(Base):
    __tablename__ = "pre_race_workouts"
    __table_args__ = (UniqueConstraint("race_id", "horse_id", "day_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    day_label: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. "전주-월", "금주-토"
    rider: Mapped[Optional[str]] = mapped_column(String(30))
    count: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
```

- [ ] **Step 3: Write migration**

Create `backend/alembic/versions/a7f8e9d0c1b2_add_detail_tab_tables.py`:

```python
"""add detail tab tables

Revision ID: a7f8e9d0c1b2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7f8e9d0c1b2'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'start_training_records',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('horse_id', sa.Integer(), sa.ForeignKey('horses.id'), nullable=False),
        sa.Column('train_date', sa.Date(), nullable=False),
        sa.Column('rider', sa.String(30)),
        sa.Column('remark', sa.String(50)),
        sa.Column('passed', sa.Boolean()),
        sa.Column('equipment', sa.String(50)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('horse_id', 'train_date'),
    )
    op.create_index('ix_strain_horse_date', 'start_training_records', ['horse_id', 'train_date'])
    op.create_table(
        'pre_race_workouts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('race_id', sa.Integer(), sa.ForeignKey('races.id'), nullable=False),
        sa.Column('horse_id', sa.Integer(), sa.ForeignKey('horses.id'), nullable=False),
        sa.Column('day_label', sa.String(10), nullable=False),
        sa.Column('rider', sa.String(30)),
        sa.Column('count', sa.Integer()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('race_id', 'horse_id', 'day_label'),
    )
    op.create_index('ix_prw_race_horse', 'pre_race_workouts', ['race_id', 'horse_id'])
    op.add_column('race_entries', sa.Column('market_fav_rank', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('race_entries', 'market_fav_rank')
    op.drop_index('ix_prw_race_horse', table_name='pre_race_workouts')
    op.drop_table('pre_race_workouts')
    op.drop_index('ix_strain_horse_date', table_name='start_training_records')
    op.drop_table('start_training_records')
```

- [ ] **Step 4: Apply and verify**

Run: `export $(grep -E '^DATABASE_URL=' .env | head -1 | xargs) && uv run alembic upgrade head`
Expected: `Running upgrade f1a2b3c4d5e6 -> a7f8e9d0c1b2`

Run: `uv run python -c "import asyncio;from sqlalchemy import text;from app.db.session import async_session_factory
async def m():
    async with async_session_factory() as s:
        for t in ['start_training_records','pre_race_workouts']:
            print(t,(await s.execute(text(f'SELECT COUNT(*) FROM {t}'))).scalar())
        print('col',(await s.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='race_entries' AND column_name='market_fav_rank'\"))).scalar())
asyncio.run(m())"`
Expected: `start_training_records 0`, `pre_race_workouts 0`, `col market_fav_rank`

- [ ] **Step 5: Commit**

```bash
git add app/db/models/crawl.py alembic/versions/a7f8e9d0c1b2_add_detail_tab_tables.py
git commit -m "feat: schema for detail-tab crawl (start training, pre-race workouts, market_fav_rank)"
```

---

### Task 2: Record real HTML fixtures from KRA

**Files:**
- Create: `backend/scripts/record_tab_fixtures.py`
- Create (output): `backend/tests/fixtures/tab_starting_train.html`, `tab_weight.html`, `tab_train_state.html`, `tab_accessory.html`, `main_seoul.html`

**Interfaces:**
- Produces: five saved HTML files used by Task 3 parser tests. Reference race for tab fixtures: **meet=1, rcDate=20260705, rcNo=6** (verified content: horse 파사퀸 program 1; StartingTrain row `2026/07/01 | 이동하 | 양호 | 꼬리받침`; Weight row `485 | -3 | … | 3위평균 490`).

- [ ] **Step 1: Write the recorder script**

Create `backend/scripts/record_tab_fixtures.py`:

```python
"""Record real KRA HTML fixtures for parser tests.

    DATABASE_URL not needed. Run:  uv run python scripts/record_tab_fixtures.py
"""
from __future__ import annotations

import asyncio
import pathlib

import httpx

KRA = "https://race.kra.co.kr"
H = {
    "User-Agent": "Mozilla/5.0",
    "Referer": KRA + "/chulmainfo/ChulmaDetailInfoList.do?Act=02&Sub=1&meet=1",
}
OUT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures"
TABS = {
    "tab_starting_train.html": "chulmaDetailInfoStartingTrain",
    "tab_weight.html": "chulmaDetailInfoWeight",
    "tab_train_state.html": "chulmaDetailInfoTrainState",
    "tab_accessory.html": "chulmaDetailInfoAccessoryState",
}
REF = {"meet": "1", "rcDate": "20260705", "rcNo": "6", "Act": "02", "Sub": "1"}


async def _fetch(client: httpx.AsyncClient, url: str, method: str = "POST", data=None) -> str:
    for attempt in range(3):
        try:
            if method == "POST":
                r = await client.post(url, headers=H, data=data, timeout=25)
            else:
                r = await client.get(url, headers=H, timeout=25)
            html = r.content.decode("euc-kr", errors="replace")
            if "정상적인 접근" in html or len(html) < 2000:
                raise RuntimeError("error page")
            return html
        except Exception:
            await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError(f"failed: {url}")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(follow_redirects=True) as c:
        for fname, ep in TABS.items():
            html = await _fetch(c, f"{KRA}/chulmainfo/{ep}.do", data=REF)
            (OUT / fname).write_text(html, encoding="utf-8")
            print("saved", fname, len(html))
            await asyncio.sleep(0.4)
        html = await _fetch(c, f"{KRA}/seoulMain.do", method="GET")
        (OUT / "main_seoul.html").write_text(html, encoding="utf-8")
        print("saved main_seoul.html", len(html))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run it**

Run: `uv run python scripts/record_tab_fixtures.py`
Expected: five `saved …` lines; files exist under `tests/fixtures/` each >2 KB.
If KRA DNS flaps (`nodename nor servname`), wait 60 s and rerun — it is intermittent.

- [ ] **Step 3: Commit**

```bash
git add scripts/record_tab_fixtures.py tests/fixtures/
git commit -m "test: record real KRA detail-tab HTML fixtures"
```

---

### Task 3: Detail-tab parsers (TDD against real fixtures)

**Files:**
- Create: `backend/app/ml/crawl/parsers/detail_tabs_parser.py`
- Test: `backend/tests/ml/test_detail_tabs_parser.py`

**Interfaces:**
- Produces (all take `html: str`):
  - `parse_starting_train(html) -> list[dict]` — keys: `program_number:int, horse_name:str, train_date:datetime.date, rider:str|None, remark:str|None, passed:bool|None, equipment:str|None`
  - `parse_weight(html) -> list[dict]` — keys: `program_number:int, horse_name:str, today_weight:int|None, weight_delta:int|None, top3_avg:int|None` (KRA prints `0` for missing stats ⇒ `None`)
  - `parse_train_state(html) -> list[dict]` — keys: `program_number:int, horse_name:str, sessions:list[dict]` with session keys `day_label:str, rider:str|None, count:int|None`
  - `parse_accessory_medical(html) -> list[dict]` — keys: `program_number:int, horse_name:str, medical:list[dict]` (`record_date:datetime.date, condition:str`), `eiph:bool`
  - `parse_main_top3(html) -> list[dict]` — keys: `track_label:str` (서울/부경/제주), `race_number:int, fav_nums:list[int]` (length 3)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/ml/test_detail_tabs_parser.py`:

```python
from __future__ import annotations

import datetime
import pathlib

import pytest

from app.ml.crawl.parsers.detail_tabs_parser import (
    parse_starting_train, parse_weight, parse_train_state,
    parse_accessory_medical, parse_main_top3,
)

FIX = pathlib.Path(__file__).resolve().parent.parent / "fixtures"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_starting_train_rows():
    rows = parse_starting_train(_read("tab_starting_train.html"))
    assert len(rows) >= 5
    r = rows[0]
    assert r["program_number"] == 1 and r["horse_name"] == "파사퀸"
    assert r["train_date"] == datetime.date(2026, 7, 1)
    assert r["remark"] == "양호" and r["passed"] is True
    assert r["equipment"] == "꼬리받침"
    # every row typed
    assert all(isinstance(x["train_date"], datetime.date) for x in rows)


def test_starting_train_passed_mapping():
    rows = parse_starting_train(_read("tab_starting_train.html"))
    for x in rows:
        if x["remark"] and "불량" in x["remark"]:
            assert x["passed"] is False
        elif x["remark"] == "양호":
            assert x["passed"] is True


def test_weight_rows():
    rows = parse_weight(_read("tab_weight.html"))
    byno = {r["program_number"]: r for r in rows}
    assert byno[1]["horse_name"] == "파사퀸"
    assert byno[1]["today_weight"] == 485 and byno[1]["weight_delta"] == -3
    assert byno[1]["top3_avg"] == 490
    # '0' means no stat -> None (황금송 3위평균=0 in fixture)
    assert byno[2]["top3_avg"] is None


def test_train_state_sessions():
    rows = parse_train_state(_read("tab_train_state.html"))
    byno = {r["program_number"]: r for r in rows}
    assert byno[1]["horse_name"] == "파사퀸"
    assert len(byno[1]["sessions"]) >= 5
    s = byno[1]["sessions"][0]
    assert set(s) == {"day_label", "rider", "count"}
    assert isinstance(s["count"], int)


def test_accessory_medical():
    rows = parse_accessory_medical(_read("tab_accessory.html"))
    byno = {r["program_number"]: r for r in rows}
    assert byno[1]["horse_name"] == "파사퀸"
    assert any(m["record_date"] == datetime.date(2026, 6, 10) for m in byno[1]["medical"])
    assert isinstance(byno[1]["eiph"], bool)


def test_main_top3():
    rows = parse_main_top3(_read("main_seoul.html"))
    assert len(rows) >= 1
    r = rows[0]
    assert r["track_label"] in ("서울", "부경", "제주")
    assert isinstance(r["race_number"], int)
    assert len(r["fav_nums"]) == 3 and all(isinstance(n, int) for n in r["fav_nums"])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/ml/test_detail_tabs_parser.py -x -q`
Expected: FAIL with `ModuleNotFoundError: … detail_tabs_parser`

- [ ] **Step 3: Implement the parsers**

Create `backend/app/ml/crawl/parsers/detail_tabs_parser.py`:

```python
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


def parse_starting_train(html: str) -> list[dict]:
    rows: list[dict] = []
    for table in _content_tables(html):
        for tr in table.find_all("tr")[1:]:
            c = _cells(tr)
            if len(c) < 5 or not c[0].strip().isdigit():
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
                "program_number": int(c[0]),
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
            if len(c) < 10 or not c[0].strip().isdigit():
                continue
            top3 = _int(c[9])
            rows.append({
                "program_number": int(c[0]),
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
            if len(c) < 3 or not c[0].strip().isdigit():
                continue
            sessions = []
            for i, cell in enumerate(c[2:]):
                cell = cell.strip()
                if not cell:
                    continue
                m = _SESSION_RE.match(cell)
                rider = m.group(1).strip() or None if m else (cell or None)
                count = int(m.group(2)) if m else None
                label = labels[i] if i < len(labels) else f"d{i}"
                sessions.append({"day_label": label, "rider": rider, "count": count})
            rows.append({
                "program_number": int(c[0]),
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
            if not c0.isdigit():
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
                "program_number": int(c0),
                "horse_name": tds[1].get_text(strip=True).replace(" ", ""),
                "medical": medical,
                "eiph": bool(eiph_txt),
            })
    return rows


def parse_main_top3(html: str) -> list[dict]:
    out: list[dict] = []
    for tr in _soup(html).find_all("tr"):
        c = _cells(tr)
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run python -m pytest tests/ml/test_detail_tabs_parser.py -q`
Expected: 6 passed. If a fixture-specific assertion fails (e.g. cell index off by one), inspect the fixture HTML table and fix the parser (not the expected values, which were verified live).

- [ ] **Step 5: Commit**

```bash
git add app/ml/crawl/parsers/detail_tabs_parser.py tests/ml/test_detail_tabs_parser.py
git commit -m "feat: parsers for KRA detail tabs and main-page top-3 favorites"
```

---

### Task 4: Upserts + crawl module

**Files:**
- Modify: `backend/app/ml/crawl/upsert.py` (2 new upserts)
- Create: `backend/app/ml/crawl/crawl_detail_tabs.py`
- Test: `backend/tests/ml/test_crawl_detail_tabs.py`

**Interfaces:**
- Consumes: Task 3 parsers; Task 1 models.
- Produces:
  - `upsert_start_training_record(session, horse_id:int, train_date, rider=None, remark=None, passed=None, equipment=None) -> None`
  - `upsert_pre_race_workout(session, race_id:int, horse_id:int, day_label:str, rider=None, count=None) -> None`
  - `crawl_detail_tabs.fetch_tab(client, tab_key:str, track:str, rc_date:str, rc_no:int) -> str|None` (tab_key ∈ starting_train/weight/train_state/accessory)
  - `crawl_detail_tabs.process_race(session, client, race) -> dict` counts `{"start_train":int,"weights":int,"workouts":int,"medical":int}` — crawls all 4 tabs for one `Race` ORM row and upserts.

- [ ] **Step 1: Write failing test (upserts + process_race with stubbed fetch)**

Create `backend/tests/ml/test_crawl_detail_tabs.py`:

```python
from __future__ import annotations

import datetime
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from app.ml.crawl import crawl_detail_tabs as cdt

FIX = pathlib.Path(__file__).resolve().parent.parent / "fixtures"


def test_tab_url_mapping():
    assert cdt.TABS["starting_train"] == "chulmaDetailInfoStartingTrain"
    assert cdt.TABS["weight"] == "chulmaDetailInfoWeight"
    assert cdt.TABS["train_state"] == "chulmaDetailInfoTrainState"
    assert cdt.TABS["accessory"] == "chulmaDetailInfoAccessoryState"
    assert cdt.TRACK_TO_MEET == {"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}


def test_error_page_detected():
    assert cdt._is_error_page("…정상적인 접근이 아닙니다…") is True
    assert cdt._is_error_page("<html>" + "x" * 3000) is False


@pytest.mark.asyncio
async def test_process_race_upserts(monkeypatch):
    """process_race maps program_number->horse_id and calls the right upserts."""
    fixtures = {
        "starting_train": (FIX / "tab_starting_train.html").read_text(encoding="utf-8"),
        "weight": (FIX / "tab_weight.html").read_text(encoding="utf-8"),
        "train_state": (FIX / "tab_train_state.html").read_text(encoding="utf-8"),
        "accessory": (FIX / "tab_accessory.html").read_text(encoding="utf-8"),
    }

    async def fake_fetch(client, tab_key, track, rc_date, rc_no):
        return fixtures[tab_key]

    monkeypatch.setattr(cdt, "fetch_tab", fake_fetch)

    calls = {"start_train": 0, "workout": 0, "health": 0, "weight_updates": 0}

    async def fake_ust(session, **kw):
        calls["start_train"] += 1

    async def fake_uprw(session, **kw):
        calls["workout"] += 1

    async def fake_uhr(session, **kw):
        calls["health"] += 1

    monkeypatch.setattr(cdt, "upsert_start_training_record", fake_ust)
    monkeypatch.setattr(cdt, "upsert_pre_race_workout", fake_uprw)
    monkeypatch.setattr(cdt, "upsert_health_record", fake_uhr)

    class E:  # entry stub
        def __init__(self, pn, hid):
            self.program_number, self.horse_id = pn, hid
            self.body_weight_kg = None
            self.market_fav_rank = None

    class R:  # race stub
        id = 1
        track = "SEOUL"
        race_date = datetime.date(2026, 7, 5)
        race_number = 6
        entries = [E(i, 100 + i) for i in range(1, 12)]

    session = AsyncMock()
    counts = await cdt.process_race(session, None, R())
    assert counts["start_train"] == calls["start_train"] > 0
    assert counts["workouts"] == calls["workout"] > 0
    assert counts["medical"] == calls["health"] > 0
    assert counts["weights"] > 0
    # 금일체중 filled onto the entry when it was NULL
    assert any(e.body_weight_kg is not None for e in R.entries)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/ml/test_crawl_detail_tabs.py -x -q`
Expected: FAIL `ModuleNotFoundError: … crawl_detail_tabs`

- [ ] **Step 3: Implement upserts**

Append to `backend/app/ml/crawl/upsert.py` (imports at top already include `pg_insert`, `sa`; add `StartTrainingRecord, PreRaceWorkout` to the models import):

```python
async def upsert_start_training_record(
    session: AsyncSession,
    horse_id: int,
    train_date: datetime.date,
    rider: Optional[str] = None,
    remark: Optional[str] = None,
    passed: Optional[bool] = None,
    equipment: Optional[str] = None,
) -> None:
    stmt = (
        pg_insert(StartTrainingRecord)
        .values(horse_id=horse_id, train_date=train_date, rider=rider,
                remark=remark, passed=passed, equipment=equipment)
        .on_conflict_do_update(
            index_elements=["horse_id", "train_date"],
            set_={"rider": rider, "remark": remark, "passed": passed, "equipment": equipment},
        )
    )
    await session.execute(stmt)


async def upsert_pre_race_workout(
    session: AsyncSession,
    race_id: int,
    horse_id: int,
    day_label: str,
    rider: Optional[str] = None,
    count: Optional[int] = None,
) -> None:
    stmt = (
        pg_insert(PreRaceWorkout)
        .values(race_id=race_id, horse_id=horse_id, day_label=day_label,
                rider=rider, count=count)
        .on_conflict_do_update(
            index_elements=["race_id", "horse_id", "day_label"],
            set_={"rider": rider, "count": count},
        )
    )
    await session.execute(stmt)
```

- [ ] **Step 4: Implement crawl module**

Create `backend/app/ml/crawl/crawl_detail_tabs.py`:

```python
"""Crawl the four KRA 출전상세정보 tabs for one race and upsert typed rows.

Endpoints verified working for historical dates (2022–2026) on 2026-07-05.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.ml.crawl.parsers.detail_tabs_parser import (
    parse_starting_train, parse_weight, parse_train_state, parse_accessory_medical,
)
from app.ml.crawl.upsert import (
    upsert_start_training_record, upsert_pre_race_workout, upsert_health_record,
)

logger = logging.getLogger(__name__)

KRA = "https://race.kra.co.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": KRA + "/chulmainfo/ChulmaDetailInfoList.do?Act=02&Sub=1&meet=1",
}
TRACK_TO_MEET = {"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}
TABS = {
    "starting_train": "chulmaDetailInfoStartingTrain",
    "weight": "chulmaDetailInfoWeight",
    "train_state": "chulmaDetailInfoTrainState",
    "accessory": "chulmaDetailInfoAccessoryState",
}


def _is_error_page(html: str) -> bool:
    return "정상적인 접근" in html or len(html) < 2000


async def fetch_tab(client: httpx.AsyncClient, tab_key: str, track: str,
                    rc_date: str, rc_no: int) -> Optional[str]:
    url = f"{KRA}/chulmainfo/{TABS[tab_key]}.do"
    data = {"Sub": "1", "Act": "02", "meet": TRACK_TO_MEET[track],
            "rcDate": rc_date, "rcNo": str(rc_no)}
    for attempt in range(3):
        try:
            r = await client.post(url, headers=HEADERS, data=data, timeout=25)
            html = r.content.decode("euc-kr", errors="replace")
            if _is_error_page(html):
                return None
            return html
        except Exception as exc:
            if attempt == 2:
                logger.warning("fetch_tab %s %s r%s failed: %s", tab_key, rc_date, rc_no, exc)
            await asyncio.sleep(1.5 ** attempt)
    return None


async def process_race(session, client: httpx.AsyncClient, race) -> dict:
    """Crawl all four tabs for one Race ORM row (entries preloaded) and upsert."""
    rc_date = race.race_date.strftime("%Y%m%d")
    num_to_horse = {e.program_number: e.horse_id for e in race.entries}
    num_to_entry = {e.program_number: e for e in race.entries}
    counts = {"start_train": 0, "weights": 0, "workouts": 0, "medical": 0}

    html = await fetch_tab(client, "starting_train", race.track, rc_date, race.race_number)
    if html:
        for row in parse_starting_train(html):
            hid = num_to_horse.get(row["program_number"])
            if hid is None:
                continue
            await upsert_start_training_record(
                session, horse_id=hid, train_date=row["train_date"],
                rider=row["rider"], remark=row["remark"],
                passed=row["passed"], equipment=row["equipment"])
            counts["start_train"] += 1

    html = await fetch_tab(client, "weight", race.track, rc_date, race.race_number)
    if html:
        for row in parse_weight(html):
            entry = num_to_entry.get(row["program_number"])
            if entry is None or row["today_weight"] is None:
                continue
            if entry.body_weight_kg is None:
                entry.body_weight_kg = float(row["today_weight"])
            counts["weights"] += 1

    html = await fetch_tab(client, "train_state", race.track, rc_date, race.race_number)
    if html:
        for row in parse_train_state(html):
            hid = num_to_horse.get(row["program_number"])
            if hid is None:
                continue
            for s in row["sessions"]:
                await upsert_pre_race_workout(
                    session, race_id=race.id, horse_id=hid,
                    day_label=s["day_label"], rider=s["rider"], count=s["count"])
                counts["workouts"] += 1

    html = await fetch_tab(client, "accessory", race.track, rc_date, race.race_number)
    if html:
        for row in parse_accessory_medical(html):
            hid = num_to_horse.get(row["program_number"])
            if hid is None:
                continue
            for m in row["medical"]:
                await upsert_health_record(
                    session, horse_id=hid, record_date=m["record_date"],
                    condition=m["condition"][:50])
                counts["medical"] += 1
            if row["eiph"]:
                await upsert_health_record(
                    session, horse_id=hid, record_date=race.race_date,
                    condition="폐출혈")
                counts["medical"] += 1

    return counts
```

- [ ] **Step 5: Run tests**

Run: `uv run python -m pytest tests/ml/test_crawl_detail_tabs.py tests/ml/test_detail_tabs_parser.py -q`
Expected: all pass (needs `pytest-asyncio` — already a dev dep since other async tests exist; if `asyncio` marker unknown, add `asyncio_mode = auto` under `[tool.pytest.ini_options]` in `pyproject.toml`).

- [ ] **Step 6: Commit**

```bash
git add app/ml/crawl/upsert.py app/ml/crawl/crawl_detail_tabs.py tests/ml/test_crawl_detail_tabs.py
git commit -m "feat: detail-tab crawl module with typed upserts"
```

---

### Task 5: Resumable backfill script

**Files:**
- Create: `backend/scripts/backfill_detail_tabs.py`

**Interfaces:**
- Consumes: `crawl_detail_tabs.process_race`.
- Produces: CLI `uv run python scripts/backfill_detail_tabs.py [--tracks SEOUL BUSAN JEJU] [--since 2021-01-01] [--until today] [--limit N]`; progress file `backfill_detail_tabs.progress.json` (`{"done_race_ids": [...]}`) making reruns skip completed races.

- [ ] **Step 1: Write the script**

```python
"""Backfill the four detail tabs for historical races (3 tracks, 2021–).

Iterates races already in the DB (no fileNo scanning), rate-limited 0.4 s,
resumable via backfill_detail_tabs.progress.json.

    DATABASE_URL=… uv run python scripts/backfill_detail_tabs.py --since 2021-01-01
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import pathlib

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.db.models.crawl import Race
from app.ml.crawl.crawl_detail_tabs import process_race

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

PROGRESS = pathlib.Path(__file__).resolve().parent.parent / "backfill_detail_tabs.progress.json"


def _load_done() -> set:
    if PROGRESS.exists():
        return set(json.loads(PROGRESS.read_text())["done_race_ids"])
    return set()


def _save_done(done: set) -> None:
    PROGRESS.write_text(json.dumps({"done_race_ids": sorted(done)}))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", nargs="+", default=["SEOUL", "BUSAN", "JEJU"])
    ap.add_argument("--since", type=datetime.date.fromisoformat,
                    default=datetime.date(2021, 1, 1))
    ap.add_argument("--until", type=datetime.date.fromisoformat,
                    default=datetime.date.today())
    ap.add_argument("--limit", type=int, default=0, help="stop after N races (0=all)")
    args = ap.parse_args()

    done = _load_done()
    processed = 0
    totals = {"start_train": 0, "weights": 0, "workouts": 0, "medical": 0}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Race).options(selectinload(Race.entries))
                .where(Race.track.in_(args.tracks),
                       Race.race_date >= args.since,
                       Race.race_date <= args.until)
                .order_by(Race.race_date, Race.track, Race.race_number)
            )
            races = list(result.scalars().all())
            todo = [r for r in races if r.id not in done]
            logger.info("races: %d total, %d already done, %d to go",
                        len(races), len(races) - len(todo), len(todo))

            for race in todo:
                try:
                    counts = await process_race(session, client, race)
                    for k in totals:
                        totals[k] += counts[k]
                except Exception as exc:
                    logger.warning("race %s (%s %s r%s) failed: %s — will retry on rerun",
                                   race.id, race.race_date, race.track, race.race_number, exc)
                    await asyncio.sleep(2)
                    continue
                done.add(race.id)
                processed += 1
                if processed % 50 == 0:
                    await session.commit()
                    _save_done(done)
                    logger.info("progress %d/%d  totals=%s", processed, len(todo), totals)
                if args.limit and processed >= args.limit:
                    break
                await asyncio.sleep(0.4)

            await session.commit()
            _save_done(done)
    logger.info("DONE processed=%d totals=%s", processed, totals)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Smoke-test on 3 races**

Run: `export $(grep -E '^DATABASE_URL=' .env | head -1 | xargs) && uv run python scripts/backfill_detail_tabs.py --tracks SEOUL --since 2026-06-01 --limit 3`
Expected: log lines ending `DONE processed=3 totals={'start_train': >0, …}`; verify:
`uv run python -c "import asyncio;from sqlalchemy import text;from app.db.session import async_session_factory
async def m():
    async with async_session_factory() as s:
        print('st',(await s.execute(text('SELECT COUNT(*) FROM start_training_records'))).scalar())
        print('prw',(await s.execute(text('SELECT COUNT(*) FROM pre_race_workouts'))).scalar())
asyncio.run(m())"`
Expected: both counts > 0.

- [ ] **Step 3: Add progress file to gitignore + commit**

Append `backfill_detail_tabs.progress.json` to `backend/.gitignore`.

```bash
git add scripts/backfill_detail_tabs.py .gitignore
git commit -m "feat: resumable backfill for detail tabs (DB-driven race list)"
```

---

### Task 6: verify_data_integrity.py coverage sections

**Files:**
- Modify: `backend/scripts/verify_data_integrity.py`

**Interfaces:**
- Consumes: tables from Task 1.
- Produces: report sections `[11] 출발조교(신규) 커버리지`, `[12] 경주전조교(신규) 커버리지` printed per year like existing sections; script still exits with 합격/불합격 as before (new sections are informational ⚠ only, not gating — gating stays on existing checks).

- [ ] **Step 1: Add queries**

In `run_all()` after section [10], add:

```python
        # 11. 출발조교(start_training_records) 커버리지 — 경주 출전 말 기준
        r = await session.execute(text("""
            SELECT EXTRACT(YEAR FROM r.race_date)::int AS yr,
                   COUNT(DISTINCT e.horse_id) AS horses,
                   COUNT(DISTINCT e.horse_id) FILTER (
                       WHERE EXISTS (SELECT 1 FROM start_training_records s
                                     WHERE s.horse_id = e.horse_id
                                       AND s.train_date <  r.race_date
                                       AND s.train_date >= r.race_date - INTERVAL '180 days')
                   ) AS with_st
            FROM races r JOIN race_entries e ON e.race_id = r.id
            WHERE r.race_date >= '2021-01-01'
            GROUP BY yr ORDER BY yr
        """))
        print("\n[11] 출발조교(신규) 커버리지 (경주 출전 말 기준):")
        for row in r.all():
            pct = row.with_st / row.horses * 100 if row.horses else 0
            mark = "✓" if pct >= 40 else "⚠"
            print(f"  {row.yr}: {row.with_st:,}/{row.horses:,}마 ({pct:5.1f}%)  {mark}")

        # 12. 경주전조교(pre_race_workouts) 커버리지 — 경주 단위
        r = await session.execute(text("""
            SELECT EXTRACT(YEAR FROM r.race_date)::int AS yr,
                   COUNT(DISTINCT r.id) AS races,
                   COUNT(DISTINCT w.race_id) AS with_wk
            FROM races r LEFT JOIN pre_race_workouts w ON w.race_id = r.id
            WHERE r.race_date >= '2021-01-01'
            GROUP BY yr ORDER BY yr
        """))
        print("\n[12] 경주전조교(신규) 커버리지 (경주 기준):")
        for row in r.all():
            pct = row.with_wk / row.races * 100 if row.races else 0
            mark = "✓" if pct >= 40 else "⚠"
            print(f"  {row.yr}: {row.with_wk:,}/{row.races:,}경주 ({pct:5.1f}%)  {mark}")
```

- [ ] **Step 2: Run**

Run: `export $(grep -E '^DATABASE_URL=' .env | head -1 | xargs) && uv run python scripts/verify_data_integrity.py`
Expected: sections [11]/[12] print (low % is fine pre-backfill); final verdict unchanged (`✓ 합격`).

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_data_integrity.py
git commit -m "feat: integrity coverage sections for new detail-tab tables"
```

---

### Task 7: dataset.py FEATURES v3 + feature engineering

**Files:**
- Modify: `backend/app/ml/train/dataset.py` (FEATURES list, `_QUERY`, `_apply_features`)
- Test: `backend/tests/ml/test_dataset_features_v3.py`

**Interfaces:**
- Consumes: tables from Task 1 (SQL joins), existing `_apply_features` df.
- Produces FEATURES v3 (35 features) = current 29 − {`morning_odds`,`morning_odds_rank`} + G1 {`mkt_fav_rank`,`mkt_is_fav`} + G2 {`days_since_start_train`,`start_train_ok_rate`,`start_train_count_90d`} + G3 {`body_weight_kg`,`body_weight_delta_kg`,`weight_vs_top3avg`} + G4 {`workout_count_2w`} + G5 {`eiph_flag`}. All new columns exist on the df after `_apply_features` regardless of DB coverage (defaults: rank 99 / rate 0.5 / counts 0 / days 999 / deltas 0.0).

- [ ] **Step 1: Write failing tests**

Create `backend/tests/ml/test_dataset_features_v3.py` (mirrors the style of `tests/ml/test_dataset_features.py`: build a small synthetic df with the raw SQL columns and run `_apply_features`):

```python
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from app.ml.train.dataset import _apply_features, FEATURES


def _raw_df():
    """Two races × 3 horses with the raw columns _QUERY provides."""
    n = 6
    df = pd.DataFrame({
        "race_id":   [1, 1, 1, 2, 2, 2],
        "race_date": pd.to_datetime(["2026-01-01"] * 3 + ["2026-02-01"] * 3),
        "horse_id":  [10, 11, 12, 10, 11, 12],
        "jockey_id": [1] * n, "trainer_id": [1] * n, "sire_id": [1] * n,
        "program_number": [1, 2, 3, 1, 2, 3],
        "distance_m": [1200] * n, "field_size": [3] * n,
        "track": ["SEOUL"] * n, "track_condition": ["건조"] * n,
        "weather": ["맑음"] * n, "humidity": [10] * n,
        "surface": ["더트"] * n, "grade": ["국6"] * n,
        "carry_weight_kg": [55.0] * n,
        "body_weight_kg": [480.0, 470.0, 460.0, 486.0, 470.0, 455.0],
        "morning_odds": [2.5, 5.0, 10.0, 3.0, None, 8.0],
        "horse_age": [3] * n, "horse_sex": ["수"] * n,
        "last_start_training_date": [None] * n,
        "last_start_training_passed": [None] * n,
        "s1f_time": [14.0] * n, "g3f_time": [37.0] * n,
        "corner1_rank": [1] * n, "corner2_rank": [1] * n, "corner3_rank": [1] * n,
        "corner4_rank": [1] * n, "corner5_rank": [None] * n,
        "corner6_rank": [None] * n, "corner7_rank": [None] * n,
        "finish_position": [1, 2, 3, 2, 1, 3],
        "finish_time_s": [75.0] * n, "is_win": [1, 0, 0, 0, 1, 0],
        "opening_odds": [None] * n, "closing_odds": [None] * n,
        "recent_workout_time_s": [None] * n, "recent_workout_rank": [None] * n,
        "swim_count_recent": [None] * n,
        "injury_count_30d": [0] * n, "days_since_injury": [None] * n,
        "serious_injury_count_30d": [0] * n, "serious_injury_count_90d": [0] * n,
        "days_since_serious_injury": [None] * n, "illness_count_30d": [0] * n,
        "total_injury_count": [0] * n, "recent_workout_count_30d": [None] * n,
        # --- new raw columns from _QUERY v3 ---
        "days_since_start_train": [3, None, 40, 5, None, None],
        "start_train_ok_rate": [1.0, None, 0.0, 1.0, None, None],
        "start_train_count_90d": [2, None, 1, 1, None, None],
        "workout_count_2w": [8, None, 3, 6, None, None],
        "eiph_flag": [0, 1, None, 0, 1, None],
    })
    return df


def test_odds_features_removed_and_market_proxy_added():
    assert "morning_odds" not in FEATURES
    assert "morning_odds_rank" not in FEATURES
    for f in ["mkt_fav_rank", "mkt_is_fav", "days_since_start_train",
              "start_train_ok_rate", "start_train_count_90d",
              "workout_count_2w", "weight_vs_top3avg", "eiph_flag",
              "body_weight_kg", "body_weight_delta_kg"]:
        assert f in FEATURES, f


def test_mkt_fav_rank_from_odds():
    out = _apply_features(_raw_df())
    r1 = out[out.race_id == 1].sort_values("program_number")
    assert list(r1["mkt_fav_rank"]) == [1.0, 2.0, 3.0]
    assert list(r1["mkt_is_fav"]) == [1, 0, 0]
    # race 2: horse with NULL odds gets rank 99
    r2 = out[out.race_id == 2].sort_values("program_number")
    assert r2.iloc[1]["mkt_fav_rank"] == 99.0


def test_new_feature_defaults():
    out = _apply_features(_raw_df())
    row = out[(out.race_id == 2) & (out.program_number == 3)].iloc[0]
    assert row["days_since_start_train"] == 999
    assert row["start_train_ok_rate"] == 0.5
    assert row["start_train_count_90d"] == 0
    assert row["workout_count_2w"] == 0
    assert row["eiph_flag"] == 0


def test_weight_vs_top3avg_no_leakage():
    out = _apply_features(_raw_df())
    # horse 10: race1 (480kg, finished 1st) is its first race -> no prior top3 -> 0.0
    first = out[(out.race_id == 1) & (out.horse_id == 10)].iloc[0]
    assert first["weight_vs_top3avg"] == 0.0
    # race2: prior top3 avg = 480 -> 486-480 = +6
    second = out[(out.race_id == 2) & (out.horse_id == 10)].iloc[0]
    assert second["weight_vs_top3avg"] == pytest.approx(6.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/ml/test_dataset_features_v3.py -x -q`
Expected: FAIL on `test_odds_features_removed_and_market_proxy_added`.

- [ ] **Step 3: Update FEATURES list**

In `backend/app/ml/train/dataset.py`, replace the FEATURES list: delete `'morning_odds',` and `'morning_odds_rank',` lines and append before the closing bracket:

```python
    # --- FEATURES v3 (2026-07-05): odds numbers removed (KRA stopped publishing
    # per-horse pre-race odds). Market signal now comes from the crawlable top-3
    # favorites proxy; measured recovery: SEOUL val_log_loss 2.065→1.912 (74% of
    # the odds skill). Groups G1–G5 are individually ablation-gated. ---
    'mkt_fav_rank',            # G1: market favorite rank 1/2/3 else 99 (train: from odds; predict: crawled)
    'mkt_is_fav',              # G1: 1 if market favorite
    'days_since_start_train',  # G2: days since last 출발조교 (999 = never)
    'start_train_ok_rate',     # G2: share of 양호 among past 출발조교 (0.5 = unknown)
    'start_train_count_90d',   # G2
    'body_weight_kg',          # G3: 금일체중 (filled race-morning by crawl)
    'body_weight_delta_kg',    # G3
    'weight_vs_top3avg',       # G3: today weight − avg weight of past top-3 finishes
    'workout_count_2w',        # G4: pre-race workout sessions (전주+금주)
    'eiph_flag',               # G5: 폐출혈 record within 365d
```

- [ ] **Step 4: Update `_QUERY`**

Add to the SELECT list (after `wk_cnt.recent_workout_count_30d`):

```sql
    st.days_since_start_train,
    st.start_train_ok_rate,
    st.start_train_count_90d,
    prw.workout_count_2w,
    eiph.eiph_flag
```

Add the joins (after the existing `wk_cnt` lateral join, before the final WHERE/ORDER):

```sql
LEFT JOIN LATERAL (
    SELECT (r.race_date - MAX(s.train_date))::int          AS days_since_start_train,
           AVG(CASE WHEN s.passed THEN 1.0
                    WHEN s.passed = false THEN 0.0 END)     AS start_train_ok_rate,
           COUNT(*) FILTER (WHERE s.train_date >= r.race_date - INTERVAL '90 days')::int
                                                            AS start_train_count_90d
    FROM start_training_records s
    WHERE s.horse_id = e.horse_id AND s.train_date < r.race_date
) st ON true
LEFT JOIN LATERAL (
    SELECT COUNT(*)::int AS workout_count_2w
    FROM pre_race_workouts w2
    WHERE w2.race_id = r.id AND w2.horse_id = e.horse_id
) prw ON true
LEFT JOIN LATERAL (
    SELECT 1 AS eiph_flag
    FROM health_records hr2
    WHERE hr2.horse_id = e.horse_id
      AND hr2.condition LIKE '%%폐출혈%%'
      AND hr2.record_date <  r.race_date
      AND hr2.record_date >= r.race_date - INTERVAL '365 days'
    LIMIT 1
) eiph ON true
```

(Note the `%%` escaping — `_QUERY` goes through `pd.read_sql(text(...))`; if the query string is not %-formatted anywhere, single `%` works: check how `_QUERY` is used — it is passed to `text()` directly, so use single `%`.)

- [ ] **Step 5: Update `_apply_features`**

Add before the final `df.sort_values(['race_date','race_id'], inplace=True); return df`:

```python
    # --- FEATURES v3 additions ---
    # G1 market proxy: rank by odds within race (train-time). NULL odds → 99.
    odds_rank = df.groupby('race_id')['morning_odds'].rank(method='first', ascending=True)
    df['mkt_fav_rank'] = np.where(df['morning_odds'].notna() & (odds_rank <= 3),
                                  odds_rank, 99.0).astype(float)
    df['mkt_is_fav'] = (df['mkt_fav_rank'] == 1.0).astype(int)

    # G2 start training defaults
    df['days_since_start_train'] = df['days_since_start_train'].fillna(999).astype(int)
    df['start_train_ok_rate'] = df['start_train_ok_rate'].fillna(0.5).astype(float)
    df['start_train_count_90d'] = df['start_train_count_90d'].fillna(0).astype(int)

    # G4 / G5 defaults
    df['workout_count_2w'] = df['workout_count_2w'].fillna(0).astype(int)
    df['eiph_flag'] = df['eiph_flag'].fillna(0).astype(int)

    # G3 weight vs past-top3 average (leakage-safe: prior races only)
    df.sort_values(['horse_id', 'race_date', 'race_id'], inplace=True)
    top3_w = df['body_weight_kg'].where(df['finish_position'] <= 3)
    past_top3_avg = top3_w.groupby(df['horse_id']).transform(
        lambda s: s.shift().expanding().mean())
    df['weight_vs_top3avg'] = (df['body_weight_kg'] - past_top3_avg).fillna(0.0)
```

(`body_weight_kg` NaN handling: it is already filled elsewhere in `_apply_features`; if not, add `df['body_weight_kg'] = df['body_weight_kg'].fillna(df.groupby('race_id')['body_weight_kg'].transform('mean')).fillna(470.0)` before the G3 block. `body_weight_delta_kg` is already computed by the existing v1 code — verify with `grep -n body_weight_delta_kg app/ml/train/dataset.py`; if it was removed, compute `df['body_weight_delta_kg'] = df.groupby('horse_id')['body_weight_kg'].diff().fillna(0.0)` inside the sorted-by-horse block.)

- [ ] **Step 6: Run tests**

Run: `uv run python -m pytest tests/ml/test_dataset_features_v3.py tests/ml/test_dataset_features.py -q`
Expected: new tests pass. If old `test_dataset_features.py` asserts `morning_odds` in FEATURES, update those assertions to the v3 reality (odds columns still exist on the df — only the FEATURES list changed).

- [ ] **Step 7: Full-load smoke test**

Run: `export $(grep -E '^DATABASE_URL=' .env | head -1 | xargs) && uv run python -c "import os;from app.ml.train.dataset import load_dataset_pg,FEATURES
tr,va,te,f,t=load_dataset_pg(os.environ['DATABASE_URL'])
print(len(FEATURES),'features'); print(tr[FEATURES].isna().sum().sum(),'NaNs in train FEATURES')"`
Expected: `35 features` (approx) and `0 NaNs`.

- [ ] **Step 8: Commit**

```bash
git add app/ml/train/dataset.py tests/ml/test_dataset_features_v3.py tests/ml/test_dataset_features.py
git commit -m "feat: FEATURES v3 — odds-free market proxy + detail-tab feature groups"
```

---

### Task 8: Rank priors artifact (pipeline) + loader

**Files:**
- Modify: `backend/app/ml/train/pipeline.py`
- Test: `backend/tests/ml/test_rank_priors.py`

**Interfaces:**
- Produces: `pipeline._compute_rank_priors(track_train: pd.DataFrame) -> dict` returning `{"1": float, "2": float, "3": float, "99": float}` (P(win | mkt_fav_rank)); `pipeline._save_rank_priors(track: str, priors: dict) -> None` merging into `models/rank_priors.json` as `{track: priors}`; called inside `run_train` right after the track filter. Task 9 reads this file.

- [ ] **Step 1: Write failing test**

Create `backend/tests/ml/test_rank_priors.py`:

```python
from __future__ import annotations

import pandas as pd

from app.ml.train.pipeline import _compute_rank_priors


def test_priors_from_fav_rank():
    df = pd.DataFrame({
        "race_id": [1, 1, 1, 2, 2, 2],
        "mkt_fav_rank": [1.0, 2.0, 99.0, 1.0, 2.0, 99.0],
        "finish_position": [1, 2, 3, 2, 1, 3],
    })
    p = _compute_rank_priors(df)
    assert p["1"] == 0.5   # fav won 1 of 2
    assert p["2"] == 0.5
    assert p["99"] == 0.0
    assert set(p) == {"1", "2", "3", "99"}
    assert p["3"] > 0      # unseen rank gets a small floor, not 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/ml/test_rank_priors.py -x -q`
Expected: FAIL ImportError.

- [ ] **Step 3: Implement in pipeline.py**

Add near the top of `backend/app/ml/train/pipeline.py`:

```python
import json
from pathlib import Path


def _compute_rank_priors(track_train) -> dict:
    """P(win | mkt_fav_rank) with a 0.01 floor so unseen ranks never zero out."""
    win = (track_train["finish_position"] == 1).astype(int)
    out = {}
    for k in (1, 2, 3, 99):
        mask = track_train["mkt_fav_rank"] == float(k)
        out[str(k)] = float(win[mask].mean()) if mask.sum() >= 20 else 0.0
    for k in out:
        if out[k] <= 0.0:
            out[k] = 0.01
    return out


def _save_rank_priors(track: str, priors: dict) -> None:
    path = _model_dir() / "rank_priors.json"
    data = {}
    if path.exists():
        with open(path) as f:
            data = json.load(f)
    data[track] = priors
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
```

Inside `run_train`, right after `track_train`/`track_val` are set (after the `len(track_train) < 50` guard), add:

```python
    # Persist market rank priors for the odds-free prediction path (service.py).
    try:
        _save_rank_priors(track, _compute_rank_priors(track_train))
    except Exception as exc:
        logger.warning("[%s] rank priors not saved: %s", track, exc)
```

- [ ] **Step 4: Run tests**

Run: `uv run python -m pytest tests/ml/test_rank_priors.py -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/ml/train/pipeline.py tests/ml/test_rank_priors.py
git commit -m "feat: rank-prior artifact computed at train time"
```

---

### Task 9: service.py odds-free prediction path

**Files:**
- Modify: `backend/app/ml/predict/service.py`
- Test: `backend/tests/ml/test_service_rank_prior.py`

**Interfaces:**
- Consumes: `models/rank_priors.json` (Task 8); `race_entries.market_fav_rank` (Task 1); new tables (feature lookups).
- Produces:
  - module-level `FEATURES` mirroring dataset v3 exactly (same 35 names).
  - `_load_rank_priors(track: str) -> dict` — `{"1":p,…,"99":p}`; uniform-ish fallback `{"1":0.30,"2":0.18,"3":0.12,"99":0.05}` when file missing.
  - `_rank_prior_probs(fav_ranks: list[float], track: str) -> np.ndarray` — normalized per race.
  - Predict flow: `mkt_fav_rank` per entry = `entry.market_fav_rank` if set, else derived from `morning_odds` rank if odds exist, else 99; cold-start anchor and `market_prob`/`edge_score` use `_rank_prior_probs` (inverse-odds anchor removed).

- [ ] **Step 1: Write failing test (pure helpers)**

Create `backend/tests/ml/test_service_rank_prior.py`:

```python
from __future__ import annotations

import numpy as np

from app.ml.predict.service import _rank_prior_probs, _load_rank_priors


def test_rank_prior_probs_normalized_and_ordered():
    probs = _rank_prior_probs([1.0, 2.0, 99.0, 99.0], "SEOUL")
    assert abs(probs.sum() - 1.0) < 1e-9
    assert probs[0] > probs[1] > probs[2]
    assert probs[2] == probs[3]


def test_load_rank_priors_fallback(tmp_path, monkeypatch):
    import app.ml.predict.service as svc
    monkeypatch.setattr(svc, "_RANK_PRIORS_PATH", tmp_path / "nope.json")
    p = _load_rank_priors("SEOUL")
    assert set(p) == {"1", "2", "3", "99"} and p["1"] > p["99"] > 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/ml/test_service_rank_prior.py -x -q`
Expected: FAIL ImportError.

- [ ] **Step 3: Implement helpers + rewire**

In `backend/app/ml/predict/service.py`:

(a) Add near the model-cache section:

```python
import json as _json

_RANK_PRIORS_PATH = Path(os.environ.get("MODEL_DIR", "models")) / "rank_priors.json"
_DEFAULT_PRIORS = {"1": 0.30, "2": 0.18, "3": 0.12, "99": 0.05}


def _load_rank_priors(track: str) -> dict:
    try:
        with open(_RANK_PRIORS_PATH) as f:
            return _json.load(f).get(track, dict(_DEFAULT_PRIORS))
    except Exception:
        return dict(_DEFAULT_PRIORS)


def _rank_prior_probs(fav_ranks, track: str):
    priors = _load_rank_priors(track)
    v = np.array([priors.get(str(int(r)), priors["99"]) for r in fav_ranks], dtype=float)
    s = v.sum()
    return v / s if s > 0 else np.ones(len(v)) / len(v)
```

(use the module's existing `Path`/`os`/`np` imports; add any missing).

(b) Sync `FEATURES` with dataset v3: copy the exact 35-name list from `dataset.py` (same order), updating the header comment to `v3, 2026-07-05`.

(c) In the per-horse row-building loop, add the new feature values:

```python
            "mkt_fav_rank": _fav_rank_for(entry, entries),
            "mkt_is_fav": 1 if _fav_rank_for(entry, entries) == 1.0 else 0,
            "days_since_start_train": st_info["days_since"],
            "start_train_ok_rate": st_info["ok_rate"],
            "start_train_count_90d": st_info["count_90d"],
            "workout_count_2w": wk2_count,
            "eiph_flag": eiph_flag,
            "weight_vs_top3avg": weight_vs_top3,
```

with these helpers added to the module (queries mirror dataset SQL semantics):

```python
def _fav_ranks_for_entries(entries) -> dict:
    """program_number -> mkt_fav_rank. Prefer crawled market_fav_rank; else
    derive from morning_odds ranks; else 99."""
    crawled = {e.program_number: e.market_fav_rank for e in entries
               if getattr(e, "market_fav_rank", None)}
    if crawled:
        return {e.program_number: float(crawled.get(e.program_number, 99)) for e in entries}
    with_odds = [(e.program_number, e.morning_odds) for e in entries if e.morning_odds]
    if not with_odds:
        return {e.program_number: 99.0 for e in entries}
    order = sorted(with_odds, key=lambda x: x[1])
    ranks = {pn: float(i + 1) for i, (pn, _o) in enumerate(order[:3])}
    return {e.program_number: ranks.get(e.program_number, 99.0) for e in entries}


async def _get_start_train_info(session, horse_id: int, race_date) -> dict:
    q = text("""
        SELECT (CAST(:rd AS date) - MAX(train_date)) AS days_since,
               AVG(CASE WHEN passed THEN 1.0 WHEN passed = false THEN 0.0 END) AS ok_rate,
               COUNT(*) FILTER (WHERE train_date >= CAST(:rd AS date) - INTERVAL '90 days') AS c90
        FROM start_training_records
        WHERE horse_id = :hid AND train_date < CAST(:rd AS date)
    """)
    row = (await session.execute(q, {"hid": horse_id, "rd": race_date})).first()
    if not row or row.days_since is None:
        return {"days_since": 999, "ok_rate": 0.5, "count_90d": 0}
    return {"days_since": int(row.days_since), "ok_rate": float(row.ok_rate or 0.5),
            "count_90d": int(row.c90 or 0)}


async def _get_workout_2w(session, race_id: int, horse_id: int) -> int:
    q = text("SELECT COUNT(*) FROM pre_race_workouts WHERE race_id=:rid AND horse_id=:hid")
    return int((await session.execute(q, {"rid": race_id, "hid": horse_id})).scalar() or 0)


async def _get_eiph_flag(session, horse_id: int, race_date) -> int:
    q = text("""
        SELECT 1 FROM health_records
        WHERE horse_id=:hid AND condition LIKE '%폐출혈%'
          AND record_date < CAST(:rd AS date)
          AND record_date >= CAST(:rd AS date) - INTERVAL '365 days'
        LIMIT 1""")
    return 1 if (await session.execute(q, {"hid": horse_id, "rd": race_date})).scalar() else 0


async def _get_weight_top3_delta(session, horse_id: int, race_date, today_weight) -> float:
    if today_weight is None:
        return 0.0
    q = text("""
        SELECT AVG(e.body_weight_kg)
        FROM race_entries e
        JOIN races r ON r.id = e.race_id
        JOIN race_results res ON res.race_id = e.race_id AND res.horse_id = e.horse_id
        WHERE e.horse_id=:hid AND r.race_date < CAST(:rd AS date)
          AND res.finish_position <= 3 AND e.body_weight_kg IS NOT NULL""")
    avg = (await session.execute(q, {"hid": horse_id, "rd": race_date})).scalar()
    return float(today_weight - avg) if avg else 0.0
```

Call `_fav_ranks_for_entries(entries)` once per race before the loop (`fav_map = …`; `_fav_rank_for(entry, entries)` above is shorthand for `fav_map[entry.program_number]` — use the map directly). Fetch the per-horse async helpers inside the existing per-entry gather/loop where health/workout lookups already happen.

(d) Replace the cold-start anchor + market prob (current lines ~893-912):

```python
    # Market prior from favorite ranks (odds are no longer published pre-race).
    fav_ranks = [fav_map[e.program_number] for e in entries]
    anchor = _rank_prior_probs(fav_ranks, race.track)

    blended = np.array([
        min(row["_n_starts"] / 3.0, 1.0) * probs[i]
        + (1 - min(row["_n_starts"] / 3.0, 1.0)) * anchor[i]
        for i, row in enumerate(rows)
    ])
    blended = blended / blended.sum()
    …
    mkt_probs = anchor  # rank-prior market probabilities (normalized)
```

Remove the `raw_odds/inv_odds` lines. `edge_score = win_prob − mkt_probs[i]` stays as-is.

- [ ] **Step 4: Run tests + live smoke**

Run: `uv run python -m pytest tests/ml/test_service_rank_prior.py -q`
Expected: pass.

Run (needs DB): `export $(grep -E '^DATABASE_URL=' .env | head -1 | xargs) && uv run python -c "import asyncio
from sqlalchemy import select
from app.db.session import async_session_factory
from app.db.models.crawl import Race
from app.ml.predict.service import predict_race
async def m():
    async with async_session_factory() as s:
        rid=(await s.execute(select(Race.id).where(Race.track=='SEOUL',Race.payouts.is_not(None)).order_by(Race.race_date.desc()).limit(1))).scalar()
        preds=await predict_race(s,rid)
        ps=[round(p.win_probability,3) for p in preds]
        print('probs',ps); print('edges',[round(p.edge_score,3) for p in preds][:4])
        assert len(set(ps))>2, 'no uniform collapse'
asyncio.run(m())"`
Expected: differentiated probabilities, no exception. (Model still v2 until Task 12 retrains — the FEATURES intersection guard in service keeps inference working.)

- [ ] **Step 5: Commit**

```bash
git add app/ml/predict/service.py tests/ml/test_service_rank_prior.py
git commit -m "feat: odds-free prediction path (rank-prior anchor/market prob, v3 features)"
```

---

### Task 10: Race-morning signal crawl + guards rename

**Files:**
- Create: `backend/scripts/crawl_raceday_signals.py`
- Modify: `backend/app/api/v1/predictions.py`, `backend/app/api/routers/reports.py`, `web/src/pages/InvestmentPage.tsx`

**Interfaces:**
- Consumes: `parse_main_top3`, `process_race`, Task 1 column.
- Produces: CLI `uv run python scripts/crawl_raceday_signals.py [--date YYYY-MM-DD]` filling `race_entries.market_fav_rank` + running the 4-tab crawl for that date. API field `signals_available` replaces `odds_available` semantics: true when any entry has `morning_odds` **or** `market_fav_rank`.

- [ ] **Step 1: Write the crawl script**

```python
"""Race-morning crawl: main-page top-3 favorites + the four detail tabs
for today's races. Run this before generating predictions on race day.

    DATABASE_URL=… uv run python scripts/crawl_raceday_signals.py
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.db.models.crawl import Race
from app.ml.crawl.crawl_detail_tabs import process_race, HEADERS, KRA
from app.ml.crawl.parsers.detail_tabs_parser import parse_main_top3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MAIN_PAGES = {"SEOUL": "/seoulMain.do", "BUSAN": "/busanMain.do", "JEJU": "/jejuMain.do"}
LABEL_TO_TRACK = {"서울": "SEOUL", "부경": "BUSAN", "제주": "JEJU"}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=datetime.date.fromisoformat,
                    default=datetime.date.today())
    args = ap.parse_args()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 1. top-3 favorites from the main pages (all three carry the full table)
        fav: dict = {}   # (track, race_number) -> [n1, n2, n3]
        for page in set(MAIN_PAGES.values()):
            try:
                r = await client.get(KRA + page, headers=HEADERS, timeout=25)
                for row in parse_main_top3(r.content.decode("euc-kr", errors="replace")):
                    key = (LABEL_TO_TRACK.get(row["track_label"]), row["race_number"])
                    fav[key] = row["fav_nums"]
            except Exception as exc:
                logger.warning("main page %s failed: %s", page, exc)
            await asyncio.sleep(0.4)
        logger.info("top-3 favorites parsed for %d races", len(fav))

        async with async_session_factory() as session:
            result = await session.execute(
                select(Race).options(selectinload(Race.entries))
                .where(Race.race_date == args.date)
                .order_by(Race.track, Race.race_number))
            races = list(result.scalars().all())
            logger.info("%d races on %s", len(races), args.date)

            filled = 0
            for race in races:
                nums = fav.get((race.track, race.race_number))
                if nums:
                    for e in race.entries:
                        if e.program_number in nums:
                            e.market_fav_rank = nums.index(e.program_number) + 1
                        else:
                            e.market_fav_rank = None
                    filled += 1
                counts = await process_race(session, client, race)
                logger.info("[%s r%s] fav=%s tabs=%s", race.track, race.race_number,
                            bool(nums), counts)
                await asyncio.sleep(0.4)
            await session.commit()
            logger.info("DONE fav_rank filled for %d/%d races", filled, len(races))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Smoke-test**

Run (any date with races in DB works for the tab part; fav part needs race day):
`export $(grep -E '^DATABASE_URL=' .env | head -1 | xargs) && uv run python scripts/crawl_raceday_signals.py --date 2026-07-05`
Expected: log `DONE fav_rank filled for N/M races` (N may be 0 on non-race-days; tab counts > 0).

- [ ] **Step 3: Rename guard to signals_available**

In `backend/app/api/v1/predictions.py` replace the odds check:

```python
    entry_rows = (
        await db.execute(
            select(RaceEntry.morning_odds, RaceEntry.market_fav_rank)
            .where(RaceEntry.race_id == race_id)
        )
    ).all()
    signals_available = any(o is not None or fr is not None for o, fr in entry_rows)

    return PredictionListResponse(items=predictions, odds_available=signals_available)
```

(keep the response field name `odds_available` for API compatibility, but its docstring comment becomes "any market signal (odds or crawled fav rank) present".)

In `backend/app/api/routers/reports.py` update the same computation:

```python
            odds_available = any(
                (e.morning_odds is not None) or (getattr(e, "market_fav_rank", None) is not None)
                for e in race.entries
            )
```

In `web/src/pages/InvestmentPage.tsx` change the warning copy:

```tsx
              배당/인기 신호가 아직 없어 예측이 신뢰불가입니다. 경주 당일 아침
              crawl_raceday_signals 실행 후 다시 확인하세요.
```

and the badge label `배당 미입력` → `당일신호 미입력`.

- [ ] **Step 4: Build + test**

Run: `cd ../web && npm run build 2>&1 | grep -E "transformed|error" | head -3 && cd ../backend`
Expected: `✓ … modules transformed.`
Run: `uv run python -m pytest tests/ml/test_detail_tabs_parser.py -q` (unchanged, still green).

- [ ] **Step 5: Commit**

```bash
git add scripts/crawl_raceday_signals.py app/api/v1/predictions.py app/api/routers/reports.py ../web/src/pages/InvestmentPage.tsx
git commit -m "feat: race-morning signal crawl + market-signal guard"
```

---

### Task 11: Group ablation gate + backtest rank-prior mode

**Files:**
- Create: `backend/scripts/ablation_v3_groups.py`
- Modify: `backend/scripts/backtest_ev.py`

**Interfaces:**
- Consumes: FEATURES v3 (Task 7), `models/rank_priors.json` (Task 8).
- Produces: `ablation_v3_groups.py` printing per-group verdicts (KEEP/DROP); `backtest_ev.py --rank-prior` flag that gates edges on rank-prior market probs instead of 1/odds.

- [ ] **Step 1: Write the ablation script**

```python
"""FEATURES v3 group ablation. Baseline = v3 minus all new groups (odds-free
core). Each group is added on top of baseline; a group KEEPs when the SEOUL
ensemble val_log_loss improves by ≥0.002 (same gate as earlier experiments).

    DATABASE_URL=… uv run python -m scripts.ablation_v3_groups
"""
from __future__ import annotations

import os
import sys

import numpy as np

GROUPS = {
    "G1_market":      ["mkt_fav_rank", "mkt_is_fav"],
    "G2_start_train": ["days_since_start_train", "start_train_ok_rate", "start_train_count_90d"],
    "G3_weight":      ["body_weight_kg", "body_weight_delta_kg", "weight_vs_top3avg"],
    "G4_workout":     ["workout_count_2w"],
    "G5_eiph":        ["eiph_flag"],
}


def _eval(tr, va, feats, target):
    from app.ml.train.models.lgbm_binary import train_lgbm
    from app.ml.train.models.catboost_binary import train_catboost
    from app.ml.train.models.ensemble import build_ensemble, _race_log_loss
    l = train_lgbm(tr, va, feats, target)
    c = train_catboost(tr, va, feats, target)
    e = build_ensemble([l, c], va, feats, target)
    return _race_log_loss(e, va, feats, target)


def main():
    db = os.environ.get("DATABASE_URL", "")
    if not db:
        print("DATABASE_URL not set"); sys.exit(1)
    from app.ml.train.dataset import load_dataset_pg, FEATURES

    tr_all, va_all, _t, feats, target = load_dataset_pg(db)
    tr = tr_all[tr_all.track == "SEOUL"].copy()
    va = va_all[va_all.track == "SEOUL"].copy()
    all_new = [f for g in GROUPS.values() for f in g]
    base = [f for f in FEATURES if f not in all_new]

    uniform = float(np.log(va.groupby("race_id").size()).mean())
    print(f"SEOUL val {va['race_id'].nunique()} races | uniform {uniform:.4f}")
    b = _eval(tr, va, base, target)
    print(f"baseline (odds-free core, {len(base)}f): {b:.4f}\n")

    keep = []
    for name, cols in GROUPS.items():
        ll = _eval(tr, va, base + cols, target)
        verdict = "KEEP ✅" if ll < b - 0.002 else "DROP ❌"
        print(f"  {name:15s} {ll:.4f}  (Δ {ll - b:+.4f})  {verdict}")
        if ll < b - 0.002:
            keep.append(name)

    kept_cols = [f for g in keep for f in GROUPS[g]]
    if kept_cols:
        full = _eval(tr, va, base + kept_cols, target)
        print(f"\ncombined KEEP groups ({keep}): {full:.4f}")
    print("\nEdit dataset.py FEATURES to comment out DROP groups, then re-sync service.py FEATURES.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add --rank-prior to backtest_ev.py**

Add flag and market-prob override. In `main()`:

```python
    ap.add_argument("--rank-prior", action="store_true",
                    help="gate edges on rank-prior market probs (odds-free strategy)")
```

Add module helper (after `_market_probs`):

```python
def _rank_prior_market(odds: np.ndarray, track: str) -> np.ndarray:
    """Historical backtest of the odds-free strategy: fav ranks derived from
    odds (what the crawl would have shown), probabilities from rank priors."""
    import json, os
    with open(os.path.join("models", "rank_priors.json")) as f:
        priors = json.load(f)[track]
    order = np.argsort(odds)
    ranks = np.full(len(odds), 99.0)
    for i, idx in enumerate(order[:3]):
        ranks[idx] = float(i + 1)
    v = np.array([priors.get(str(int(r)), priors["99"]) for r in ranks])
    return v / v.sum()
```

In `run()` (and `run_quinella_gate()`), where `mkt = _market_probs(...)` is computed, switch on the flag:

```python
        if RANK_PRIOR_MODE:
            mkt = _rank_prior_market(g["morning_odds"].values.astype(float), track)
        else:
            mkt = _market_probs(g["morning_odds"].values)
```

with module global `RANK_PRIOR_MODE = False` set from `args.rank_prior` in `main()` before dispatch.

- [ ] **Step 3: Sanity run (pre-backfill)**

Run: `export $(grep -E '^DATABASE_URL=' .env | head -1 | xargs) && uv run python -m scripts.ablation_v3_groups 2>/dev/null | tail -12`
Expected (pre-backfill): G1 KEEP (data already present via odds derivation); G2/G4 likely DROP (tables still sparse) — this run is the harness check, the decisive run happens after backfill in Task 12.

- [ ] **Step 4: Commit**

```bash
git add scripts/ablation_v3_groups.py scripts/backtest_ev.py
git commit -m "feat: v3 group ablation gate + rank-prior backtest mode"
```

---

### Task 12: Operations — backfill, gate, retrain, re-validate

**Files:**
- Modify: `backend/app/ml/train/dataset.py` (prune DROP groups), `backend/app/ml/predict/service.py` (re-sync FEATURES), `web/src/pages/InvestmentPage.tsx` (min_edge default if re-tuned)

This task is sequential operations; each step has a hard gate.

- [ ] **Step 1: Run the full backfill (background, ~8–10 h)**

Run: `export $(grep -E '^DATABASE_URL=' .env | head -1 | xargs) && nohup uv run python scripts/backfill_detail_tabs.py > backfill_detail_tabs.log 2>&1 &`
Monitor: `tail -3 backfill_detail_tabs.log` — expect `progress N/M` lines. Resumable: rerun the same command after any crash; it skips done races.
Gate: log ends with `DONE processed=… totals=…`.

- [ ] **Step 2: Integrity gate**

Run: `uv run python scripts/verify_data_integrity.py`
Gate: `✓ 합격` AND sections [11]/[12] show ≥40 % coverage for 2024–2026. If coverage is low, investigate parse failures in `backfill_detail_tabs.log` before proceeding.

- [ ] **Step 3: Decisive ablation**

Run: `uv run python -m scripts.ablation_v3_groups 2>/dev/null | tail -12`
Action: in `dataset.py` FEATURES, comment out every DROP group's lines (keep the comment `# DROPPED by ablation 2026-07-XX: …`), and mirror the final list into `service.py` FEATURES. Re-run `uv run python -m pytest tests/ml/test_dataset_features_v3.py -q` — update the feature-presence test to assert only KEEP groups.

- [ ] **Step 4: Retrain all tracks**

Run: `uv run python -c "import os;from app.ml.train.pipeline import run_train
for t in ['SEOUL','BUSAN','JEJU']: print(run_train(t, os.environ['DATABASE_URL']))"`
Gate: each track prints `val_log_loss` ≤ its previous champion (promotion handles this); SEOUL val_log_loss target ≤ 1.92. `models/rank_priors.json` exists with all three tracks.

- [ ] **Step 5: Re-validate the edge strategy odds-free**

Run: `uv run python -m scripts.backtest_ev --rank-prior --since 2026-01-02 2>/dev/null`
Read the SEOUL block: pick the smallest `min_edge` whose SEOUL quinella ROI > 0 with ≥100 races. If it differs from 0.05, update `EDGE_PRESETS` default (`useState(0.05)`) in `web/src/pages/InvestmentPage.tsx` and note the new threshold in the UI copy. If **no** threshold is profitable, set the investment tab banner copy to state the strategy is under re-validation and file the finding in memory — do not advertise an unvalidated strategy.

- [ ] **Step 6: End-to-end race-morning rehearsal**

On the next race day (or with `--date` of the most recent race day):
`uv run python scripts/crawl_raceday_signals.py && uv run python -c "…predict_race smoke from Task 9 Step 4…"`
Gate: predictions differentiated; investment tab shows recommendations without the 당일신호 warning.

- [ ] **Step 7: Full test suite + commit + memory**

Run: `uv run python -m pytest -q 2>&1 | tail -2`
Gate: failures ≤ baseline (39 failed / 7 errors).

```bash
git add app/ml/train/dataset.py app/ml/predict/service.py ../web/src/pages/InvestmentPage.tsx
git commit -m "feat: finalize odds-free FEATURES v3 after backfill ablation + retrain"
git push
```

Update memory files: `ev_backtest_results.md` (new thresholds), `project_roi_improvement.md` (odds-free path live), `MEMORY.md` index lines.

---

## Self-Review

**Spec coverage:** crawler+parsers (T2–4), schema (T1), backfill+integrity (T5–6, T12), FEATURES v3 groups G1–G5 (T7), rank priors + service path (T8–9), race-morning crawl + guard rename (T10), ablation gates + backtest re-validation + UI defaults (T11–12), fixtures/tests throughout. StewardsReport correctly absent (Phase 2). ✓

**Placeholder scan:** every code step contains full code; no TBD/similar-to. The one intentional judgment point (Task 12 Step 3/5 outcomes) is an operational gate, not a placeholder. ✓

**Type consistency:** parser keys (`program_number/horse_name/train_date/rider/remark/passed/equipment`, `today_weight/weight_delta/top3_avg`, `sessions[day_label/rider/count]`, `medical[record_date/condition]/eiph`, `track_label/race_number/fav_nums`) match consumers in `process_race` and `crawl_raceday_signals`; upsert signatures match models; FEATURES v3 names identical across dataset/service/ablation/tests; `_rank_prior_probs(fav_ranks, track)` signature consistent between service and tests. ✓
