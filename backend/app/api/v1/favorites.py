import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.api.deps import get_db, get_current_user
from app.db.models.users import User
from app.services import favorite_service
from pydantic import BaseModel
from app.core.errors import error_response

router = APIRouter(prefix="/favorites", tags=["favorites"])

class FavoriteHorse(BaseModel):
    id: int
    name: str

class FavoriteResponseItem(BaseModel):
    horse: FavoriteHorse
    created_at: datetime.datetime

class FavoriteListResponse(BaseModel):
    items: List[FavoriteResponseItem]

class AddFavoriteRequest(BaseModel):
    horse_id: int

@router.get("", response_model=FavoriteListResponse)
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    favorites = await favorite_service.get_user_favorites(db, current_user.id)
    items = []
    for f in favorites:
        items.append(FavoriteResponseItem(
            horse=FavoriteHorse(id=f.horse.id, name=f.horse.name),
            created_at=f.created_at
        ))
    return FavoriteListResponse(items=items)

@router.post("", status_code=201)
async def add_favorite(
    body: AddFavoriteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    favorite = await favorite_service.add_favorite(db, current_user.id, body.horse_id)
    if not favorite:
        return error_response("ALREADY_FAVORITED", "Horse already favorited", 400)
    return {"status": "ok"}

@router.delete("/{horse_id}", status_code=204)
async def remove_favorite(
    horse_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    removed = await favorite_service.remove_favorite(db, current_user.id, horse_id)
    if not removed:
        return error_response("NOT_FOUND", "Favorite not found", 404)
    return None
