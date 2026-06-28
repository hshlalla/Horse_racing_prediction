import asyncio
import datetime
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import structlog

log = structlog.get_logger()
logger = logging.getLogger(__name__)

KST = datetime.timezone(datetime.timedelta(hours=9))


async def crawl_job():
    """Daily 02:00 KST: crawl yesterday's results and today's race cards."""
    try:
        from app.ml.crawl.pipeline import run_crawl

        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        result = await run_crawl(
            start_date=yesterday,
            end_date=today + datetime.timedelta(days=2),
        )
        logger.info("crawl_job done: %s", result)
    except Exception as exc:
        logger.error("crawl_job failed: %s", exc)


async def predict_job():
    """Daily 03:00 KST: compute predictions for all of today's and tomorrow's races."""
    try:
        from app.db.session import async_session_factory
        from app.db.models.crawl import Race
        from app.ml.predict.service import predict_race
        from sqlalchemy import select

        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)

        async with async_session_factory() as session:
            result = await session.execute(
                select(Race).where(Race.race_date.in_([today, tomorrow]))
            )
            races = result.scalars().all()
            for race in races:
                try:
                    await predict_race(session, race.id)
                except Exception as exc:
                    logger.error("predict_job failed for race %s: %s", race.id, exc)

        logger.info("predict_job done: %d races processed", len(races))
    except Exception as exc:
        logger.error("predict_job failed: %s", exc)


async def train_job():
    """Sunday 04:00 KST: retrain models for all three tracks."""
    try:
        from app.ml.train.pipeline import run_train

        db_url = os.environ.get("DATABASE_URL", "")
        for track in ["SEOUL", "BUSAN", "JEJU"]:
            try:
                result = await asyncio.to_thread(run_train, track, db_url)
                logger.info("train_job [%s]: %s", track, result)
            except Exception as exc:
                logger.error("train_job failed for track %s: %s", track, exc)
    except Exception as exc:
        logger.error("train_job failed: %s", exc)


async def thursday_pdf_crawl_job():
    """목요일 14:00 KST: 이번 주말(금/토/일) 출마표 PDF 크롤.
    건강 기록·조교 타임까지 함께 저장되므로 경기 당일 예측 품질이 높아진다."""
    try:
        from app.ml.crawl.crawl_pdf_entries import crawl_pdf_entries

        today = datetime.date.today()
        upcoming = []
        for offset in range(1, 5):
            d = today + datetime.timedelta(days=offset)
            if d.weekday() in (4, 5, 6):   # 금=4, 토=5, 일=6
                upcoming.append(d)

        for race_date in upcoming:
            result = await crawl_pdf_entries(race_date)
            logger.info(
                "thursday_pdf_crawl: %s → races=%d entries=%d",
                race_date, result["races_upserted"], result["entries_upserted"],
            )
    except Exception as exc:
        logger.error("thursday_pdf_crawl_job failed: %s", exc)


async def odds_job():
    """매 5분: 경기 시작 30분 전부터 해당 트랙 odds 크롤 + 예측 갱신.
    post_time이 없는 경주는 경마 시간대(09~18 KST) 전체를 커버한다."""
    now_kst = datetime.datetime.now(KST)
    if not (9 <= now_kst.hour < 18):
        return

    try:
        from app.ml.crawl.crawl_entries import crawl_entries
        from app.db.session import async_session_factory
        from app.db.models.crawl import Race
        from app.ml.predict.service import predict_race
        from sqlalchemy import select

        today = datetime.date.today()

        # 30분 창 안에 출발하는 경주가 있는 트랙만 크롤
        window_start = now_kst
        window_end = now_kst + datetime.timedelta(minutes=35)

        async with async_session_factory() as session:
            all_races_q = await session.execute(
                select(Race).where(Race.race_date == today)
            )
            all_races = all_races_q.scalars().all()

        if not all_races:
            return

        # post_time이 있으면 창 필터, 없으면 경마 시간대 내 모두 포함
        tracks_to_crawl = set()
        for race in all_races:
            if race.post_time is None:
                tracks_to_crawl.add(race.track)
            else:
                pt_kst = race.post_time.astimezone(KST)
                if window_start <= pt_kst <= window_end:
                    tracks_to_crawl.add(race.track)

        if not tracks_to_crawl:
            return

        logger.info("odds_job: 크롤 대상 트랙 %s (창=%s~%s KST)",
                    tracks_to_crawl,
                    window_start.strftime("%H:%M"),
                    window_end.strftime("%H:%M"))

        result = await crawl_entries(target_date=today, tracks=list(tracks_to_crawl))
        logger.info(
            "odds_job crawl done: races=%d entries=%d",
            result["races_upserted"], result["entries_upserted"],
        )

        # 해당 트랙 예측 갱신
        async with async_session_factory() as session:
            for race in all_races:
                if race.track not in tracks_to_crawl:
                    continue
                try:
                    await predict_race(session, race.id)
                except Exception as exc:
                    logger.error("odds_job predict failed race=%s: %s", race.id, exc)

        logger.info("odds_job done: %d 트랙 예측 갱신", len(tracks_to_crawl))
    except Exception as exc:
        logger.error("odds_job failed: %s", exc)


async def notify_job():
    """Every 5 min: send FCM notifications for races starting in 15-30 min."""
    pass


scheduler = AsyncIOScheduler()


def setup_scheduler():
    from .triggers import setup_triggers
    setup_triggers(scheduler)
    scheduler.start()
    log.info("Scheduler started")
