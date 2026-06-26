import asyncio
import logging
import requests
import datetime
import sys
from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models.crawl import Horse, Jockey, Trainer, Race, RaceEntry, RaceResult, InraceTiming
from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
from app.ml.crawl.crawl_2026 import crawl_date_bruteforce

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

async def crawl_history(start_year: int, end_year: int):
    # Generate weekend dates (Friday, Saturday, Sunday) for the given years
    # KRA racing usually happens on Fri (Busan/Jeju), Sat (Seoul/Jeju), Sun (Seoul/Busan)
    dates = []
    start = datetime.date(start_year, 1, 1)
    end = datetime.date(end_year, 12, 31)
    curr = start
    while curr <= end:
        if curr.weekday() in [4, 5, 6]: # Friday, Saturday, Sunday
            dates.append(curr.strftime("%Y%m%d"))
        curr += datetime.timedelta(days=1)
    
    logger.info(f"Generated {len(dates)} dates to crawl from {start_year} to {end_year}.")
    
    async with async_session_factory() as session:
        for d in dates:
            for meet in ["1", "2", "3"]: # Seoul, Jeju, Busan
                try:
                    await crawl_date_bruteforce(session, d, meet=meet)
                except Exception as e:
                    logger.error(f"Error on {d} meet {meet}: {e}")
            
    logger.info(f"History Crawl Complete for {start_year}-{end_year}!")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python crawl_history.py <start_year> <end_year>")
        sys.exit(1)
        
    start_y = int(sys.argv[1])
    end_y = int(sys.argv[2])
    asyncio.run(crawl_history(start_y, end_y))
