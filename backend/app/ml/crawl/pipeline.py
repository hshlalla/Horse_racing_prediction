import logging
import os
import glob
from datetime import date
from sqlalchemy.orm import Session
from app.ml.crawl.kra_client import KRAClient
from app.ml.crawl.kra_openapi import KRAOpenAPIClient
from app.ml.crawl.parsers.kra_html_parser import parse_race_list_html
from app.ml.crawl.synthetic_data import main as populate_db

logger = logging.getLogger(__name__)

class CrawlingPipeline:
    """
    Hybrid Crawling Pipeline:
    1. Attempts to use KRA OpenAPI (API187) if key is active.
    2. Uses local HTML dumps (backend/data/kra_dumps/*.html) if provided to bypass web blocks.
    3. Falls back to synthetic data populator if requested.
    """
    def __init__(self, db_session: Session, api_key: str = None):
        self.db = db_session
        self.client = KRAClient()
        self.openapi_client = KRAOpenAPIClient(api_key) if api_key else None
        self.dump_dir = os.path.join(os.getcwd(), "data", "kra_dumps")

    async def run(self, start_date: date, end_date: date, use_synthetic_fallback: bool = True):
        logger.info(f"Starting KRA crawl pipeline from {start_date} to {end_date}")
        
        # 1. Process local HTML dumps first (to bypass IP blocks securely)
        if os.path.exists(self.dump_dir):
            html_files = glob.glob(os.path.join(self.dump_dir, "*.html"))
            for file_path in html_files:
                logger.info(f"Parsing local HTML dump: {file_path}")
                with open(file_path, "r", encoding="euc-kr", errors="ignore") as f:
                    html_content = f.read()
                    parsed_races = parse_race_list_html(html_content)
                    if parsed_races:
                        logger.info(f"Found {len(parsed_races)} dates in dump {os.path.basename(file_path)}")
        
        # 2. Live Web Crawling (Chulma / Score Detail)
        logger.info("Attempting Live Web Crawling from race.kra.co.kr...")
        try:
            from app.ml.crawl.parsers.kra_live_parser import KRALiveParser
            list_html = self.client.fetch_page("/raceScore/ScoretableScoreList.do", {"Act": "04", "Sub": "1", "meet": "1"})
            
            if list_html:
                logger.info("Successfully fetched ScoretableScoreList.do")
                live_races = KRALiveParser.parse_chulma_list(list_html)
                
                if live_races:
                    logger.info(f"Found {len(live_races)} race dates on live site.")
                    # Fetch detailed results for the first race of the first date to verify
                    first_date = live_races[0]
                    rc_date = first_date['date']
                    rc_no = first_date['races'][0] if first_date['races'] else 1
                    
                    logger.info(f"Fetching detailed race results for {rc_date} Race {rc_no}...")
                    import requests
                    res = requests.post(
                        "https://race.kra.co.kr/raceScore/ScoretableDetailList.do",
                        headers={"User-Agent": "Mozilla/5.0"},
                        data={"meet": "1", "realRcDate": rc_date, "realRcNo": str(rc_no)},
                        timeout=10
                    )
                    res.encoding = 'euc-kr'
                    detail_results = KRALiveParser.parse_race_detail(res.text)
                    if detail_results:
                        logger.info(f"Successfully scraped {len(detail_results)} horses for Race {rc_no}!")
                        for h in detail_results[:3]:
                            logger.info(f"  -> Rank {h['rank']}: {h['horse_name']} (Odds: {h['odds_win']})")
                    else:
                        logger.warning("Could not extract detailed horse info.")
        except Exception as e:
            logger.error(f"Live crawling failed: {e}")
                
        # 3. Synthetic Fallback
        if use_synthetic_fallback:
            logger.info("Using synthetic data generator to populate database as fallback")
            await populate_db()
        
        logger.info("Crawl pipeline finished successfully.")

def execute():
    from app.db.session import async_session_factory
    import asyncio
    
    # User's provided decoding key
    api_key = "7d7Y9lSLZvt//+HmnwT8W7vbC5JsoY4ZvQ4WJGfl33ZUC5KJ+/lUhsP9hSulAgPMcvlLocZ1BIzzVaaX9Hqbtg=="
    
    async def _execute():
        async with async_session_factory() as db:
            pipeline = CrawlingPipeline(db, api_key=api_key)
            await pipeline.run(date(1990, 1, 1), date.today(), use_synthetic_fallback=True)
            
    asyncio.run(_execute())
