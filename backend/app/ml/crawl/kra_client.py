import requests
import time
import logging

logger = logging.getLogger(__name__)

class KRAClient:
    """
    Robust HTTP client for scraping KRA endpoints.
    Implements exponential backoff and session management.
    """
    def __init__(self, base_url="https://race.kra.co.kr"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "KRA_Quant_Bot/1.0",
            "Accept-Language": "ko-KR,ko;q=0.9"
        })

    def fetch_page(self, path: str, params: dict = None, retries=3) -> str:
        """
        Fetches an HTML page with exponential backoff.
        """
        url = f"{self.base_url}{path}"
        delay = 1.0

        for attempt in range(retries):
            try:
                logger.info(f"Fetching {url} with params {params}")
                # We add a 1 second delay to avoid stressing the KRA server
                time.sleep(1.0)
                
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                
                # The KRA site uses euc-kr encoding
                response.encoding = 'euc-kr'
                return response.text
                
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt == retries - 1:
                    logger.error(f"All {retries} attempts failed.")
                    return ""

                time.sleep(delay)
                delay *= 2

        return ""
