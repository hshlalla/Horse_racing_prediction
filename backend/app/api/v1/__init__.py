from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.races import router as races_router
from app.api.v1.predictions import router as predictions_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.meta import router as meta_router
from app.api.v1.ml import router as ml_router
from app.api.v1.horses import router as horses_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(races_router)
router.include_router(predictions_router)
router.include_router(favorites_router)
router.include_router(notifications_router)
router.include_router(meta_router)
router.include_router(ml_router)
router.include_router(horses_router)

