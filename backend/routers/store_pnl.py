from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import AuthClaims, require_auth
from db.connection import get_pool
from permissions import can_access_management, require_privileged_access
from privileged_access import STORE_PNL_ACCESS_GROUPS_ENV, has_configured_group
from repositories.store_pnl import StorePnlRepository
from services.store_pnl import StorePnlService

router = APIRouter(prefix="/api/store-pnl", tags=["store-pnl"])
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def can_access_store_pnl(claims: AuthClaims) -> bool:
    return (
        can_access_management(claims)
        and has_configured_group(claims.groups, STORE_PNL_ACCESS_GROUPS_ENV)
    )


def require_store_pnl_owner(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    return require_privileged_access(
        request=request,
        claims=claims,
        allowed=can_access_store_pnl(claims),
        resource="store_pnl",
        detail="Accesul la P&L nu este disponibil pentru acest utilizator.",
        fallback_route="/api/store-pnl",
    )


def parse_month(value: str) -> date:
    if not MONTH_PATTERN.match(value):
        raise HTTPException(status_code=422, detail="Luna trebuie sa fie in format YYYY-MM.")
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


async def get_service() -> StorePnlService:
    return StorePnlService(StorePnlRepository(await get_pool()))


@router.get("/permissions")
async def pnl_permissions(claims: AuthClaims = Depends(require_auth)) -> dict[str, bool]:
    """Capability display endpoint; it intentionally does not emit audit events."""
    return {"can_view": can_access_store_pnl(claims)}


@router.get("/months")
async def months(
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    return {"months": await service.months()}


def validate_company(company: str | None) -> None:
    if company not in (None, "Mobicell", "Mobiup"):
        raise HTTPException(status_code=422, detail="Companie P&L invalida.")


@router.get("/stores")
async def stores(
    company: str | None = Query(default=None),
    regional: str | None = Query(default=None),
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    validate_company(company)
    return {"stores": await service.stores(company, regional)}


@router.get("/regions")
async def regions(
    company: str | None = Query(default=None),
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    validate_company(company)
    return {"regions": await service.regions(company)}


@router.get("/annual")
async def annual(
    company: str | None = Query(default=None),
    site_code: str | None = Query(default=None, max_length=100),
    site_company: str | None = Query(default=None),
    regional: str | None = Query(default=None),
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    validate_company(company)
    validate_company(site_company)
    return {"annual": await service.annual(company, site_code, site_company, regional)}


@router.get("/overview")
async def overview(
    start_month: str = Query(...),
    end_month: str = Query(...),
    company: str | None = Query(default=None),
    site_code: str | None = Query(default=None, max_length=100),
    site_company: str | None = Query(default=None),
    regional: str | None = Query(default=None),
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    validate_company(company)
    validate_company(site_company)
    start, end = parse_month(start_month), parse_month(end_month)
    if start > end:
        raise HTTPException(status_code=422, detail="Intervalul P&L este inversat.")
    return await service.overview(start, end, company, site_code, site_company, regional)
