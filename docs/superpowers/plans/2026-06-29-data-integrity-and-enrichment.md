# Data Integrity & Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2021-01부터 현재까지 건강기록·조교시간 백필을 완성하고, 출발훈련·수영훈련 피처를 추가하며, 데이터 정합성을 전수 검증한 뒤 모델을 재학습한다.

**Architecture:** 게시판 PDF 백필(boardNo=68/84/75)과 개별경주 PDF 백필(2024-01~현재)을 병행 완료 → 새 피처 파싱·저장 → 통합 검증 스크립트로 날짜·말·경주 간 정합성 확인 → 재학습 및 promote.

**Tech Stack:** Python/asyncio, httpx, pdfminer, PostgreSQL/SQLAlchemy, LightGBM/CatBoost, Alembic

## Global Constraints

- DB driver: `postgresql+asyncpg` (async), `postgresql+psycopg2` (sync/SQLAlchemy)
- Python: `uv run python` (pyproject.toml 관리)
- 모든 날짜: `datetime.date` (naive, KST 기준)
- upsert는 항상 ON CONFLICT DO UPDATE — 중복 삽입 금지
- 학습 데이터 split: val = 최근 6개월, train = 그 이전 전체 (dataset.py 동적 cutoff 적용됨)
- 배포 경로: `backend/` 아래, 스크립트는 `scripts/`

---

## 현재 진행 중인 백그라운드 작업

| PID | 스크립트 | 범위 |
|-----|---------|------|
| 84800 | `backfill_board_pdfs.py` | boardNo=68/84/75, fileNo 98194~160000 |

---

## File Map

| 파일 | 역할 | 변경 |
|------|------|------|
| `app/db/models/crawl.py` | WorkoutTime, Horse 모델 | 컬럼 추가 |
| `alembic/versions/xxxx_add_start_training_swim.py` | 마이그레이션 | 신규 |
| `app/ml/crawl/crawl_pdf_entries.py` | PDF 파서 | 출발훈련·수영 추출 추가 |
| `app/ml/crawl/upsert.py` | DB upsert | workout 업데이트 |
| `app/ml/train/dataset.py` | 피처 엔지니어링 | 신규 피처 4개 추가 |
| `scripts/backfill_pdf_workouts_health.py` | 개별경주 PDF 백필 | 이미 존재, 그대로 실행 |
| `scripts/verify_data_integrity.py` | 정합성 검증 | 신규 |
| `tests/crawl/test_pdf_parser_extra.py` | 파서 단위 테스트 | 신규 |

---

## Task 1: 출발훈련·수영훈련 파싱 함수 추가

**Files:**
- Modify: `app/ml/crawl/crawl_pdf_entries.py`
- Test: `tests/crawl/test_pdf_parser_extra.py`

**목표:** PDF 텍스트에서 출발훈련 통과 여부와 수영 횟수를 추출한다.

**추출 대상 텍스트 예시:**
```
출발훈련:210106(승,양호)
수영 : 3회 12바퀴
9회114분(승,승)/구10습0
```

- [ ] **Step 1: 테스트 파일 생성**

`tests/crawl/test_pdf_parser_extra.py` 생성:

```python
import pytest
from app.ml.crawl.crawl_pdf_entries import _extract_start_training, _extract_swim

def test_start_training_pass():
    lines = ["출발훈련:210106(승,양호)", "수영 : 0회 0바퀴"]
    result = _extract_start_training(lines)
    assert result == {"date": "210106", "passed": True}

def test_start_training_fail():
    lines = ["출발훈련:210305(불합격,불량)"]
    result = _extract_start_training(lines)
    assert result["passed"] is False

def test_start_training_none():
    result = _extract_start_training(["아무텍스트"])
    assert result is None

def test_swim_count():
    lines = ["수영 : 3회 12바퀴"]
    assert _extract_swim(lines) == 3

def test_swim_zero():
    lines = ["수영 : 0회 0바퀴"]
    assert _extract_swim(lines) == 0

def test_swim_none():
    assert _extract_swim(["텍스트없음"]) == 0
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd backend && uv run pytest tests/crawl/test_pdf_parser_extra.py -v 2>&1 | head -20
```
예상: `ImportError` 또는 `AttributeError: module has no attribute '_extract_start_training'`

- [ ] **Step 3: 파싱 함수 구현**

`app/ml/crawl/crawl_pdf_entries.py` 파일에서 `HEALTH_RE` 정의 다음에 추가:

```python
# 출발훈련: 210106(승,양호) 또는 불합격
START_TRAIN_RE = re.compile(
    r"출발훈련:(\d{6})\(([^)]+)\)"
)
# 수영: N회 N바퀴
SWIM_RE = re.compile(r"수영\s*:\s*(\d+)회")


def _extract_start_training(lines: List[str]) -> Optional[Dict]:
    """출발훈련 최근 결과 추출. passed=True(승/합격), False(불합격/불량)."""
    combined = "\n".join(lines)
    m = START_TRAIN_RE.search(combined)
    if not m:
        return None
    result_str = m.group(2)
    passed = "승" in result_str or "합격" in result_str
    return {"date": m.group(1), "passed": passed}


def _extract_swim(lines: List[str]) -> int:
    """수영 훈련 횟수 추출. 없으면 0."""
    combined = "\n".join(lines)
    m = SWIM_RE.search(combined)
    return int(m.group(1)) if m else 0
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd backend && uv run pytest tests/crawl/test_pdf_parser_extra.py -v
```
예상: `5 passed`

- [ ] **Step 5: `_parse_entry_pdf_pages` 및 `_parse_pdf_pages`에서 호출 추가**

두 파서 함수의 `_finalize` 내부에서 entry dict에 추가:

```python
def _finalize(entry: Dict, block_lines: List[str]) -> None:
    entry["workout_records"] = _extract_workouts(
        block_lines, entry["program_number"], entry["horse_name"]
    )
    entry["health_records"] = _extract_health_records(block_lines)
    entry["start_training"] = _extract_start_training(block_lines)   # 추가
    entry["swim_count"] = _extract_swim(block_lines)                  # 추가
```

- [ ] **Step 6: 커밋**

```bash
git add app/ml/crawl/crawl_pdf_entries.py tests/crawl/test_pdf_parser_extra.py
git commit -m "feat: extract start_training result and swim count from entry PDFs"
```

---

## Task 2: DB 컬럼 추가 (WorkoutTime + Horse)

**Files:**
- Modify: `app/db/models/crawl.py`
- Create: `alembic/versions/XXXX_add_start_training_swim.py`

**목표:** `workout_times` 테이블에 `start_training_passed`, `swim_count_recent` 컬럼을 추가한다.

- [ ] **Step 1: 모델에 컬럼 추가**

`app/db/models/crawl.py`의 `WorkoutTime` 클래스에 추가:

```python
class WorkoutTime(Base):
    __tablename__ = "workout_times"
    __table_args__ = (UniqueConstraint("horse_id", "workout_date", "distance_m"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    workout_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    workout_type: Mapped[Optional[str]] = mapped_column(String(20))
    distance_m: Mapped[Optional[int]] = mapped_column(Integer)
    time_s: Mapped[Optional[float]] = mapped_column(Float)
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    group_size: Mapped[Optional[int]] = mapped_column(Integer)
    start_training_passed: Mapped[Optional[bool]] = mapped_column(Boolean)   # 추가
    swim_count_recent: Mapped[Optional[int]] = mapped_column(Integer)        # 추가
```

`Horse` 클래스에도 추가 (마지막 출발훈련 통과 날짜 캐시):
```python
    last_start_training_date: Mapped[Optional[datetime.date]] = mapped_column(Date)   # 추가
    last_start_training_passed: Mapped[Optional[bool]] = mapped_column(Boolean)       # 추가
```

- [ ] **Step 2: Alembic 마이그레이션 생성**

```bash
cd backend && uv run alembic revision --autogenerate -m "add_start_training_swim"
```

생성된 파일에서 `upgrade()` 확인:
```python
def upgrade() -> None:
    op.add_column('workout_times', sa.Column('start_training_passed', sa.Boolean(), nullable=True))
    op.add_column('workout_times', sa.Column('swim_count_recent', sa.Integer(), nullable=True))
    op.add_column('horses', sa.Column('last_start_training_date', sa.Date(), nullable=True))
    op.add_column('horses', sa.Column('last_start_training_passed', sa.Boolean(), nullable=True))
```

- [ ] **Step 3: 마이그레이션 적용**

```bash
cd backend && uv run alembic upgrade head
```
예상: `Running upgrade ... -> XXXX, add_start_training_swim`

- [ ] **Step 4: 컬럼 존재 확인**

```bash
cd backend && uv run python -c "
from app.db.models.crawl import WorkoutTime, Horse
print([c.key for c in WorkoutTime.__table__.columns])
print([c.key for c in Horse.__table__.columns])
"
```
예상 출력에 `start_training_passed`, `swim_count_recent`, `last_start_training_date`, `last_start_training_passed` 포함.

- [ ] **Step 5: 커밋**

```bash
git add app/db/models/crawl.py alembic/versions/
git commit -m "feat: add start_training and swim columns to workout_times and horses"
```

---

## Task 3: upsert_workout_time 업데이트

**Files:**
- Modify: `app/ml/crawl/upsert.py`

**목표:** `upsert_workout_time`이 `start_training_passed`, `swim_count_recent`를 받아 저장한다. `upsert_horse`가 `last_start_training_*`를 업데이트한다.

- [ ] **Step 1: `upsert_workout_time` 시그니처 확장**

`app/ml/crawl/upsert.py`에서 `upsert_workout_time` 함수:

```python
async def upsert_workout_time(
    session: AsyncSession,
    horse_id: int,
    workout_date: datetime.date,
    workout_type: Optional[str] = None,
    distance_m: Optional[int] = None,
    time_s: Optional[float] = None,
    rank: Optional[int] = None,
    group_size: Optional[int] = None,
    start_training_passed: Optional[bool] = None,   # 추가
    swim_count_recent: Optional[int] = None,         # 추가
) -> int:
    from app.db.models.crawl import WorkoutTime
    stmt = pg_insert(WorkoutTime).values(
        horse_id=horse_id,
        workout_date=workout_date,
        workout_type=workout_type,
        distance_m=distance_m or 1000,
        time_s=time_s,
        rank=rank,
        group_size=group_size,
        start_training_passed=start_training_passed,
        swim_count_recent=swim_count_recent,
    ).on_conflict_do_update(
        index_elements=["horse_id", "workout_date", "distance_m"],
        set_={
            "workout_type": workout_type,
            "time_s": time_s,
            "rank": rank,
            "group_size": group_size,
            "start_training_passed": start_training_passed,
            "swim_count_recent": swim_count_recent,
        },
    )
    result = await session.execute(stmt)
    return result.inserted_primary_key[0]
```

- [ ] **Step 2: `upsert_horse` 확장 — 출발훈련 캐시 업데이트**

`upsert_horse` 함수에 파라미터 추가:

```python
async def upsert_horse(
    session: AsyncSession,
    name: str,
    age: int,
    sex: str,
    last_start_training_date: Optional[datetime.date] = None,   # 추가
    last_start_training_passed: Optional[bool] = None,           # 추가
) -> int:
```

set_ 블록에도 추가:
```python
set_={
    "age": age,
    "sex": sex,
    **({"last_start_training_date": last_start_training_date,
        "last_start_training_passed": last_start_training_passed}
       if last_start_training_date else {}),
},
```

- [ ] **Step 3: `backfill_board_pdfs.py`의 `_process_pdf`에서 신규 필드 전달**

`scripts/backfill_board_pdfs.py`의 `_process_pdf` 함수:

```python
async def _process_pdf(session, pdf_bytes: bytes, filename: str) -> dict:
    from app.ml.crawl.crawl_pdf_entries import _parse_entry_pdf_pages, _parse_pdf_pages
    from app.ml.crawl.upsert import upsert_horse, upsert_workout_time, upsert_health_record

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

        horse_id = await upsert_horse(
            session,
            name=entry["horse_name"],
            age=entry.get("horse_age") or 3,
            sex=entry.get("horse_sex") or "M",
            last_start_training_date=st_date,
            last_start_training_passed=st_passed,
        )
        horses_saved += 1

        swim_count = entry.get("swim_count", 0)

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
                swim_count_recent=swim_count,
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
```

`crawl_pdf_entries.py`에서 `_yymmdd_to_date` import 필요:
```python
from app.ml.crawl.crawl_pdf_entries import _parse_entry_pdf_pages, _parse_pdf_pages, _yymmdd_to_date
```

- [ ] **Step 4: `crawl_pdf_entries.py`의 기존 `crawl_pdf_entries` 함수도 신규 필드 전달 업데이트**

`crawl_pdf_entries` 함수 내 루프에서:

```python
# 기존 upsert_workout_time 호출부
for wk in entry.get("workout_records") or []:
    st = entry.get("start_training")
    await upsert_workout_time(
        session,
        horse_id=horse_id,
        workout_date=wk["workout_date"],
        workout_type=wk.get("workout_type"),
        distance_m=wk.get("distance_m", 1000),
        time_s=wk.get("time_s"),
        rank=wk.get("rank"),
        group_size=None,
        start_training_passed=st["passed"] if st else None,
        swim_count_recent=entry.get("swim_count", 0),
    )
```

- [ ] **Step 5: 커밋**

```bash
git add app/ml/crawl/upsert.py app/ml/crawl/crawl_pdf_entries.py scripts/backfill_board_pdfs.py
git commit -m "feat: propagate start_training and swim_count through upsert pipeline"
```

---

## Task 4: Dataset 피처 추가 (start_training, swim)

**Files:**
- Modify: `app/ml/train/dataset.py`

**목표:** 4개 신규 피처를 학습에 추가한다.

| 피처명 | 출처 | 설명 |
|--------|------|------|
| `start_training_passed` | horses.last_start_training_passed | 최근 출발훈련 통과 여부 (1/0) |
| `days_since_start_training` | horses.last_start_training_date | 마지막 출발훈련 이후 일수 |
| `swim_count_recent` | workout_times.swim_count_recent | 최근 수영 훈련 횟수 |
| `recent_workout_count_30d` | workout_times | 최근 30일 조교 횟수 |

- [ ] **Step 1: FEATURES 리스트에 추가**

`dataset.py` FEATURES 리스트:

```python
FEATURES = [
    # ... 기존 피처들 ...
    'recent_workout_time_s',
    'recent_workout_rank',
    'injury_count_30d',
    'days_since_injury',
    'start_training_passed',        # 추가
    'days_since_start_training',    # 추가
    'swim_count_recent',            # 추가
    'recent_workout_count_30d',     # 추가
]
```

- [ ] **Step 2: SQL 쿼리에 신규 피처 추가**

`_QUERY` 내 SELECT와 LEFT JOIN 추가:

SELECT에 추가:
```sql
    h.last_start_training_passed,
    h.last_start_training_date,
    wk_swim.swim_count_recent,
    wk_cnt.workout_count_30d AS recent_workout_count_30d,
```

LEFT JOIN 추가 (`wk ON true` 다음에):
```sql
LEFT JOIN LATERAL (
    SELECT swim_count_recent
    FROM workout_times
    WHERE horse_id = e.horse_id
      AND workout_date < r.race_date
      AND swim_count_recent IS NOT NULL
    ORDER BY workout_date DESC
    LIMIT 1
) wk_swim ON true
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS workout_count_30d
    FROM workout_times
    WHERE horse_id = e.horse_id
      AND workout_date >= r.race_date - INTERVAL '30 days'
      AND workout_date < r.race_date
) wk_cnt ON true
```

- [ ] **Step 3: `_apply_features`에서 신규 피처 전처리**

`_apply_features` 함수 내 Workout features 섹션 다음:

```python
# Start training features
df['start_training_passed'] = df['last_start_training_passed'].fillna(-1).astype(int)
df['days_since_start_training'] = (
    (pd.Timestamp.today() - df['last_start_training_date'])
    .dt.days
    .fillna(999)
    .clip(upper=999)
    .astype(int)
)
# Swim and workout count
df['swim_count_recent'] = df['swim_count_recent'].fillna(0).astype(int)
df['recent_workout_count_30d'] = df['recent_workout_count_30d'].fillna(0).astype(int)
```

- [ ] **Step 4: 컬럼명 정리 (SQL alias → pandas column명 일치)**

SELECT에서 alias 정확히:
- `h.last_start_training_passed` (pandas 컬럼: `last_start_training_passed`)
- `h.last_start_training_date` (pandas 컬럼: `last_start_training_date`)
- `wk_swim.swim_count_recent` (alias: `swim_count_recent`)
- `wk_cnt.workout_count_30d AS recent_workout_count_30d`

- [ ] **Step 5: 로컬 동작 확인**

```bash
cd backend && uv run python -c "
from app.ml.train.dataset import load_dataset_pg
import os
url = os.environ.get('DATABASE_URL', '')
train, val, test, feats, tgt = load_dataset_pg(url)
print('피처 수:', len(feats))
print('신규 피처 커버리지:')
for f in ['start_training_passed','days_since_start_training','swim_count_recent','recent_workout_count_30d']:
    non_null = (train[f] != 0).mean() if f != 'days_since_start_training' else (train[f] < 999).mean()
    print(f'  {f}: {non_null:.1%} non-default')
"
```

- [ ] **Step 6: 커밋**

```bash
git add app/ml/train/dataset.py
git commit -m "feat: add start_training, swim, workout_count_30d features to dataset"
```

---

## Task 5: 개별 경주 PDF 백필 실행 (2024-01 ~ 현재)

**Files:**
- Run: `scripts/backfill_pdf_workouts_health.py`

**목표:** 2024-01-01~2026-06-28 기간 개별 경주 PDF(서울/부산/제주)를 크롤하여 건강·조교 기록을 채운다.

- [ ] **Step 1: 게시판 백필(PID 84800) 완료 확인**

```bash
tail -20 /tmp/backfill_board.log | grep -E "완료|BUSAN|JEJU|ERROR"
```
서울 완료 → 부산 완료 → 제주 완료 순서. 완료 로그:
```
[SEOUL] 완료: 스캔=... PDF=... 말=... 조교=... 건강=...
[BUSAN] 완료: ...
[JEJU] 완료: ...
```

- [ ] **Step 2: 개별경주 PDF 백필 실행 (백그라운드)**

```bash
cd /path/to/backend
nohup uv run python scripts/backfill_pdf_workouts_health.py 2024-01-01 2026-06-28 > /tmp/backfill_individual.log 2>&1 &
echo "PID: $!"
```

- [ ] **Step 3: 진행 모니터링**

```bash
tail -f /tmp/backfill_individual.log
```
날짜별 진행 확인, ERROR 없어야 함.

---

## Task 6: 데이터 정합성 검증 스크립트

**Files:**
- Create: `scripts/verify_data_integrity.py`

**목표:** 5개 항목을 자동 검증하여 문제 있으면 상세 리포트를 출력한다.

검증 항목:
1. **날짜별 경주 커버리지** — 2021-01 이후 경마일에 race 레코드 있는지
2. **건강기록 커버리지** — race_entries 말 중 health_records 있는 비율 (연도별)
3. **조교기록 커버리지** — race_entries 말 중 workout_times 있는 비율 (연도별)
4. **날짜 역전 검사** — health_record.record_date > race.race_date 인 케이스
5. **말 이름 중복** — 같은 이름이 다른 horse_id로 저장된 케이스

- [ ] **Step 1: 스크립트 작성**

`scripts/verify_data_integrity.py`:

```python
"""
데이터 정합성 검증 스크립트

Usage:
    uv run python scripts/verify_data_integrity.py
"""
import asyncio
import datetime
from sqlalchemy import text
from app.db.session import async_session_factory

CHECKS = []

async def run_all():
    async with async_session_factory() as session:
        results = {}

        # 1. 연도별 경주 수
        r = await session.execute(text("""
            SELECT EXTRACT(YEAR FROM race_date)::int AS yr,
                   COUNT(DISTINCT id) AS races
            FROM races
            WHERE race_date >= '2021-01-01'
            GROUP BY yr ORDER BY yr
        """))
        results['races_by_year'] = r.fetchall()

        # 2. 건강기록 커버리지 (말 기준, 연도별 경주 출전 말 중)
        r = await session.execute(text("""
            SELECT EXTRACT(YEAR FROM r.race_date)::int AS yr,
                   COUNT(DISTINCT e.horse_id) AS horses_in_races,
                   COUNT(DISTINCT hr.horse_id) AS horses_with_health
            FROM races r
            JOIN race_entries e ON r.id = e.race_id
            LEFT JOIN health_records hr ON e.horse_id = hr.horse_id
            WHERE r.race_date >= '2021-01-01'
            GROUP BY yr ORDER BY yr
        """))
        results['health_coverage'] = r.fetchall()

        # 3. 조교기록 커버리지
        r = await session.execute(text("""
            SELECT EXTRACT(YEAR FROM r.race_date)::int AS yr,
                   COUNT(DISTINCT e.horse_id) AS horses_in_races,
                   COUNT(DISTINCT wk.horse_id) AS horses_with_workout
            FROM races r
            JOIN race_entries e ON r.id = e.race_id
            LEFT JOIN workout_times wk ON e.horse_id = wk.horse_id
            WHERE r.race_date >= '2021-01-01'
            GROUP BY yr ORDER BY yr
        """))
        results['workout_coverage'] = r.fetchall()

        # 4. 날짜 역전 (미래 건강기록이 경주 전에 존재하는 비율)
        r = await session.execute(text("""
            SELECT COUNT(*) AS bad_rows
            FROM race_entries e
            JOIN races r ON e.race_id = r.id
            JOIN health_records hr ON e.horse_id = hr.horse_id
            WHERE hr.record_date > r.race_date
        """))
        results['future_health_records'] = r.scalar()

        # 5. 말 이름 중복 (같은 이름, 다른 ID)
        r = await session.execute(text("""
            SELECT name, COUNT(*) AS cnt
            FROM horses
            GROUP BY name HAVING COUNT(*) > 1
            ORDER BY cnt DESC LIMIT 20
        """))
        results['duplicate_horse_names'] = r.fetchall()

        # 6. 건강기록 날짜 범위
        r = await session.execute(text("""
            SELECT MIN(record_date), MAX(record_date), COUNT(*)
            FROM health_records
        """))
        results['health_date_range'] = r.fetchone()

        # 7. 조교기록 날짜 범위
        r = await session.execute(text("""
            SELECT MIN(workout_date), MAX(workout_date), COUNT(*)
            FROM workout_times
        """))
        results['workout_date_range'] = r.fetchone()

        # 리포트 출력
        print("\n" + "="*60)
        print("DATA INTEGRITY REPORT")
        print("="*60)

        print("\n[1] 연도별 경주 수:")
        for yr, races in results['races_by_year']:
            print(f"  {yr}: {races:,}경주")

        print("\n[2] 건강기록 커버리지 (말 기준):")
        for yr, total, with_h in results['health_coverage']:
            pct = with_h / total * 100 if total else 0
            status = "✓" if pct > 50 else "⚠" if pct > 10 else "✗"
            print(f"  {yr}: {with_h:,}/{total:,}마 ({pct:.1f}%) {status}")

        print("\n[3] 조교기록 커버리지 (말 기준):")
        for yr, total, with_w in results['workout_coverage']:
            pct = with_w / total * 100 if total else 0
            status = "✓" if pct > 50 else "⚠" if pct > 10 else "✗"
            print(f"  {yr}: {with_w:,}/{total:,}마 ({pct:.1f}%) {status}")

        print(f"\n[4] 미래 건강기록 (경주 이후 날짜): {results['future_health_records']:,}건")
        if results['future_health_records'] > 0:
            print("  ⚠ 이는 정상 — 건강기록 날짜가 경주 날짜보다 최신일 수 있음")

        print("\n[5] 말 이름 중복 (상위 20):")
        if not results['duplicate_horse_names']:
            print("  ✓ 중복 없음")
        for name, cnt in results['duplicate_horse_names']:
            print(f"  {name}: {cnt}개 ID")

        h_range = results['health_date_range']
        print(f"\n[6] 건강기록: {h_range[0]} ~ {h_range[1]} ({h_range[2]:,}건)")

        w_range = results['workout_date_range']
        print(f"[7] 조교기록: {w_range[0]} ~ {w_range[1]} ({w_range[2]:,}건)")

        print("\n" + "="*60)

        # 합격 기준
        ok = True
        for yr, total, with_h in results['health_coverage']:
            if yr >= 2022 and total > 0 and with_h / total < 0.1:
                print(f"FAIL: {yr}년 건강기록 커버리지 10% 미만")
                ok = False
        for yr, total, with_w in results['workout_coverage']:
            if yr >= 2022 and total > 0 and with_w / total < 0.05:
                print(f"FAIL: {yr}년 조교기록 커버리지 5% 미만")
                ok = False

        print("결론:", "✓ 합격 — 재학습 진행 가능" if ok else "✗ 불합격 — 백필 재확인 필요")
        return ok

if __name__ == "__main__":
    asyncio.run(run_all())
```

- [ ] **Step 2: 실행 및 결과 확인**

```bash
cd backend && uv run python scripts/verify_data_integrity.py
```

예상 출력 (백필 완료 후):
```
[2] 건강기록 커버리지 (말 기준):
  2021: N/total마 (>10%) ✓ 또는 ⚠
  2022: ...
  ...
결론: ✓ 합격 — 재학습 진행 가능
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/verify_data_integrity.py
git commit -m "feat: add data integrity verification script"
```

---

## Task 7: 말 이름 중복 정리 (발견 시)

**Files:**
- Create: `scripts/merge_duplicate_horses.py`

**목표:** 같은 이름의 말이 두 개 이상 horse_id로 등록된 경우, 하나로 병합한다.

- [ ] **Step 1: 중복 조회**

```bash
cd backend && uv run python -c "
import asyncio
from sqlalchemy import text
from app.db.session import async_session_factory

async def check():
    async with async_session_factory() as s:
        r = await s.execute(text(
            'SELECT name, array_agg(id ORDER BY id) FROM horses GROUP BY name HAVING COUNT(*)>1'
        ))
        rows = r.fetchall()
        print(f'중복 말 이름: {len(rows)}건')
        for name, ids in rows[:10]:
            print(f'  {name}: {ids}')

asyncio.run(check())
"
```

중복이 없으면 Task 7 건너뜀.

- [ ] **Step 2: 중복 병합 스크립트 작성 (중복 있을 경우)**

`scripts/merge_duplicate_horses.py`:

```python
"""
같은 이름의 말을 id가 가장 작은 것으로 병합.
관련 테이블: race_entries, health_records, workout_times, pedigree
"""
import asyncio
from sqlalchemy import text
from app.db.session import async_session_factory

RELATED_TABLES = [
    ("race_entries", "horse_id"),
    ("health_records", "horse_id"),
    ("workout_times", "horse_id"),
    ("pedigree", "horse_id"),
    ("race_results", "horse_id"),
    ("inrace_timings", "horse_id"),
]

async def merge():
    async with async_session_factory() as session:
        r = await session.execute(text(
            "SELECT name, array_agg(id ORDER BY id) FROM horses GROUP BY name HAVING COUNT(*)>1"
        ))
        groups = r.fetchall()
        print(f"병합 대상: {len(groups)}그룹")

        for name, ids in groups:
            keep_id = ids[0]
            remove_ids = ids[1:]
            for table, col in RELATED_TABLES:
                for rid in remove_ids:
                    await session.execute(text(
                        f"UPDATE {table} SET {col} = :keep WHERE {col} = :remove"
                    ), {"keep": keep_id, "remove": rid})
            for rid in remove_ids:
                await session.execute(text(
                    "DELETE FROM horses WHERE id = :rid"
                ), {"rid": rid})
            print(f"  병합: {name} {ids} → {keep_id}")

        await session.commit()
        print("완료")

if __name__ == "__main__":
    asyncio.run(merge())
```

- [ ] **Step 3: 실행**

```bash
cd backend && uv run python scripts/merge_duplicate_horses.py
```

- [ ] **Step 4: 재검증**

```bash
cd backend && uv run python scripts/verify_data_integrity.py
```

---

## Task 8: 모델 재학습 및 검증

**Files:**
- Run: `app/ml/train/pipeline.py`

**목표:** 모든 데이터 정합성 확인 후 세 트랙 모델을 재학습하고 promote 여부 확인한다.

**전제조건:** Task 6의 검증 스크립트가 `✓ 합격` 출력해야 진행.

- [ ] **Step 1: 학습 데이터 크기 사전 확인**

```bash
cd backend && uv run python -c "
from app.ml.train.dataset import load_dataset_pg
import os
train, val, _, feats, _ = load_dataset_pg(os.environ['DATABASE_URL'])
print(f'train: {len(train):,}행 ({train.race_date.min().date()} ~ {train.race_date.max().date()})')
print(f'val:   {len(val):,}행 ({val.race_date.min().date()} ~ {val.race_date.max().date()})')
print(f'피처:  {len(feats)}개')
new_feats = ['start_training_passed','days_since_start_training','swim_count_recent','recent_workout_count_30d']
for f in new_feats:
    coverage = (train[f] != 0).mean() if f != 'days_since_start_training' else (train[f] < 999).mean()
    print(f'  {f}: {coverage:.1%} coverage')
"
```

예상: train 50,000+행, val 10,000+행, 피처 29개

- [ ] **Step 2: 세 트랙 재학습**

```bash
cd backend && uv run python -c "
import asyncio, os
from app.ml.train.pipeline import run_train
db_url = os.environ['DATABASE_URL']

for track in ['SEOUL', 'BUSAN', 'JEJU']:
    result = run_train(track, db_url)
    print(f'{track}: val_log_loss={result[\"val_log_loss\"]:.4f} promoted={result[\"promoted\"]}')
"
```

- [ ] **Step 3: 결과 확인**

`models/production.json` 확인:
```bash
cat backend/models/production.json | python3 -m json.tool
```

이전 대비 `log_loss` 개선 여부 확인.
- SEOUL: < 2.3329 이면 promote
- BUSAN: < 2.3924 이면 promote
- JEJU: < 2.2717 이면 promote

- [ ] **Step 4: 커밋**

```bash
git add models/production.json
git commit -m "feat: retrain models with 2021-2026 backfilled health/workout data"
```

---

## Task 9: 테스트 회귀 확인

- [ ] **Step 1: 전체 테스트 스위트 실행**

```bash
cd backend && uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```

예상: 기존 테스트 모두 통과.

- [ ] **Step 2: 신규 파서 테스트 확인**

```bash
cd backend && uv run pytest tests/crawl/test_pdf_parser_extra.py -v
```

예상: `5 passed`

- [ ] **Step 3: 커밋 (변경사항 있을 경우)**

```bash
git add -A && git commit -m "test: ensure all tests pass after data enrichment"
```

---

## 실행 순서 요약

```
현재 실행 중: backfill_board_pdfs.py (PID 84800)

즉시 진행 가능:
  Task 1 → Task 2 → Task 3 → Task 4 → Task 6(스크립트 작성)

게시판 백필 완료 후:
  Task 5 (개별경주 PDF 백필 실행)
  Task 6 (검증 실행) → Task 7 (중복 정리, 해당 시)

모든 백필 완료 + 검증 통과 후:
  Task 8 (재학습)
  Task 9 (테스트)
```

---

## 기대 효과

| 지표 | 현재 | 목표 |
|------|------|------|
| 건강기록 연도별 커버리지 | 2025+만 10%+ | **2022+에서 30%+** |
| 조교기록 커버리지 | 2025+만 커버 | **2022+에서 30%+** |
| train 행 수 | ~50,000 | ~50,000 (val split 개선) |
| val 행 수 (최근 6개월) | ~5,000 | ~8,000 (2026 상반기 포함) |
| 신규 피처 | 0 | 4개 추가 |
| val_log_loss | SEOUL 2.3329 | **개선 기대** |
