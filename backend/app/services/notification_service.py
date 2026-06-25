from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.users import Device

async def register_device(db: AsyncSession, user_id: int, fcm_token: str, platform: str) -> Device:
    existing = await db.execute(select(Device).where(Device.fcm_token == fcm_token))
    device = existing.scalar_one_or_none()
    
    if device:
        if device.user_id != user_id:
            device.user_id = user_id
            await db.commit()
        return device

    device = Device(user_id=user_id, fcm_token=fcm_token, platform=platform)
    db.add(device)
    await db.commit()
    return device
