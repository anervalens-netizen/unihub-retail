from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from composition import build_agents_service
from schemas.common import BoundedListItem100, BoundedText120, MonthStr, MonthWindowStr
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
from services.agents import AgentsService

router = APIRouter(prefix="/api/agents", tags=["agents"])

get_agents_service = build_agents_service


@router.get("/overview", response_model=AgentsOverviewResponse)
async def get_agents_overview(
    selected_month: MonthStr,
    firma: BoundedText120 | None = Query(None),
    regional: BoundedText120 | None = Query(None),
    asm: BoundedText120 | None = Query(None),
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    agent: list[BoundedListItem100] | None = Query(None, max_length=100),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agents_overview(selected_month, firma, regional, asm, site_code, agent)


@router.get("/movement", response_model=AgentMovementResponse)
async def get_agents_movement(
    selected_month: MonthStr,
    firma: BoundedText120 | None = Query(None),
    regional: BoundedText120 | None = Query(None),
    asm: BoundedText120 | None = Query(None),
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    agent: list[BoundedListItem100] | None = Query(None, max_length=100),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agents_movement(selected_month, firma, regional, asm, site_code, agent)


@router.get("/list", response_model=AgentListResponse)
async def get_agents_list(
    selected_month: MonthStr,
    search: BoundedText120 | None = Query(None),
    firma: BoundedText120 | None = Query(None),
    regional: BoundedText120 | None = Query(None),
    asm: BoundedText120 | None = Query(None),
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agents_list(selected_month, search, firma, regional, asm, site_code)


@router.get("/evaluation", response_model=AgentEvaluationResponse)
async def get_agent_evaluation(
    month: MonthStr | None = Query(None),
    months: MonthWindowStr | None = Query(None),
    firma: BoundedText120 | None = Query(None),
    asm: BoundedText120 | None = Query(None),
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agent_evaluation(month, months, firma, asm, site_code)


@router.get("/evaluation-v2", response_model=AgentEvaluationV2Response)
async def get_agent_evaluation_v2(
    month: MonthStr | None = Query(None),
    months: MonthWindowStr | None = Query(None),
    firma: BoundedText120 | None = Query(None),
    asm: BoundedText120 | None = Query(None),
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agent_evaluation_v2(month, months, firma, asm, site_code)


@router.get("/profile", response_model=AgentProfileResponse)
async def get_agent_profile(
    agent: BoundedText120,
    selected_month: MonthStr,
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agent_profile(agent, selected_month)


@router.get("/history", response_model=AgentHistoryResponse)
async def get_agent_history(
    agent: BoundedText120,
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_agent_history(agent)


@router.get("/stores-coverage", response_model=StoreCoverageResponse)
async def get_stores_coverage(
    selected_month: MonthStr,
    firma: BoundedText120 | None = Query(None),
    regional: BoundedText120 | None = Query(None),
    asm: BoundedText120 | None = Query(None),
    svc: AgentsService = Depends(get_agents_service),
):
    return await svc.get_stores_coverage(selected_month, firma, regional, asm)
