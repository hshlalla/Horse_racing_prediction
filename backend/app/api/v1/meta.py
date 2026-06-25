from fastapi import APIRouter
from typing import List, Dict

router = APIRouter(tags=["meta"])

@router.get("/tracks")
async def get_tracks() -> Dict[str, List[Dict[str, str]]]:
    """Return a list of available tracks."""
    return {
        "items": [
            {"id": "SEOUL", "name": "Seoul", "surface": "Sand"},
            {"id": "BUSAN", "name": "Busan", "surface": "Sand"},
            {"id": "JEJU", "name": "Jeju", "surface": "Sand"},
        ]
    }

@router.get("/jockeys")
async def get_jockeys() -> Dict[str, List[Dict[str, str]]]:
    """Return a list of jockeys."""
    return {
        "items": [
            {"id": "1", "name": "Kim Dong Soo"},
            {"id": "2", "name": "Park Tae Jong"},
            {"id": "3", "name": "Moon Se Young"},
        ]
    }
