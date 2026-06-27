# 출마표 크롤러 (Pre-Race Entry Crawler)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a crawler that fetches tomorrow's race entries (출마표) from the KRA website and stores them so the existing predict API can serve predictions before a race happens.

**Architecture:** Three tasks. Task 1 extends the existing `KRALiveParser.parse_upcoming_race` to add `carry_weight` and `morning_odds`, then creates `crawl_entries.py`. Task 2 wires it into an admin API endpoint. Task 3 adds a CLI helper.

The KRA website has two relevant endpoints: `ScoretableScoreList.do` for the race schedule (list of race numbers per date) and `ChulmaDetailInfo.do` (or `chulmaDetailInfoChulmapyo.do`) for per-race entry data. `parse_upcoming_race` already parses the entry page. We extend it and build the crawler on top.

**Tech Stack:** Python 3.9+, httpx (async HTTP), BeautifulSoup4, async SQLAlchemy, FastAPI, pytest

## Global Constraints

- Python 3.9+ — use `from __future__ import annotations` at top of any file using `X | Y` or `list[...]` annotations, OR use `Optional[X]` and `List[...]` from `typing`
- No new pip packages (httpx, BeautifulSoup4, sqlalchemy already in `pyproject.toml`)
- For upcoming races: insert Race + RaceEntry only — do NOT insert RaceResult (no finish position yet)
- Idempotent: re-running for the same date must not duplicate rows (use existing upsert helpers from `app.ml.crawl.upsert`)
- KRA website requests: always `User-Agent: "Mozilla/5.0"`, decode as `euc-kr`, `timeout: 15s`
- `TRACK_MEET_MAP = {"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}` — defined in `pipeline.py`, repeat locally in `crawl_entries.py`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/ml/crawl/parsers/kra_live_parser.py` | Modify | Extend `parse_upcoming_race` to add `carry_weight` + `morning_odds` |
| `backend/app/ml/crawl/crawl_entries.py` | Create | Fetch + store upcoming race entries for a target date |
| `backend/app/api/v1/admin.py` | Modify | Add `POST /admin/crawl/entries` endpoint |
| `backend/tests/crawl/test_kra_entry_parser.py` | Create | Parser extension tests |
| `backend/tests/api/test_admin_entries.py` | Create | Admin endpoint test |
| `backend/app/ml/crawl/run_entry_crawl.py` | Create | CLI runner for cron/manual use |
| `backend/tests/crawl/test_crawl_entries_unit.py` | Create | Unit test for crawler with mocked HTTP |

---

## Task 1: Extend Parser + Build Crawler Module

**Files:**
- Modify: `backend/app/ml/crawl/parsers/kra_live_parser.py`
- Create: `backend/app/ml/crawl/crawl_entries.py`
- Create: `backend/tests/crawl/test_kra_entry_parser.py`
- Create: `backend/tests/crawl/test_crawl_entries_unit.py`

**Interfaces:**
- `KRALiveParser.parse_upcoming_race(html: str) -> List[Dict[str, Any]]`
  - Already exists at line 307 of `kra_live_parser.py` — **extend in place**, do not rewrite
  - Currently returns `[{"horse_no": int, "horse_name": str, "sex": str, "age": int, "weight": float, "jockey": str, "trainer": str, "odds_win": 1.0, "odds_place": 1.0}]`
  - After extension must return these additional keys: `"carry_weight": float`, `"morning_odds": Optional[float]`
  - Must also strip delta suffixes from body weight: `"480(-2)"` → `480.0` (current code does NOT do this)
  - Remove the hardcoded `"odds_win": 1.0` and `"odds_place": 1.0` keys (misleading); replace with `"morning_odds": None` when no odds column present

- `async crawl_entries(target_date: datetime.date, tracks: Optional[List[str]], session: Optional[AsyncSession]) -> Dict[str, Any]`
  - Returns: `{"races_upserted": int, "entries_upserted": int, "errors": List[str]}`

**Context — existing code to understand:**

`kra_live_parser.py` line 307 has `parse_upcoming_race` which parses `div.tableType2 > tbody > tr` rows:
- col[0] = horse_no (마번) — digits only; non-digit rows are skipped
- col[1] = horse_name (마명)
- col[3] = sex (성별) — `"수"`, `"암"`, `"거"` kept as-is; already has cancel filtering for `"취소"` in horse_name/jockey
- col[4] = age (마령) — digits
- col[6] = body weight (마체중) — needs delta stripped: `"490(+2)"` → `490.0`
- col[8] = jockey (기수)
- col[9] = trainer (조교사)

The carry weight column (`부담중량`) is typically col[5] on the 출마표 page. The morning odds column (`단승`) may or may not exist; check if headers include `"단승"` to find its index dynamically.

The KRA entry detail endpoint for upcoming races:
```
POST https://race.kra.co.kr/chulmaList/ChulmaDetailInfoPrint.do
data: {"meet": "1", "rcDate": "20260628", "rcNo": "1"}
```
Alternative URL to try if above returns empty: `ChulmaDetailInfo.do` with same params.

Race schedule (list of upcoming race numbers) comes from:
```
POST https://race.kra.co.kr/raceScore/ScoretableScoreList.do
data: {"Act": "04", "Sub": "1", "meet": "1", "rcDate": "20260628"}
```
Then `KRALiveParser.parse_chulma_list(html)` returns `[{"date": "20260628", "track": ..., "races": [1,2,3,...]}]`.

Race metadata (distance, surface, track_condition, weather) comes from the same entry page or from the first page in the schedule.

---

- [ ] **Step 1: Write failing parser extension tests**

Create `backend/tests/crawl/test_kra_entry_parser.py`:

```python
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser

# HTML mimicking ChulmaDetailInfoPrint.do response structure
# div.tableType2 > tbody structure; columns: 마번, 마명, 색모, 성별, 마령, 부담중량, 마체중, 기수코드, 기수, 조교사
SAMPLE_UPCOMING_HTML = """
<html><body>
<div class="tableType2">
<table>
  <thead>
    <tr>
      <th>마번</th><th>마명</th><th>색모</th><th>성별</th><th>마령</th>
      <th>부담중량</th><th>마체중</th><th>기수코드</th><th>기수</th><th>조교사</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>1</td><td>천하무적</td><td>갈</td><td>수</td><td>4</td>
      <td>57.0</td><td>490</td><td>K001</td><td>김철수</td><td>이영희</td>
    </tr>
    <tr>
      <td>2</td><td>날개없는천사</td><td>흑</td><td>암</td><td>3</td>
      <td>54.0</td><td>480(-2)</td><td>K002</td><td>이순신</td><td>강감찬</td>
    </tr>
    <tr>
      <td>취소</td><td>취소말</td><td></td><td>수</td><td>4</td>
      <td>57.0</td><td>500</td><td></td><td>취소기수</td><td>취소조교사</td>
    </tr>
  </tbody>
</table>
</div>
</body></html>
"""

SAMPLE_UPCOMING_WITH_ODDS_HTML = """
<html><body>
<div class="tableType2">
<table>
  <thead>
    <tr>
      <th>마번</th><th>마명</th><th>색모</th><th>성별</th><th>마령</th>
      <th>부담중량</th><th>마체중</th><th>기수코드</th><th>기수</th><th>조교사</th><th>단승</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>1</td><td>천하무적</td><td>갈</td><td>수</td><td>4</td>
      <td>57.0</td><td>490</td><td>K001</td><td>김철수</td><td>이영희</td><td>3.5</td>
    </tr>
  </tbody>
</table>
</div>
</body></html>
"""

EMPTY_HTML = "<html><body><p>데이터 없음</p></body></html>"


def test_parse_upcoming_returns_two_non_cancelled_horses():
    """Non-digit 마번 (취소) rows are skipped."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert len(entries) == 2


def test_parse_upcoming_horse_no():
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert entries[0]["horse_no"] == 1
    assert entries[1]["horse_no"] == 2


def test_parse_upcoming_horse_name():
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert entries[0]["horse_name"] == "천하무적"


def test_parse_upcoming_carry_weight():
    """carry_weight field is present and parsed from 부담중량 column (col[5])."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert "carry_weight" in entries[0]
    assert abs(entries[0]["carry_weight"] - 57.0) < 0.01


def test_parse_upcoming_body_weight_strips_delta():
    """'480(-2)' in col[6] should yield weight=480.0 (delta stripped)."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert abs(entries[1]["weight"] - 480.0) < 0.01


def test_parse_upcoming_jockey_and_trainer():
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert entries[0]["jockey"] == "김철수"
    assert entries[0]["trainer"] == "이영희"


def test_parse_upcoming_morning_odds_none_when_column_absent():
    """When page has no 단승 column, morning_odds is None (not 1.0)."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_HTML)
    assert "morning_odds" in entries[0]
    assert entries[0]["morning_odds"] is None


def test_parse_upcoming_morning_odds_parsed_when_column_present():
    """When 단승 column exists, morning_odds is parsed as float."""
    entries = KRALiveParser.parse_upcoming_race(SAMPLE_UPCOMING_WITH_ODDS_HTML)
    assert abs(entries[0]["morning_odds"] - 3.5) < 0.01


def test_parse_upcoming_empty_page_returns_empty_list():
    entries = KRALiveParser.parse_upcoming_race(EMPTY_HTML)
    assert entries == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/crawl/test_kra_entry_parser.py -v 2>&1 | head -30
```

Expected: `test_parse_upcoming_carry_weight` fails (no `carry_weight` key), `test_parse_upcoming_body_weight_strips_delta` fails (delta not stripped), `test_parse_upcoming_morning_odds_none_when_column_absent` fails (key missing or equals 1.0).

Also run existing live parser tests to capture baseline:
```bash
uv run pytest tests/crawl/test_kra_live_parser.py -v
```

Expected: 7 passed (baseline to protect against regressions).

- [ ] **Step 3: Extend `parse_upcoming_race` in `kra_live_parser.py`**

Read lines 306–368 of `kra_live_parser.py` (the `parse_upcoming_race` method) and update it.

Key changes to make **inside the existing method** (do not change class structure):

1. **Find carry_weight column** — it's likely col[5] (`부담중량`). Add `carry_weight` parsing from col[5]:
   ```python
   carry_str = cols[5].get_text(strip=True).replace('*', '')
   carry_weight = float(carry_str) if carry_str.replace('.', '', 1).isdigit() else 0.0
   ```

2. **Strip delta from body weight** — col[6] currently goes directly to `float(weight_str)` which fails for `"480(-2)"`. Fix:
   ```python
   weight_str = cols[6].get_text(strip=True)
   import re as _re
   bw_match = _re.match(r'(\d+(?:\.\d+)?)', weight_str)
   weight = float(bw_match.group(1)) if bw_match else 0.0
   ```

3. **Find morning_odds column dynamically** — look for `단승` in the table's `<th>` headers to get the column index, then parse that column. If not found, use `None`.
   ```python
   # Find 단승 column index from <th> headers in the same table
   header_row = table.find('tr')  # where 'table' is the located table element
   if header_row:
       headers = [th.get_text(strip=True) for th in header_row.find_all('th')]
       odds_col_idx = headers.index('단승') if '단승' in headers else -1
   else:
       odds_col_idx = -1
   
   morning_odds = None
   if odds_col_idx >= 0 and len(cols) > odds_col_idx:
       odds_str = cols[odds_col_idx].get_text(strip=True)
       if odds_str.replace('.', '', 1).isdigit():
           morning_odds = float(odds_str)
   ```

4. **Remove `odds_win: 1.0` and `odds_place: 1.0`** from the returned dict. Replace with `morning_odds: morning_odds`.

5. **Add `carry_weight` to the returned dict.**

The updated dict for each entry should be:
```python
{
    "horse_no": horse_no,
    "horse_name": horse_name,
    "sex": sex,
    "age": age,
    "weight": weight,
    "carry_weight": carry_weight,
    "jockey": jockey,
    "trainer": trainer,
    "morning_odds": morning_odds,
}
```

Note: the `table` variable inside `parse_upcoming_race` currently refers to `soup.find('div', class_='tableType2')`. For dynamic header detection, get the `<table>` element inside it: `actual_table = table.find('table')`.

- [ ] **Step 4: Run parser tests**

```bash
cd backend
uv run pytest tests/crawl/test_kra_entry_parser.py -v
uv run pytest tests/crawl/test_kra_live_parser.py -v
```

Expected: 9 new tests passed, 7 existing tests still passed.

- [ ] **Step 5: Write crawler unit test**

Create `backend/tests/crawl/test_crawl_entries_unit.py`:

```python
import pytest
import datetime
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_crawl_entries_upserts_races_and_entries():
    """crawl_entries stores race and entry rows given mocked HTTP."""
    from app.ml.crawl.crawl_entries import crawl_entries

    fake_races = [1, 2]
    fake_entries = [
        {
            "horse_no": 1,
            "horse_name": "천하무적",
            "sex": "수",
            "age": 4,
            "jockey": "김철수",
            "trainer": "이영희",
            "carry_weight": 57.0,
            "weight": 490.0,
            "morning_odds": 3.5,
        }
    ]
    fake_meta = {"distance_m": 1200, "surface": "Dirt", "track_condition": "건조"}

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.ml.crawl.crawl_entries._fetch_race_list", new=AsyncMock(return_value=fake_races)), \
         patch("app.ml.crawl.crawl_entries._fetch_race_entries", new=AsyncMock(return_value=fake_entries)), \
         patch("app.ml.crawl.crawl_entries._fetch_race_meta", new=AsyncMock(return_value=fake_meta)), \
         patch("app.ml.crawl.crawl_entries.upsert_horse", new=AsyncMock(return_value=1)), \
         patch("app.ml.crawl.crawl_entries.upsert_jockey", new=AsyncMock(return_value=1)), \
         patch("app.ml.crawl.crawl_entries.upsert_trainer", new=AsyncMock(return_value=1)), \
         patch("app.ml.crawl.crawl_entries.upsert_race", new=AsyncMock(return_value=1)), \
         patch("app.ml.crawl.crawl_entries.upsert_race_entry", new=AsyncMock()):

        result = await crawl_entries(
            target_date=datetime.date(2026, 6, 28),
            tracks=["SEOUL"],
            session=mock_session,
        )

    assert result["races_upserted"] == 2
    assert result["entries_upserted"] == 2
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_crawl_entries_empty_race_list_returns_zeros():
    """When no races found for a date, return zero counts and no errors."""
    from app.ml.crawl.crawl_entries import crawl_entries

    mock_session = AsyncMock()
    with patch("app.ml.crawl.crawl_entries._fetch_race_list", new=AsyncMock(return_value=[])):
        result = await crawl_entries(
            target_date=datetime.date(2026, 6, 28),
            tracks=["SEOUL"],
            session=mock_session,
        )

    assert result["races_upserted"] == 0
    assert result["entries_upserted"] == 0
    assert result["errors"] == []
```

- [ ] **Step 6: Run crawler tests to verify they fail**

```bash
cd backend
uv run pytest tests/crawl/test_crawl_entries_unit.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.ml.crawl.crawl_entries'`

- [ ] **Step 7: Create `crawl_entries.py`**

Create `backend/app/ml/crawl/crawl_entries.py`:

```python
"""
출마표 (Pre-Race Entry) Crawler

Fetches upcoming race entries from the KRA website and upserts Race + RaceEntry
rows so the prediction API can serve predictions before races run.

Usage:
    from app.ml.crawl.crawl_entries import crawl_entries
    result = await crawl_entries(datetime.date(2026, 6, 28), ["SEOUL"])
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from app.ml.crawl.upsert import (
    upsert_horse, upsert_jockey, upsert_trainer,
    upsert_race, upsert_race_entry,
)

logger = logging.getLogger(__name__)

TRACK_MEET_MAP = {"SEOUL": "1", "JEJU": "2", "BUSAN": "3"}
KRA_BASE = "https://race.kra.co.kr"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}


async def _fetch_race_list(client: httpx.AsyncClient, rc_date: str, meet: str) -> List[int]:
    """Return list of race numbers for the given date and meet code."""
    try:
        res = await client.post(
            f"{KRA_BASE}/raceScore/ScoretableScoreList.do",
            headers=HEADERS,
            data={"Act": "04", "Sub": "1", "meet": meet, "rcDate": rc_date},
            timeout=15.0,
        )
        html = res.content.decode("euc-kr", errors="replace")
        schedule = KRALiveParser.parse_chulma_list(html)
        for day in schedule:
            if day.get("date") == rc_date:
                return day.get("races", [])
        return []
    except Exception as exc:
        logger.warning("_fetch_race_list failed %s meet=%s: %s", rc_date, meet, exc)
        return []


async def _fetch_race_entries(
    client: httpx.AsyncClient, rc_date: str, meet: str, rc_no: int
) -> List[Dict]:
    """Fetch and parse entry list for one upcoming race."""
    for path in [
        "/chulmaList/ChulmaDetailInfoPrint.do",
        "/chulmaList/ChulmaDetailInfo.do",
    ]:
        try:
            res = await client.post(
                f"{KRA_BASE}{path}",
                headers=HEADERS,
                data={"meet": meet, "rcDate": rc_date, "rcNo": str(rc_no)},
                timeout=15.0,
            )
            html = res.content.decode("euc-kr", errors="replace")
            entries = KRALiveParser.parse_upcoming_race(html)
            if entries:
                return entries
        except Exception as exc:
            logger.warning("_fetch_race_entries %s %s race %s: %s", path, rc_date, rc_no, exc)
    return []


async def _fetch_race_meta(
    client: httpx.AsyncClient, rc_date: str, meet: str, rc_no: int
) -> Dict:
    """Fetch race metadata (distance, surface, weather) from the detail page."""
    try:
        res = await client.post(
            f"{KRA_BASE}/raceScore/ScoretableDetailList.do",
            headers=HEADERS,
            data={"meet": meet, "realRcDate": rc_date, "realRcNo": str(rc_no)},
            timeout=15.0,
        )
        html = res.content.decode("euc-kr", errors="replace")
        parsed = KRALiveParser.parse_race_detail(html)
        return parsed.get("meta", {})
    except Exception as exc:
        logger.warning("_fetch_race_meta failed %s race %s: %s", rc_date, rc_no, exc)
        return {}


async def crawl_entries(
    target_date: datetime.date,
    tracks: Optional[List[str]] = None,
    session: Optional[AsyncSession] = None,
) -> Dict:
    """
    Fetch and store upcoming race entries for target_date.

    Parameters
    ----------
    target_date : the race day to fetch entries for
    tracks      : e.g. ["SEOUL", "BUSAN"]; defaults to all three tracks
    session     : optional AsyncSession; if None, creates its own

    Returns
    -------
    {"races_upserted": int, "entries_upserted": int, "errors": List[str]}
    """
    if tracks is None:
        tracks = ["SEOUL", "BUSAN", "JEJU"]

    rc_date = target_date.strftime("%Y%m%d")
    races_upserted = 0
    entries_upserted = 0
    errors: List[str] = []

    async def _run(sess: AsyncSession) -> None:
        nonlocal races_upserted, entries_upserted

        async with httpx.AsyncClient() as client:
            for track in tracks:
                meet = TRACK_MEET_MAP.get(track, "1")
                race_numbers = await _fetch_race_list(client, rc_date, meet)
                if not race_numbers:
                    logger.info("No races found for %s on %s", track, rc_date)
                    continue

                logger.info("Found %d races for %s on %s", len(race_numbers), track, rc_date)

                for rc_no in race_numbers:
                    await asyncio.sleep(0.5)

                    meta = await _fetch_race_meta(client, rc_date, meet, rc_no)
                    entries = await _fetch_race_entries(client, rc_date, meet, rc_no)

                    if not entries:
                        errors.append(f"{track} race {rc_no}: no entries returned")
                        continue

                    race_id = await upsert_race(
                        sess,
                        track=track,
                        race_date=target_date,
                        race_number=rc_no,
                        race_name=meta.get("race_name", f"{rc_no}경주"),
                        distance_m=meta.get("distance_m", 1200),
                        surface=meta.get("surface", "Dirt"),
                        track_condition=meta.get("track_condition"),
                        weather=meta.get("weather"),
                        humidity=meta.get("humidity"),
                        grade=meta.get("grade"),
                        field_size=len(entries),
                    )
                    races_upserted += 1

                    for e in entries:
                        # parse_upcoming_race returns horse_no as program_number equivalent
                        horse_id = await upsert_horse(
                            sess,
                            name=e["horse_name"],
                            sex=e.get("sex", "M"),
                            age=e.get("age"),
                        )
                        jockey_id = (
                            await upsert_jockey(sess, name=e["jockey"])
                            if e.get("jockey") else None
                        )
                        trainer_id = (
                            await upsert_trainer(sess, name=e["trainer"])
                            if e.get("trainer") else None
                        )

                        await upsert_race_entry(
                            sess,
                            race_id=race_id,
                            horse_id=horse_id,
                            program_number=e["horse_no"],
                            jockey_id=jockey_id,
                            trainer_id=trainer_id,
                            carry_weight_kg=e.get("carry_weight"),
                            body_weight_kg=e.get("weight"),
                            morning_odds=e.get("morning_odds"),
                        )
                        entries_upserted += 1

                    await sess.commit()
                    logger.info(
                        "Upserted %s/%s with %d entries", track, rc_no, len(entries)
                    )

    if session is not None:
        await _run(session)
    else:
        async with async_session_factory() as sess:
            await _run(sess)

    return {
        "races_upserted": races_upserted,
        "entries_upserted": entries_upserted,
        "errors": errors,
    }
```

- [ ] **Step 8: Run all parser + crawler unit tests**

```bash
cd backend
uv run pytest tests/crawl/test_kra_entry_parser.py tests/crawl/test_crawl_entries_unit.py -v
```

Expected: 9 + 2 = 11 new tests passed.

- [ ] **Step 9: Run full non-Docker test suite**

```bash
cd backend
uv run pytest tests/ -q --ignore=tests/db --ignore=tests/ml/test_dataset_pg.py
```

Expected: all prior tests pass + 11 new tests.

- [ ] **Step 10: Commit**

```bash
git add backend/app/ml/crawl/parsers/kra_live_parser.py \
        backend/app/ml/crawl/crawl_entries.py \
        backend/tests/crawl/test_kra_entry_parser.py \
        backend/tests/crawl/test_crawl_entries_unit.py
git commit -m "feat: extend parse_upcoming_race and add 출마표 entry crawler"
```

---

## Task 2: Admin API Endpoint — POST /admin/crawl/entries

**Files:**
- Modify: `backend/app/api/v1/admin.py`
- Create: `backend/tests/api/test_admin_entries.py`

**Interfaces:**
- `POST /api/v1/admin/crawl/entries`
  - Request body: `{"date": "2026-06-28", "tracks": ["SEOUL"]}` (`tracks` optional, defaults to all three)
  - Response: `{"ok": true, "date": "2026-06-28", "tracks": ["SEOUL"], "message": "Entry crawl started in background"}`
  - Runs the crawl as an `asyncio.create_task` background task (same pattern as existing `retry_crawl` at line 168)

**Context — existing admin.py patterns:**

`admin.py` already has:
```python
import asyncio
import datetime
from pydantic import BaseModel
router = APIRouter(prefix="/admin", tags=["admin"])
```
The `RetryRequest` model and `retry_crawl` endpoint (line 168) show the exact pattern to follow: local import of the crawler inside the endpoint, `asyncio.create_task(_run())`, immediate `return {"ok": True, ...}`.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/api/test_admin_entries.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_crawl_entries_endpoint_returns_ok():
    """POST /admin/crawl/entries accepts request and returns ok immediately."""
    with patch(
        "app.api.v1.admin.crawl_entries",
        new=AsyncMock(return_value={"races_upserted": 3, "entries_upserted": 45, "errors": []}),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/admin/crawl/entries",
                json={"date": "2026-06-28", "tracks": ["SEOUL"]},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["date"] == "2026-06-28"
    assert body["tracks"] == ["SEOUL"]


@pytest.mark.asyncio
async def test_crawl_entries_defaults_all_tracks():
    """When tracks omitted, response contains all three tracks."""
    with patch(
        "app.api.v1.admin.crawl_entries",
        new=AsyncMock(return_value={"races_upserted": 0, "entries_upserted": 0, "errors": []}),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/admin/crawl/entries",
                json={"date": "2026-06-28"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["tracks"]) == {"SEOUL", "BUSAN", "JEJU"}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/api/test_admin_entries.py -v 2>&1 | head -20
```

Expected: `404 Not Found` (endpoint not yet added).

- [ ] **Step 3: Add request model and endpoint to `admin.py`**

After the existing `RetryRequest` class, add:

```python
class CrawlEntriesRequest(BaseModel):
    date: datetime.date
    tracks: Optional[List[str]] = None
```

Add `from typing import List, Optional` if not already imported (check existing imports first).

After the existing `retry_crawl` endpoint (around line 180), add:

```python
@router.post("/crawl/entries")
async def crawl_race_entries(req: CrawlEntriesRequest):
    """Trigger 출마표 (pre-race entry) crawl for a target date. Runs in background."""
    from app.ml.crawl.crawl_entries import crawl_entries   # local import avoids circular dep

    tracks = req.tracks or ["SEOUL", "BUSAN", "JEJU"]
    target = req.date

    async def _run():
        try:
            result = await crawl_entries(target_date=target, tracks=tracks)
            logger.info("entry_crawl_done date=%s result=%s", target, result)
        except Exception as exc:
            logger.error("entry_crawl_failed date=%s error=%s", target, exc)

    asyncio.create_task(_run())
    return {
        "ok": True,
        "date": str(target),
        "tracks": tracks,
        "message": "Entry crawl started in background",
    }
```

- [ ] **Step 4: Run endpoint tests**

```bash
cd backend
uv run pytest tests/api/test_admin_entries.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run full test suite**

```bash
cd backend
uv run pytest tests/ -q --ignore=tests/db --ignore=tests/ml/test_dataset_pg.py
```

Expected: all prior tests + 11 (Task 1) + 2 (Task 2) = all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/admin.py backend/tests/api/test_admin_entries.py
git commit -m "feat: add POST /admin/crawl/entries endpoint for 출마표 crawling"
```

---

## Task 3: CLI Runner

**Files:**
- Create: `backend/app/ml/crawl/run_entry_crawl.py`

**Interfaces:**
- `python -m app.ml.crawl.run_entry_crawl --date 2026-06-28 --tracks SEOUL BUSAN`
- `python -m app.ml.crawl.run_entry_crawl` (defaults: tomorrow, all tracks)
- Requires `DATABASE_URL` env var; exits with code 1 if missing or if there are errors

**Context:** No new tests needed — the business logic is already covered by Task 1's unit tests. This is purely a CLI wrapper.

- [ ] **Step 1: Create the CLI runner**

Create `backend/app/ml/crawl/run_entry_crawl.py`:

```python
"""
CLI runner for 출마표 (pre-race entry) crawl.

Usage:
    cd backend
    DATABASE_URL=postgresql+asyncpg://... python -m app.ml.crawl.run_entry_crawl
    DATABASE_URL=... python -m app.ml.crawl.run_entry_crawl --date 2026-06-28
    DATABASE_URL=... python -m app.ml.crawl.run_entry_crawl --date 2026-06-28 --tracks SEOUL BUSAN
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ALL_TRACKS = ["SEOUL", "BUSAN", "JEJU"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl KRA 출마표 for a target date")
    parser.add_argument(
        "--date",
        type=datetime.date.fromisoformat,
        default=datetime.date.today() + datetime.timedelta(days=1),
        help="Race date in YYYY-MM-DD format (default: tomorrow)",
    )
    parser.add_argument(
        "--tracks",
        nargs="+",
        choices=ALL_TRACKS,
        default=ALL_TRACKS,
        help="Track names to crawl (default: all)",
    )
    return parser.parse_args()


async def _main() -> None:
    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL environment variable not set")
        sys.exit(1)

    args = _parse_args()
    from app.ml.crawl.crawl_entries import crawl_entries

    logger.info("Crawling entries for %s tracks=%s", args.date, args.tracks)
    result = await crawl_entries(target_date=args.date, tracks=args.tracks)

    logger.info(
        "Done — races=%d entries=%d errors=%d",
        result["races_upserted"],
        result["entries_upserted"],
        len(result["errors"]),
    )
    for err in result["errors"]:
        logger.warning("Error: %s", err)

    sys.exit(0 if not result["errors"] else 1)


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 2: Verify the module is importable**

```bash
cd backend
uv run python -c "import app.ml.crawl.run_entry_crawl; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Run full test suite one final time**

```bash
cd backend
uv run pytest tests/ -q --ignore=tests/db --ignore=tests/ml/test_dataset_pg.py
```

Expected: all pass. Total new tests added across all tasks: 9 (parser) + 2 (crawler unit) + 2 (admin API) = 13.

- [ ] **Step 4: Commit**

```bash
git add backend/app/ml/crawl/run_entry_crawl.py
git commit -m "feat: add 출마표 CLI runner for cron/manual use"
```

---

## 실전 사용법 (Usage Guide)

### 내일 레이스 예측 플로우

```bash
# 1. 오늘 밤 또는 내일 아침: 출마표 크롤
DATABASE_URL=postgresql+asyncpg://... \
  python -m app.ml.crawl.run_entry_crawl --date 2026-06-28

# 또는 Admin API로 (서버 실행 중일 때):
curl -X POST http://localhost:8000/api/v1/admin/crawl/entries \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-06-28", "tracks": ["SEOUL"]}'

# 2. DB에서 레이스 ID 확인
SELECT id, race_number, distance_m FROM races WHERE race_date = '2026-06-28';

# 3. 예측 API 호출 (기존 엔드포인트 그대로)
curl http://localhost:8000/api/v1/predict/race/12345
```

### 모닝 오즈 업데이트
레이스 당일 아침 7-8시에 재크롤하면 `upsert_race_entry`가 `morning_odds`를 업데이트합니다.

---

## Self-Review

### Spec Coverage

| Feature | Task |
|---|---|
| KRA 출마표 파서 (`carry_weight`, `morning_odds`) | Task 1 |
| 출마표 크롤러 (Race + RaceEntry 저장) | Task 1 |
| Admin API endpoint | Task 2 |
| CLI 실행기 | Task 3 |

### 중요 주의사항

1. **엔드포인트 불확실성**: `ChulmaDetailInfoPrint.do`가 작동 안 하면 `ChulmaDetailInfo.do`를 시도 (`_fetch_race_entries`가 두 URL을 순서대로 시도)
2. **KRA 모닝오즈 타이밍**: 레이스 당일 아침에만 `단승` 컬럼이 채워짐; 전날 크롤 시 `morning_odds=None`이 정상
3. **취소/제외마 필터링**: 기존 `parse_upcoming_race`가 이미 처리 중 (`"취소" in horse_name` 조건)
4. **파이썬 3.9 호환**: `from __future__ import annotations` 추가 필수 (`list[...]`, `X | Y` 사용 시)
