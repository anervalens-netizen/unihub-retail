from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from db.connection import get_pool
from repositories.hr import HrRepository
from services.hr import HrService

router = APIRouter(prefix="/api/hr", tags=["hr"])


class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    start_date: str
    end_date: str
    leave_type: str
    notes: str | None = None


class LeaveStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


async def get_hr_service() -> HrService:
    pool = await get_pool()
    repo = HrRepository(pool)
    return HrService(repo)


@router.get("/leave-requests")
async def get_leave_requests(
    status: str | None = Query(None),
    agent_name: str | None = Query(None),
    svc: HrService = Depends(get_hr_service),
):
    return await svc.list_leave_requests(status, agent_name)


@router.post("/leave-requests")
async def post_leave_request(
    body: LeaveRequestCreate,
    svc: HrService = Depends(get_hr_service),
):
    return await svc.create_leave_request(body.model_dump())


@router.patch("/leave-requests/{request_id}")
async def patch_leave_request(
    request_id: int,
    body: LeaveStatusUpdate,
    svc: HrService = Depends(get_hr_service),
):
    return await svc.update_leave_status(request_id, body.status)


@router.get("/performance/{agent_name}")
async def get_performance(
    agent_name: str,
    svc: HrService = Depends(get_hr_service),
):
    return await svc.get_agent_performance(agent_name)


@router.get("/asm-performance")
async def get_asm_perf(
    month: str = Query(...),
    regional: str | None = Query(None),
    svc: HrService = Depends(get_hr_service),
):
    return await svc.get_asm_performance(month, regional)


@router.get("/asm-performance/{asm_name}/history")
async def get_asm_perf_history(
    asm_name: str,
    months: int = Query(6, ge=1, le=24),
    svc: HrService = Depends(get_hr_service),
):
    return await svc.get_asm_performance_history(asm_name, months)
