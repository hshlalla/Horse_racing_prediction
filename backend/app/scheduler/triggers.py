from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from .jobs import crawl_job, predict_job, train_job, notify_job, odds_job, thursday_pdf_crawl_job, live_results_job


def setup_triggers(scheduler: AsyncIOScheduler):
    # Daily crawl at 02:00 KST (17:00 UTC)
    scheduler.add_job(
        crawl_job,
        trigger=CronTrigger(hour=17, minute=0, timezone="UTC"),
        id="crawl",
    )

    # Daily predict at 03:00 KST (18:00 UTC)
    scheduler.add_job(
        predict_job,
        trigger=CronTrigger(hour=18, minute=0, timezone="UTC"),
        id="predict",
    )

    # Weekly retrain on Sunday at 04:00 KST (19:00 UTC)
    scheduler.add_job(
        train_job,
        trigger=CronTrigger(day_of_week="sun", hour=19, minute=0, timezone="UTC"),
        id="train",
    )

    # 목요일 14:00 KST (05:00 UTC): 이번 주말 출마표 PDF 크롤
    # 건강 기록·조교 타임 포함 → 금/토/일 예측 품질 향상
    scheduler.add_job(
        thursday_pdf_crawl_job,
        trigger=CronTrigger(day_of_week="thu", hour=5, minute=0, timezone="UTC"),
        id="thursday_pdf_crawl",
    )

    # 경기 당일 5분마다: 출발 30분 전 트랙 odds 크롤 + 예측 갱신
    # (기존 10분 → 5분, 전체 경마 시간대 → 출발 30분 전 창으로 집중)
    scheduler.add_job(
        odds_job,
        trigger=IntervalTrigger(minutes=5),
        id="odds",
    )

    # 매 15분마다: 상세 결과 크롤
    scheduler.add_job(
        live_results_job,
        trigger=IntervalTrigger(minutes=15),
        id="live_results",
    )

    # FCM 알림 (추후 구현)
    scheduler.add_job(
        notify_job,
        trigger=IntervalTrigger(minutes=5),
        id="notify",
    )
