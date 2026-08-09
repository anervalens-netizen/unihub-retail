from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import Field
from schemas.common import StrictApiModel

from composition import build_salarii_service
from services.salarii import SalariiService
from salary_identity import get_salary_person_id_key
from schemas.salarii import SalaryAgentsSummaryResponse, SalaryHistoryResponse, SalaryRecordPublic
from services.salarii import InvalidSalaryPersonId, UnknownSalaryPerson

router = APIRouter(
    prefix="/salarii",
    tags=["salarii"],
)
logger = logging.getLogger(__name__)


class SalaryExportAudit(StrictApiModel):
    export_kind: Literal["store_summary", "monthly_trend", "agents_page"]
    row_count: int = Field(ge=0, le=5000)


class SalaryCompanyTotal(StrictApiModel):

    company: str | None = None
    name: str | None = None
    total: float


class SalaryOverviewResponse(StrictApiModel):

    total: float | None = None
    by_company: list[SalaryCompanyTotal] = Field(default_factory=list)
    record_count: int | None = None
    agent_count: int | None = None
    agent_month_count: int | None = None
    avg_agent_month_count: int | None = None
    avg_salary: float | None = None
    months_span: tuple[int, int, int, int] | None = None


class SalaryEvolutionPoint(StrictApiModel):
    month: str
    total: float
    mobicell: float
    mobiup: float


class SalaryComparisonItem(StrictApiModel):

    site_code: str
    locatie: str | None = None
    company_name: str
    total_salary: float
    agent_count: int
    avg_agent_count: int
    avg_salary: float
    total_sales: float
    ratio: float


class SalarySummaryResponse(StrictApiModel):
    month: str | None = None
    items: list[SalaryComparisonItem] = Field(default_factory=list)


class SalaryTrendPoint(StrictApiModel):

    month: str
    total_salary: float
    total_sales: float
    agent_count: int
    avg_agent_count: int
    avg_salary: float
    by_company: dict[str, object] = Field(default_factory=dict)


class SalaryStoreOption(StrictApiModel):
    site_code: str
    locatie: str | None = None


async def get_salarii_service() -> SalariiService:
    return await build_salarii_service()


async def get_identity_salarii_service() -> SalariiService:
    try:
        key = get_salary_person_id_key()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="salary identity is unavailable",
        ) from exc
    return await build_salarii_service(person_id_key=key)


@router.get(
    "/overview",
    response_model=SalaryOverviewResponse,
    response_model_exclude_unset=True,
)
async def salarii_overview(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    svc: SalariiService = Depends(get_salarii_service),
):
    return await svc.get_overview(company_name, site_code, regional, asm)


@router.get("/evolution", response_model=list[SalaryEvolutionPoint])
async def salarii_evolution(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    svc: SalariiService = Depends(get_salarii_service),
):
    return await svc.get_evolution(company_name, site_code, regional, asm)


@router.get("/agents/summary", response_model=SalaryAgentsSummaryResponse)
async def agents_summary(
    q: str | None = Query(None),
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    svc: SalariiService = Depends(get_identity_salarii_service),
):
    return await svc.get_agents_summary(q, company_name, site_code, regional, asm, year, month, limit, offset)


@router.get("/agents/{person_id}/history", response_model=SalaryHistoryResponse)
async def agent_history(
    person_id: str = Path(..., pattern=r"^sp1_[0-9a-f]{64}$"),
    svc: SalariiService = Depends(get_identity_salarii_service),
):
    try:
        return await svc.get_agent_history(person_id)
    except InvalidSalaryPersonId as exc:
        raise HTTPException(status_code=422, detail="invalid salary person_id") from exc
    except UnknownSalaryPerson as exc:
        raise HTTPException(status_code=404, detail="salary agent not found") from exc


@router.get("/agents/history-by-retail-code", response_model=SalaryHistoryResponse)
async def agent_history_by_retail_code(
    agent_code: str = Query(...),
    site_code: str = Query(...),
    svc: SalariiService = Depends(get_identity_salarii_service),
):
    return await svc.get_agent_history_by_retail_code(
        agent_code=agent_code,
        site_code=site_code,
    )


@router.get("/summary", response_model=SalarySummaryResponse)
async def salarii_summary(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    svc: SalariiService = Depends(get_salarii_service),
):
    return await svc.get_summary(company_name, site_code, regional, asm, year, month)


@router.get("/trend", response_model=list[SalaryTrendPoint])
async def salarii_trend(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    svc: SalariiService = Depends(get_salarii_service),
):
    return await svc.get_trend(company_name, site_code, regional, asm)


@router.get("/stores", response_model=list[SalaryStoreOption])
async def salarii_stores(
    company_name: str | None = Query(None),
    svc: SalariiService = Depends(get_salarii_service),
):
    return await svc.get_stores(company_name)


@router.get("/records", response_model=list[SalaryRecordPublic])
async def list_records(
    company_name: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    site_code: str | None = Query(None),
    limit: int = Query(100, le=2000),
    offset: int = Query(0),
    svc: SalariiService = Depends(get_identity_salarii_service),
):
    return await svc.get_records(company_name, year, month, site_code, limit, offset)


@router.post(
    "/audit/export",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def audit_salary_export(
    body: SalaryExportAudit,
    request: Request,
) -> Response:
    claims = request.state.salary_claims
    logger.info(
        "sensitive_export resource=salarii subject=%s kind=%s rows=%d",
        claims.sub,
        body.export_kind,
        body.row_count,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
