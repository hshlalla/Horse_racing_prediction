import logging
import requests
from typing import Dict, Any, Optional
from urllib.parse import unquote

logger = logging.getLogger(__name__)

class KRAOpenAPIClient:
    """
    Client for data.go.kr API187 (한국마사회 경마경주정보).
    Endpoint: http://apis.data.go.kr/B551015/API187/HorseRaceInfo
    """
    def __init__(self, service_key: str):
        # The requests library usually works better with the decoded key, 
        # or we explicitly pass the exact encoded key in the URL.
        self.service_key = unquote(service_key) if '%' in service_key else service_key
        self.base_url = "http://apis.data.go.kr/B551015/API187/HorseRaceInfo"
        self.session = requests.Session()

    def get_race_info(self, rc_date: str, page_no: int = 1, num_of_rows: int = 100) -> Optional[Dict[str, Any]]:
        """
        Fetches race info for a given date (YYYYMMDD).
        """
        params = {
            "serviceKey": self.service_key,
            "pageNo": str(page_no),
            "numOfRows": str(num_of_rows),
            "rc_date": rc_date,
            "_type": "json" # Force JSON if supported by the API
        }
        
        try:
            logger.info(f"Calling OpenAPI for {rc_date} (Page {page_no})")
            response = self.session.get(self.base_url, params=params, timeout=10)
            
            # Often OpenAPI returns 200 OK but the body contains an error message if the key is unauthorized
            response.raise_for_status()
            
            # API might return XML by default if `_type=json` is ignored. 
            # We'll try parsing JSON first.
            try:
                data = response.json()
                return data
            except ValueError:
                logger.warning("Failed to parse JSON. API might have returned XML or an error page.")
                logger.debug(f"Response: {response.text[:200]}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"OpenAPI Request failed: {e}")
            return None

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    
    # Test with provided decoding key
    key = "7d7Y9lSLZvt//+HmnwT8W7vbC5JsoY4ZvQ4WJGfl33ZUC5KJ+/lUhsP9hSulAgPMcvlLocZ1BIzzVaaX9Hqbtg=="
    client = KRAOpenAPIClient(key)
    res = client.get_race_info("20240101")
    print("API Response:", res)
