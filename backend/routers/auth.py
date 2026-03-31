from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from db.connection import get_pool
from dependencies import get_current_user
from models import LoginRequest, LoginResponse, UserResponse
from services.auth_service import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            """
            SELECT id, username, password_hash, role, full_name, is_active
            FROM users
            WHERE lower(username) = lower($1)
            """,
            payload.username,
        )
        if user is None:
            logger.warning("Login failed: unknown username=%s", payload.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credențiale invalide",
            )
        if not user["is_active"]:
            logger.warning("Login failed: inactive username=%s", payload.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cont inactiv",
            )
        if not verify_password(payload.password, user["password_hash"]):
            logger.warning("Login failed: invalid password username=%s", payload.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credențiale invalide",
            )

        await conn.execute("UPDATE users SET last_login_at = now() WHERE id = $1", user["id"])

    token = create_access_token(user["id"], user["username"], user["role"])
    return LoginResponse(
        access_token=token,
        role=user["role"],
        full_name=user["full_name"],
    )


@router.get("/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)) -> UserResponse:
    return UserResponse(**user)
