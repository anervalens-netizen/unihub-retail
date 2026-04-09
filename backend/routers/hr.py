from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_pool
from dependencies import require_role

router = APIRouter(prefix="/api/hr", tags=["hr"])

ALLOWED_ROLES = require_role("admin", "management")


class LeaveRequestCreate(BaseModel):
    agent_name: str
    start_date: str   # YYYY-MM-DD
    end_date: str     # YYYY-MM-DD
    leave_type: str   # 'odihna' | 'medical' | 'altul'
    notes: str | None = None


class LeaveStatusUpdate(BaseModel):
    status: str       # 'approved' | 'rejected'


async def create_leave_request(conn: Any, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO leave_requests (agent_name, start_date, end_date, leave_type, notes)
        VALUES ($1, $2::text::date, $3::text::date, $4, $5)
        RETURNING id, agent_name, start_date::text, end_date::text, leave_type, notes,
                  status, created_at::text, updated_at::text
        """,
        data["agent_name"],
        data["start_date"],
        data["end_date"],
        data["leave_type"],
        data.get("notes"),
    )
    return dict(row)


async def update_leave_status(conn: Any, request_id: int, status: str) -> dict:
    row = await conn.fetchrow(
        """
        UPDATE leave_requests
        SET status = $1, updated_at = now()
        WHERE id = $2
        RETURNING id, agent_name, start_date::text, end_date::text, leave_type, notes,
                  status, created_at::text, updated_at::text
        """,
        status,
        request_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Cerere negăsită")
    return dict(row)


async def list_leave_requests(conn: Any, status: str | None, agent_name: str | None) -> list[dict]:
    clauses = []
    params: list[Any] = []
    idx = 1
    if status:
        clauses.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if agent_name:
        clauses.append(f"agent_name ILIKE ${idx}")
        params.append(f"%{agent_name}%")
        idx += 1
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await conn.fetch(
        f"""
        SELECT id, agent_name, start_date::text, end_date::text, leave_type, notes,
               status, created_at::text, updated_at::text
        FROM leave_requests
        {where}
        ORDER BY created_at DESC
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def get_agent_performance(conn: Any, agent_name: str) -> list[dict]:
    """Agregat lunar per agent: vânzări, % target — ultimele 12 luni."""
    rows = await conn.fetch(
        """
        SELECT
            ram.import_month,
            SUM(ram.total_sales) AS total_value,
            SUM(ram.receipt_count) AS transaction_count,
            SUM(ram.working_days) AS active_days,
            COALESCE(
                ROUND(
                    SUM(ram.total_sales)::numeric /
                    NULLIF(
                        (SELECT SUM(st.target_value)
                         FROM store_targets st
                         WHERE st.import_month = ram.import_month
                           AND st.site_code = ram.site_code),
                        0
                    ) * 100,
                    1
                ),
                0
            ) AS target_pct
        FROM reporting_agent_month ram
        WHERE ram.agent = $1
          AND ram.import_month >= to_char(now() - interval '12 months', 'YYYY-MM')
        GROUP BY ram.import_month, ram.site_code
        ORDER BY ram.import_month
        """,
        agent_name,
    )
    return [dict(r) for r in rows]


@router.get("/leave-requests")
async def get_leave_requests(
    status: str | None = Query(None),
    agent_name: str | None = Query(None),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await list_leave_requests(conn, status, agent_name)


@router.post("/leave-requests")
async def post_leave_request(body: LeaveRequestCreate, user: dict = Depends(ALLOWED_ROLES)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await create_leave_request(conn, body.model_dump())


@router.patch("/leave-requests/{request_id}")
async def patch_leave_request(
    request_id: int,
    body: LeaveStatusUpdate,
    user: dict = Depends(ALLOWED_ROLES),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status invalid. Folosește 'approved' sau 'rejected'.")
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await update_leave_status(conn, request_id, body.status)


@router.get("/performance/{agent_name}")
async def get_performance(agent_name: str, user: dict = Depends(ALLOWED_ROLES)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await get_agent_performance(conn, agent_name)
