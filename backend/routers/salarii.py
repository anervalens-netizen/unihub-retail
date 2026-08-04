from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field

from db.connection import get_pool
from repositories.salarii import SalariiRepository
from services.salarii import SalariiService
from salary_identity import get_salary_person_id_key
from schemas.salarii import SalaryAgentsSummaryResponse, SalaryHistoryResponse, SalaryRecordPublic
from services.salarii import InvalidSalaryPersonId, UnknownSalaryPerson

router = APIRouter(
    prefix="/salarii",
    tags=["salarii"],
)
logger = logging.getLogger(__name__)


class SalaryExportAudit(BaseModel):
    export_kind: Literal["store_summary", "monthly_trend", "agents_page"]
    row_count: int = Field(ge=0, le=5000)


async def get_salarii_service() -> SalariiService:
    pool = await get_pool()
    repo = SalariiRepository(pool)
    return SalariiService(repo)


async def get_identity_salarii_service() -> SalariiService:
    pool = await get_pool()
    try:
        key = get_salary_person_id_key()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="salary identity is unavailable") from exc
    return SalariiService(SalariiRepository(pool), key)


@router.get("/overview")
async def salarii_overview(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    svc: SalariiService = Depends(get_salarii_service),
):
    return await svc.get_overview(company_name, site_code, regional, asm)


@router.get("/evolution")
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


@router.get("/summary")
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


@router.get("/trend")
async def salarii_trend(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    svc: SalariiService = Depends(get_salarii_service),
):
    return await svc.get_trend(company_name, site_code, regional, asm)


@router.get("/stores")
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
