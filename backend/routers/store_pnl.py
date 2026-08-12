from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from schemas.common import BoundedCode64, BoundedText120, MonthStr, StrictApiModel

from auth import AuthClaims, require_auth
from composition import build_store_pnl_service
from permissions import can_access_management, require_privileged_access
from privileged_access import STORE_PNL_ACCESS_GROUPS_ENV, has_configured_group
from services.store_pnl import StorePnlService

router = APIRouter(prefix="/api/store-pnl", tags=["store-pnl"])


class PnlMetricsResponse(StrictApiModel):
    revenue: Decimal
    cogs: Decimal
    gross_margin: Decimal
    operating_costs: Decimal
    ebitda: Decimal
    depreciation: Decimal
    ebit: Decimal


class PnlMonthResponse(StrictApiModel):
    month: str
    has_actual: bool
    has_estimated: bool


class PnlPermissionsResponse(StrictApiModel):
    can_view: bool


class PnlMonthsResponse(StrictApiModel):
    months: list[PnlMonthResponse]


class PnlStoreOptionResponse(StrictApiModel):

    company_name: str
    site_code: str
    location: str
    regional: str | None = None
    scope_company: str | None = None


class PnlStoresResponse(StrictApiModel):
    stores: list[PnlStoreOptionResponse]


class PnlRegionsResponse(StrictApiModel):
    regions: list[str]


class PnlAnnualItemResponse(StrictApiModel):

    year: str
    store_count: int
    month_count: int
    is_estimated: bool
    revenue: Decimal
    cogs: Decimal
    gross_margin: Decimal
    operating_costs: Decimal
    ebitda: Decimal
    depreciation: Decimal
    ebit: Decimal


class PnlAnnualResponse(StrictApiModel):
    annual: list[PnlAnnualItemResponse]


class PnlMonthlyItemResponse(StrictApiModel):

    month: str
    is_estimated: bool
    revenue: Decimal
    cogs: Decimal
    gross_margin: Decimal
    operating_costs: Decimal
    ebitda: Decimal
    depreciation: Decimal
    ebit: Decimal


class PnlStoreResponse(StrictApiModel):

    company: str
    site_code: str
    source_site_code: str
    location: str
    regional: str | None = None
    has_estimates: bool
    revenue: Decimal
    cogs: Decimal
    gross_margin: Decimal
    operating_costs: Decimal
    ebitda: Decimal
    depreciation: Decimal
    ebit: Decimal


class PnlReconciliationResponse(StrictApiModel):
    month: str
    pnl_revenue: Decimal
    retail_sales_gross: Decimal
    retail_sales_net: Decimal
    difference_to_net: Decimal
    pnl_to_net_sales_pct: Decimal | None = None


class PnlOverviewResponse(StrictApiModel):

    start_month: str
    end_month: str
    company: str | None = None
    site_code: str | None = None
    site_company: str | None = None
    regional: str | None = None
    summary: PnlMetricsResponse
    monthly: list[PnlMonthlyItemResponse] = Field(default_factory=list)
    categories: dict[str, Decimal] = Field(default_factory=dict)
    stores: list[PnlStoreResponse] = Field(default_factory=list)
    reconciliation: list[PnlReconciliationResponse] = Field(default_factory=list)


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


def parse_month(value: MonthStr) -> date:
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


get_service = build_store_pnl_service


@router.get("/permissions", response_model=PnlPermissionsResponse)
async def pnl_permissions(claims: AuthClaims = Depends(require_auth)) -> dict[str, bool]:
    """Capability display endpoint; it intentionally does not emit audit events."""
    return {"can_view": can_access_store_pnl(claims)}


@router.get("/months", response_model=PnlMonthsResponse)
async def months(
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    return {"months": await service.months()}


def validate_company(company: str | None) -> None:
    if company not in (None, "Mobicell", "Mobiup"):
        raise HTTPException(status_code=422, detail="Companie P&L invalida.")


@router.get("/stores", response_model=PnlStoresResponse)
async def stores(
    company: BoundedText120 | None = Query(default=None),
    regional: BoundedText120 | None = Query(default=None),
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    validate_company(company)
    return {"stores": await service.stores(company, regional)}


@router.get("/regions", response_model=PnlRegionsResponse)
async def regions(
    company: BoundedText120 | None = Query(default=None),
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    validate_company(company)
    return {"regions": await service.regions(company)}


@router.get("/annual", response_model=PnlAnnualResponse)
async def annual(
    company: BoundedText120 | None = Query(default=None),
    site_code: BoundedCode64 | None = Query(default=None),
    site_company: BoundedText120 | None = Query(default=None),
    regional: BoundedText120 | None = Query(default=None),
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    validate_company(company)
    validate_company(site_company)
    return {"annual": await service.annual(company, site_code, site_company, regional)}


@router.get("/overview", response_model=PnlOverviewResponse)
async def overview(
    start_month: MonthStr,
    end_month: MonthStr,
    company: BoundedText120 | None = Query(default=None),
    site_code: BoundedCode64 | None = Query(default=None),
    site_company: BoundedText120 | None = Query(default=None),
    regional: BoundedText120 | None = Query(default=None),
    _claims: AuthClaims = Depends(require_store_pnl_owner),
    service: StorePnlService = Depends(get_service),
):
    validate_company(company)
    validate_company(site_company)
    start, end = parse_month(start_month), parse_month(end_month)
    if start > end:
        raise HTTPException(status_code=422, detail="Intervalul P&L este inversat.")
    return await service.overview(start, end, company, site_code, site_company, regional)
