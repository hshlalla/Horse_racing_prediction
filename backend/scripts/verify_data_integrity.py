"""
데이터 정합성 검증 스크립트

백필 완료 후 날짜-말-경주 간 정합성을 검사한다.

Usage:
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db uv run python scripts/verify_data_integrity.py
"""
from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


def _get_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")
    return url


async def run_all() -> bool:
    engine = create_async_engine(_get_db_url())
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        results: dict = {}

        # 1. 연도별 경주 수
        r = await session.execute(text("""
            SELECT EXTRACT(YEAR FROM race_date)::int AS yr,
                   COUNT(DISTINCT id) AS races
            FROM races
            WHERE race_date >= '2021-01-01'
            GROUP BY yr ORDER BY yr
        """))
        results['races_by_year'] = r.fetchall()

        # 2. 연도별 건강기록 커버리지 (경주 출전 말 기준)
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

        # 3. 연도별 조교기록 커버리지
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

        # 4. 날짜 역전 — 경주 이후에 기록된 건강 이벤트 수 (이건 정상일 수 있음)
        r = await session.execute(text("""
            SELECT COUNT(*) AS cnt
            FROM race_entries e
            JOIN races r ON e.race_id = r.id
            JOIN health_records hr ON e.horse_id = hr.horse_id
            WHERE hr.record_date < r.race_date - INTERVAL '3 years'
        """))
        results['stale_health_records'] = r.scalar()

        # 5. 말 이름 중복 (다른 horse_id, 같은 이름)
        r = await session.execute(text("""
            SELECT name, COUNT(*) AS cnt
            FROM horses
            GROUP BY name HAVING COUNT(*) > 1
            ORDER BY cnt DESC
            LIMIT 20
        """))
        results['duplicate_horse_names'] = r.fetchall()

        # 6. 건강기록 날짜 범위 및 총 건수
        r = await session.execute(text("""
            SELECT MIN(record_date), MAX(record_date), COUNT(*)
            FROM health_records
        """))
        results['health_date_range'] = r.fetchone()

        # 7. 조교기록 날짜 범위 및 총 건수
        r = await session.execute(text("""
            SELECT MIN(workout_date), MAX(workout_date), COUNT(*)
            FROM workout_times
        """))
        results['workout_date_range'] = r.fetchone()

        # 8. 출발훈련 데이터 현황
        r = await session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE last_start_training_passed IS TRUE)  AS passed,
                COUNT(*) FILTER (WHERE last_start_training_passed IS FALSE) AS failed,
                COUNT(*) FILTER (WHERE last_start_training_passed IS NULL)  AS missing
            FROM horses
        """))
        results['start_training_stats'] = r.fetchone()

        # 9. 수영 데이터 현황
        r = await session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE swim_count_recent > 0) AS with_swim,
                COUNT(*) FILTER (WHERE swim_count_recent IS NULL OR swim_count_recent = 0) AS no_swim
            FROM workout_times
        """))
        results['swim_stats'] = r.fetchone()

        # 10. 미래 날짜 조교기록 (파싱 버그로 인한 이상값)
        r = await session.execute(text("""
            SELECT COUNT(*) FROM workout_times WHERE workout_date > CURRENT_DATE + INTERVAL '1 year'
        """))
        results['future_workout_count'] = r.scalar()

    await engine.dispose()

    # ─── 리포트 출력 ───────────────────────────────────────────────
    SEP = "=" * 65
    print(f"\n{SEP}")
    print("DATA INTEGRITY REPORT")
    print(SEP)

    print("\n[1] 연도별 경주 수:")
    for yr, races in results['races_by_year']:
        mark = "✓" if races > 100 else "⚠"
        print(f"  {yr}: {races:>5,}경주  {mark}")

    print("\n[2] 건강기록 커버리지 (경주 출전 말 기준):")
    for yr, total, with_h in results['health_coverage']:
        pct = with_h / total * 100 if total else 0
        mark = "✓" if pct >= 30 else ("⚠" if pct >= 5 else "✗")
        print(f"  {yr}: {with_h:>5,}/{total:,}마 ({pct:5.1f}%)  {mark}")

    print("\n[3] 조교기록 커버리지 (경주 출전 말 기준):")
    for yr, total, with_w in results['workout_coverage']:
        pct = with_w / total * 100 if total else 0
        mark = "✓" if pct >= 30 else ("⚠" if pct >= 5 else "✗")
        print(f"  {yr}: {with_w:>5,}/{total:,}마 ({pct:5.1f}%)  {mark}")

    print(f"\n[4] 3년 이상 오래된 건강기록 참조: {results['stale_health_records']:,}건")

    print("\n[5] 말 이름 중복 (상위 20):")
    if not results['duplicate_horse_names']:
        print("  ✓ 중복 없음")
    else:
        for name, cnt in results['duplicate_horse_names']:
            print(f"  {name}: {cnt}개 ID  ⚠")

    h = results['health_date_range']
    print(f"\n[6] 건강기록: {h[0]} ~ {h[1]}  총 {h[2]:,}건")

    w = results['workout_date_range']
    print(f"[7] 조교기록: {w[0]} ~ {w[1]}  총 {w[2]:,}건")

    st = results['start_training_stats']
    print(f"\n[8] 출발훈련 데이터: 통과={st[0]:,} 불합격={st[1]:,} 미기록={st[2]:,}")

    sw = results['swim_stats']
    print(f"[9] 수영훈련 데이터: 기록있음={sw[0]:,} 없음={sw[1]:,}")

    fwc = results['future_workout_count']
    if fwc > 0:
        print(f"\n[10] ⚠ 미래 날짜 조교기록: {fwc:,}건 (파싱 버그 의심)")
        print(f"     수동 삭제 필요:")
        print(f"     DELETE FROM workout_times WHERE workout_date > CURRENT_DATE + INTERVAL '1 year';")
    else:
        print(f"\n[10] 미래 날짜 조교기록: 없음 ✓")

    # ─── 합격/불합격 판정 ──────────────────────────────────────────
    ok = True
    fail_msgs = []

    for yr, races in results['races_by_year']:
        if yr >= 2022 and races < 50:
            fail_msgs.append(f"✗ {yr}년 경주 수 부족 ({races}건)")
            ok = False

    for yr, total, with_h in results['health_coverage']:
        if yr >= 2022 and total > 0 and with_h / total < 0.03:
            fail_msgs.append(f"✗ {yr}년 건강기록 커버리지 3% 미만 ({with_h}/{total})")
            ok = False

    for yr, total, with_w in results['workout_coverage']:
        if yr >= 2022 and total > 0 and with_w / total < 0.03:
            fail_msgs.append(f"✗ {yr}년 조교기록 커버리지 3% 미만 ({with_w}/{total})")
            ok = False

    print(f"\n{SEP}")
    if ok:
        print("결론: ✓ 합격 — 재학습 진행 가능")
    else:
        print("결론: ✗ 불합격 — 백필 재확인 필요")
        for msg in fail_msgs:
            print(f"  {msg}")
    print(SEP)

    return ok


if __name__ == "__main__":
    passed = asyncio.run(run_all())
    sys.exit(0 if passed else 1)
