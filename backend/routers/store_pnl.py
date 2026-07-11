from __future__ import annotations

import os
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import AuthClaims, require_auth
from db.connection import get_pool
from repositories.store_pnl import StorePnlRepository
from services.store_pnl import StorePnlService

router = APIRouter(prefix="/api/store-pnl", tags=["store-pnl"])
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DEFAULT_OWNER_EMAILS = "aner.valens@gmail.com"


def can_access_store_pnl(claims: AuthClaims) -> bool:
    configured = os.getenv(
        "PNL_OWNER_EMAILS",
        os.getenv("TARGET_CALCULATOR_FINALIZER_EMAILS", DEFAULT_OWNER_EMAILS),
    )
    allowed = {email.strip().casefold() for email in configured.split(",") if email.strip()}
    return claims.email.strip().casefold() in allowed


def require_store_pnl_owner(claims: AuthClaims = Depends(require_auth)) -> AuthClaims:
    if not can_access_store_pnl(claims):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="P&L este disponibil doar proprietarului configurat.")
    return claims


def parse_month(value: str) -> date:
    if not MONTH_PATTERN.match(value):
        raise HTTPException(status_code=422, detail="Luna trebuie sa fie in format YYYY-MM.")
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


async def get_service() -> StorePnlService:
    return StorePnlService(StorePnlRepository(await get_pool()))


@router.get("/months")
async def months(
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    return {"months": await service.months()}


@router.get("/overview")
async def overview(
    start_month: str = Query(...),
    end_month: str = Query(...),
    company: str | None = Query(default=None),
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    if company not in (None, "Mobicell", "Mobiup"):
        raise HTTPException(status_code=422, detail="Companie P&L invalida.")
    start, end = parse_month(start_month), parse_month(end_month)
    if start > end:
        raise HTTPException(status_code=422, detail="Intervalul P&L este inversat.")
    return await service.overview(start, end, company)
