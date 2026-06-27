from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from .jobs import crawl_job, predict_job, train_job, notify_job, odds_job


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

    # Live odds refresh every 10 minutes (job itself guards 09:00~18:00 KST)
    scheduler.add_job(
        odds_job,
        trigger=IntervalTrigger(minutes=10),
        id="odds",
    )

    # Notify users about upcoming races every 5 minutes
    scheduler.add_job(
        notify_job,
        trigger=IntervalTrigger(minutes=5),
        id="notify",
    )
