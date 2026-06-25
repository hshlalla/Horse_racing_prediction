from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.races import router as races_router
from app.api.v1.predictions import router as predictions_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.notifications import router as notifications_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(races_router)
router.include_router(predictions_router)
router.include_router(favorites_router)
router.include_router(notifications_router)
