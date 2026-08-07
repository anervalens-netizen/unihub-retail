from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from schemas.common import MonthStr
from schemas.agents import (
    AgentsOverviewResponse,
    AgentMovementResponse,
    AgentListResponse,
    AgentProfileResponse,
    AgentHistoryResponse,
    AgentEvaluationResponse,
    AgentEvaluationV2Response,
    StoreCoverageResponse,
)
from repositories.agents import AgentsRepository
from services.agents import AgentsService

router = APIRouter(prefix="/api/agents", tags=["agents"])

async def get_agents_service() -> AgentsService:
    pool = await get_pool()
    repo = AgentsRepository(pool)
    return AgentsService(repo)


@router.get("/overview", response_model=AgentsOverviewResponse)
async def get_agents_overview(
    selected_month: MonthStr = Query(...),
    firma: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    site_code: str | None = Query(None),
    agent: str | None = Query(None),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agents_overview(selected_month, firma, regional, asm, site_code, agent)


@router.get("/movement", response_model=AgentMovementResponse)
async def get_agents_movement(
    selected_month: MonthStr = Query(...),
    firma: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    site_code: str | None = Query(None),
    agent: str | None = Query(None),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agents_movement(selected_month, firma, regional, asm, site_code, agent)


@router.get("/list", response_model=AgentListResponse)
async def get_agents_list(
    selected_month: MonthStr = Query(...),
    search: str | None = Query(None),
    firma: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    site_code: str | None = Query(None),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agents_list(selected_month, search, firma, regional, asm, site_code)


@router.get("/evaluation", response_model=AgentEvaluationResponse)
async def get_agent_evaluation(
    month: MonthStr | None = Query(None),
    months: str | None = Query(None),
    firma: str | None = Query(None),
    asm: str | None = Query(None),
    site_code: str | None = Query(None),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agent_evaluation(month, months, firma, asm, site_code)


@router.get("/evaluation-v2", response_model=AgentEvaluationV2Response)
async def get_agent_evaluation_v2(
    month: MonthStr | None = Query(None),
    months: str | None = Query(None),
    firma: str | None = Query(None),
    asm: str | None = Query(None),
    site_code: str | None = Query(None),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agent_evaluation_v2(month, months, firma, asm, site_code)


@router.get("/profile", response_model=AgentProfileResponse)
async def get_agent_profile(
    agent: str = Query(...),
    selected_month: MonthStr = Query(...),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agent_profile(agent, selected_month)


@router.get("/history", response_model=AgentHistoryResponse)
async def get_agent_history(
    agent: str = Query(...),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agent_history(agent)


@router.get("/stores-coverage", response_model=StoreCoverageResponse)
async def get_stores_coverage(
    selected_month: MonthStr = Query(...),
    firma: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_stores_coverage(selected_month, firma, regional, asm)
