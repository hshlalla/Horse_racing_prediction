from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.deps import get_db, get_current_user
from app.db.models.users import User
from app.services import notification_service

router = APIRouter(prefix="/devices", tags=["notifications"])

class DeviceRegistrationRequest(BaseModel):
    fcm_token: str
    platform: str = "android"

@router.post("", status_code=201)
async def register_device(
    body: DeviceRegistrationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await notification_service.register_device(db, current_user.id, body.fcm_token, body.platform)
    return {"status": "ok"}
