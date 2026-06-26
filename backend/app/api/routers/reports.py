import json
import os
from fastapi import APIRouter, HTTPException

router = APIRouter()

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "roi_cache.json")

@router.get("/roi")
async def get_roi_report():
    if not os.path.exists(CACHE_PATH):
        # Return empty data if not yet generated
        return {
            "overall": {
                "WIN": {"investment": 0, "return": 0, "hits": 0, "total_races": 0},
                "QUINELLA": {"investment": 0, "return": 0, "hits": 0, "total_races": 0},
                "TRIO": {"investment": 0, "return": 0, "hits": 0, "total_races": 0}
            },
            "monthly": []
        }
    
    try:
        with open(CACHE_PATH, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
