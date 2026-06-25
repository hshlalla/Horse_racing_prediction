from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from .jobs import crawl_and_predict_job, retrain_models_job, notify_races_job

def setup_triggers(scheduler: AsyncIOScheduler):
    # Daily crawl and predict at 02:00 KST
    scheduler.add_job(
        crawl_and_predict_job,
        trigger=CronTrigger(hour=2, minute=0, timezone="Asia/Seoul"),
        id="crawl_and_predict"
    )

    # Weekly retrain on Sunday at 03:00 KST
    scheduler.add_job(
        retrain_models_job,
        trigger=CronTrigger(day_of_week='sun', hour=3, minute=0, timezone="Asia/Seoul"),
        id="retrain_models"
    )

    # Notify users about upcoming races every 5 minutes
    scheduler.add_job(
        notify_races_job,
        trigger=CronTrigger(minute="*/5"),
        id="notify_races"
    )
