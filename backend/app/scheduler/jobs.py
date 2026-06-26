import asyncio
import datetime
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import structlog

log = structlog.get_logger()
logger = logging.getLogger(__name__)


async def crawl_job():
    """Daily 02:00 KST: crawl yesterday's results and today's race cards."""
    try:
        from app.ml.crawl.pipeline import run_crawl

        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        result = await run_crawl(
            start_date=yesterday,
            end_date=today,
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


async def notify_job():
    """Every 5 min: send FCM notifications for races starting in 15-30 min."""
    # Unchanged from v1 scaffold — implement when FCM is wired up
    pass


scheduler = AsyncIOScheduler()


def setup_scheduler():
    from .triggers import setup_triggers
    setup_triggers(scheduler)
    scheduler.start()
    log.info("Scheduler started")
