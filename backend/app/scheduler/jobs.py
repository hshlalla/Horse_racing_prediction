from apscheduler.schedulers.asyncio import AsyncIOScheduler
import structlog

log = structlog.get_logger()

async def crawl_and_predict_job():
    log.info("Running daily crawl and predict job...")
    # This would invoke the ML pipeline's crawl and predict stages
    pass

async def retrain_models_job():
    log.info("Running weekly retrain models job...")
    # This would invoke the ML pipeline's train stage
    pass

async def notify_races_job():
    log.info("Running race notification job...")
    # This would query upcoming races and send FCM notifications
    pass

scheduler = AsyncIOScheduler()

def setup_scheduler():
    from .triggers import setup_triggers
    setup_triggers(scheduler)
    scheduler.start()
    log.info("Scheduler started")
