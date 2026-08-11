from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import Field
from schemas.common import StrictApiModel

from composition import build_export_operations_service, build_salarii_service
from domain.export_operations import ExportOperationCapacityError
from models import ExportOperationResponse, ExportOperationUnavailableResponse
from rate_limits import REPORT_EXPORT_LIMIT, rate_limit
from schemas.salarii import SalaryExportRequest
from services.export_operations import ExportOperationsService
from services.exports import ExportValidationError
from services.salarii import SalariiService
from salary_identity import get_salary_person_id_key
from schemas.salarii import SalaryAgentsSummaryResponse, SalaryHistoryResponse, SalaryRecordPublic
from services.salarii import InvalidSalaryPersonId, UnknownSalaryPerson

router = APIRouter(
    prefix="/salarii",
    tags=["salarii"],
)
class SalaryCompanyTotal(StrictApiModel):

    company: str | None = None
    name: str | None = None
    total: Decimal


class SalaryOverviewResponse(StrictApiModel):

    total: Decimal | None = None
    by_company: list[SalaryCompanyTotal] = Field(default_factory=list)
    record_count: int | None = None
    agent_count: int | None = None
    agent_month_count: int | None = None
    avg_agent_month_count: int | None = None
    avg_salary: Decimal | None = None
    months_span: tuple[int, int, int, int] | None = None


class SalaryEvolutionPoint(StrictApiModel):
    month: str
    total: Decimal
    mobicell: Decimal
    mobiup: Decimal


class SalaryComparisonItem(StrictApiModel):

    site_code: str | None
    locatie: str | None = None
    company_name: str
    total_salary: Decimal
    agent_count: int
    avg_agent_count: int
    avg_salary: Decimal
    total_sales: Decimal
    ratio: Decimal


class SalarySummaryResponse(StrictApiModel):
    month: str | None = None
    items: list[SalaryComparisonItem] = Field(default_factory=list)


class SalaryTrendPoint(StrictApiModel):

    month: str
    total_salary: Decimal
    total_sales: Decimal
    agent_count: int
    avg_agent_count: int
    avg_salary: Decimal
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
    site_code: list[str] | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    svc: SalariiService = Depends(get_salarii_service),
):
    return await svc.get_overview(company_name, site_code, regional, asm)


@router.get("/evolution", response_model=list[SalaryEvolutionPoint])
async def salarii_evolution(
    company_name: str | None = Query(None),
    site_code: list[str] | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    svc: SalariiService = Depends(get_salarii_service),
):
    return await svc.get_evolution(company_name, site_code, regional, asm)


@router.get("/agents/summary", response_model=SalaryAgentsSummaryResponse)
async def agents_summary(
    q: str | None = Query(None),
    company_name: str | None = Query(None),
    site_code: list[str] | None = Query(None),
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
    site_code: list[str] | None = Query(None),
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
    site_code: list[str] | None = Query(None),
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
    site_code: list[str] | None = Query(None),
    limit: int = Query(100, le=2000),
    offset: int = Query(0),
    svc: SalariiService = Depends(get_identity_salarii_service),
):
    return await svc.get_records(company_name, year, month, site_code, limit, offset)


@router.post(
    "/exports/operations",
    response_model=ExportOperationResponse,
    responses={
        400: {"description": "Cerere salariala invalida"},
        409: {"description": "Capacitate activa epuizata"},
        503: {
            "model": ExportOperationUnavailableResponse,
            "description": "Publicare ARQ indisponibila sau neconfirmata",
        },
    },
)
async def create_salary_export_operation(
    body: SalaryExportRequest,
    request: Request,
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: ExportOperationsService = Depends(build_export_operations_service),
) -> ExportOperationResponse:
    claims = request.state.salary_claims
    try:
        return await svc.reserve_salary(
            body.model_dump(mode="json"),
            requested_by_sub=claims.sub,
        )
    except ExportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExportOperationCapacityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exista deja prea multe exporturi active.",
        ) from exc
