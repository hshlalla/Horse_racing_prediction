from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.deps import get_db
from app.core.errors import error_response
from app.core.rate_limit import auth_rate_limit
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "rt"
COOKIE_OPTS = dict(httponly=True, secure=True, samesite="lax", max_age=60 * 60 * 24 * 30)


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE_NAME, token, **COOKIE_OPTS)


@router.post("/register", status_code=201, response_model=TokenResponse)
async def register(
    body: AuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(auth_rate_limit),
):
    try:
        _, access, refresh_raw = await auth_service.register(db, body.email, body.password)
    except auth_service.EmailTaken:
        return error_response("EMAIL_TAKEN", "Email already registered", 409)
    _set_refresh_cookie(response, refresh_raw)
    return TokenResponse(access_token=access)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: AuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(auth_rate_limit),
):
    try:
        _, access, refresh_raw = await auth_service.login(db, body.email, body.password)
    except auth_service.InvalidCredentials:
        return error_response("INVALID_CREDENTIALS", "Invalid email or password", 401)
    _set_refresh_cookie(response, refresh_raw)
    return TokenResponse(access_token=access)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    rt: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(auth_rate_limit),
):
    if rt is None:
        return error_response("NO_REFRESH_TOKEN", "Refresh token missing", 401)
    try:
        access, new_raw = await auth_service.refresh(db, rt)
    except auth_service.InvalidRefreshToken:
        return error_response("INVALID_REFRESH_TOKEN", "Refresh token invalid or expired", 401)
    _set_refresh_cookie(response, new_raw)
    return TokenResponse(access_token=access)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    rt: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(auth_rate_limit),
):
    if rt:
        await auth_service.logout(db, rt)
    response.delete_cookie(COOKIE_NAME)
