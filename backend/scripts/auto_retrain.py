"""
자동 재훈련 파이프라인

크롤 완료 여부를 판단하고 모델을 재훈련합니다.

Usage:
    uv run python scripts/auto_retrain.py                     # 기본 (신규 200경주 이상 시 훈련)
    uv run python scripts/auto_retrain.py --min-new-races 0   # 무조건 훈련
    uv run python scripts/auto_retrain.py --track SEOUL       # 특정 트랙만

자동 실행 예시 (크론탭):
    0 * * * * cd /path/to/backend && uv run python scripts/auto_retrain.py >> /tmp/retrain.log 2>&1
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

# backend 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.ml.train.pipeline import run_train

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PRODUCTION_JSON = Path(__file__).parent.parent / "models" / "production.json"
TRACKS = ["SEOUL", "BUSAN", "JEJU"]


def _get_last_trained_at() -> datetime.datetime | None:
    """production.json에서 가장 최근 promoted_at 시각을 반환."""
    if not PRODUCTION_JSON.exists():
        return None
    data = json.loads(PRODUCTION_JSON.read_text())
    times = []
    for v in data.values():
        t = v.get("promoted_at")
        if t:
            try:
                times.append(datetime.datetime.fromisoformat(t))
            except ValueError:
                pass
    return max(times) if times else None


def _count_new_races(db_url: str, since: datetime.datetime | None) -> int:
    """마지막 훈련 이후 추가된 경주 수 반환."""
    from sqlalchemy import create_engine, text

    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        if since is None:
            row = conn.execute(text("SELECT COUNT(*) FROM races")).fetchone()
        else:
            row = conn.execute(
                text("SELECT COUNT(*) FROM races WHERE race_date >= :since"),
                {"since": since.date()},
            ).fetchone()
    engine.dispose()
    return row[0] if row else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="자동 재훈련 파이프라인")
    parser.add_argument(
        "--min-new-races", type=int, default=200,
        help="최소 신규 경주 수 (이 수 이상이어야 훈련 시작, 기본 200)",
    )
    parser.add_argument(
        "--track", choices=TRACKS + ["ALL"], default="ALL",
        help="훈련할 트랙 (기본 ALL)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="신규 경주 수 무관하게 강제 훈련",
    )
    args = parser.parse_args()

    db_url = str(settings.DATABASE_URL)
    last_trained = _get_last_trained_at()
    new_races = _count_new_races(db_url, last_trained)

    logger.info(
        "마지막 훈련: %s | 신규 경주: %d개",
        last_trained.isoformat() if last_trained else "없음",
        new_races,
    )

    if not args.force and new_races < args.min_new_races:
        logger.info(
            "신규 경주 %d개 < 기준 %d개 → 훈련 스킵",
            new_races, args.min_new_races,
        )
        return

    tracks = TRACKS if args.track == "ALL" else [args.track]
    results = []
    for track in tracks:
        logger.info("=== %s 훈련 시작 ===", track)
        try:
            result = run_train(track, db_url)
            results.append(result)
            logger.info(
                "[%s] 완료: val_log_loss=%.4f  val_roi=%.4f  promoted=%s",
                track, result["val_log_loss"], result["val_roi"], result["promoted"],
            )
        except Exception as exc:
            logger.error("[%s] 훈련 실패: %s", track, exc)

    # 요약 출력
    print("\n" + "=" * 50)
    print(f"재훈련 완료 ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print(f"학습에 사용된 신규 데이터: {new_races:,}경주")
    print("-" * 50)
    for r in results:
        promoted_tag = "✅ 프로덕션 교체" if r.get("promoted") else "⏭ 기존 모델 유지"
        print(f"  {r['track']:6s}  LogLoss={r['val_log_loss']:.4f}  ROI={r['val_roi']:+.2%}  {promoted_tag}")
    print("=" * 50)


if __name__ == "__main__":
    main()
