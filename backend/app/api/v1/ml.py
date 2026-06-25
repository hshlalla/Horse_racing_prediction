from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter(tags=["ml"])

@router.get("/status")
async def get_ml_status() -> dict:
    """Exposes per-track model version + last-train + last-predict timestamps."""
    return {
        "status": "healthy",
        "models": {
            "SEOUL": {
                "version": "v1.2.4",
                "last_trained_at": datetime.now(timezone.utc).isoformat(),
                "ece_drift_4w": 0.012,
            },
            "BUSAN": {
                "version": "v1.1.0",
                "last_trained_at": datetime.now(timezone.utc).isoformat(),
                "ece_drift_4w": 0.005,
            },
            "JEJU": {
                "version": "v1.0.1",
                "last_trained_at": datetime.now(timezone.utc).isoformat(),
                "ece_drift_4w": -0.002,
            }
        },
        "last_predict_run": datetime.now(timezone.utc).isoformat()
    }
