from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_pool
from dependencies import get_current_user, require_role

router = APIRouter(prefix="/api/hr", tags=["hr"])

ALLOWED_ROLES = require_role("admin", "management")
ALL_ROLES = get_current_user


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


import asyncio
import sqlite3

VISITS_DB_PATH = "/opt/Mobiup/unihub/data/visits/visits.db"


def _query_visits_by_asm(year_month: str) -> list[dict]:
    """Execuție sincronă — apelată din run_in_executor."""
    con = sqlite3.connect(VISITS_DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.execute(
        """
        SELECT
            asm,
            COUNT(*) AS total_visits,
            ROUND(AVG(completion_pct), 1) AS avg_completion,
            ROUND(AVG(durata_vizita_ore), 2) AS avg_duration,
            COUNT(DISTINCT magazin) AS distinct_stores,
            ROUND(AVG(
                (COALESCE(curatenie, 0) + COALESCE(imagine, 0) + COALESCE(uniforma, 0)
                 + COALESCE(afise, 0) + COALESCE(produse_promo, 0)) * 20.0
            ), 1) AS checklist_score,
            ROUND(
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
                1
            ) AS approved_pct
        FROM visits
        WHERE substr(data_raport, 1, 7) = ?
          AND asm IS NOT NULL AND asm != ''
        GROUP BY asm
        """,
        (year_month,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def _query_visits_history(asm_name: str, months: int) -> list[dict]:
    """Execuție sincronă — istoricul vizitelor per ASM."""
    con = sqlite3.connect(VISITS_DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.execute(
        """
        SELECT
            substr(data_raport, 1, 7) AS month,
            COUNT(*) AS total_visits,
            ROUND(AVG(completion_pct), 1) AS avg_completion,
            ROUND(AVG(durata_vizita_ore), 2) AS avg_duration
        FROM visits
        WHERE asm = ?
          AND data_raport >= date('now', ? || ' months')
        GROUP BY substr(data_raport, 1, 7)
        ORDER BY month
        """,
        (asm_name, f"-{months}"),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


async def get_asm_performance(conn: Any, month: str, regional: str | None) -> list[dict]:
    """Profil combinat per ASM: vânzări din PostgreSQL + vizite din SQLite."""
    pg_rows = await conn.fetch(
        """
        SELECT
            s.asm,
            s.regional,
            SUM(ram.total_sales)                                         AS total_sales,
            COALESCE(SUM(st.target_value), 0)                           AS total_target,
            COUNT(DISTINCT ram.site_code)                                AS active_stores,
            COUNT(DISTINCT ram.agent)                                    AS active_agents,
            ROUND(
                SUM(ram.receipt_2plus_count) * 100.0
                / NULLIF(SUM(ram.receipt_count), 0),
                1
            )                                                            AS pct_bon2acc,
            ROUND(
                SUM(ram.focus_quantity) * 100.0
                / NULLIF(SUM(ram.total_quantity), 0),
                1
            )                                                            AS pct_focus
        FROM reporting_agent_month ram
        JOIN stores s ON s.site_code = ram.site_code
        LEFT JOIN store_targets st
            ON st.site_code = ram.site_code AND st.import_month = ram.import_month
        WHERE ram.import_month = $1
          AND ($2::text IS NULL OR s.regional = $2)
        GROUP BY s.asm, s.regional
        ORDER BY total_sales DESC
        """,
        month,
        regional,
    )

    loop = asyncio.get_event_loop()
    sqlite_rows = await loop.run_in_executor(None, _query_visits_by_asm, month)
    sqlite_map = {r["asm"]: r for r in sqlite_rows}

    result = []
    for pg in pg_rows:
        asm = pg["asm"]
        sq = sqlite_map.get(asm, {})
        total_sales = float(pg["total_sales"] or 0)
        total_target = float(pg["total_target"] or 0)
        result.append({
            "asm": asm,
            "regional": pg["regional"],
            "total_sales": total_sales,
            "total_target": total_target,
            "target_pct": round(total_sales / total_target * 100, 1) if total_target > 0 else None,
            "active_stores": pg["active_stores"],
            "active_agents": pg["active_agents"],
            "pct_bon2acc": float(pg["pct_bon2acc"] or 0),
            "pct_focus": float(pg["pct_focus"] or 0),
            "total_visits": sq.get("total_visits", 0),
            "avg_completion": sq.get("avg_completion"),
            "avg_duration": sq.get("avg_duration"),
            "distinct_stores_visited": sq.get("distinct_stores", 0),
            "checklist_score": sq.get("checklist_score"),
            "approved_pct": sq.get("approved_pct"),
        })
    return result


async def get_asm_performance_history(conn: Any, asm_name: str, months: int = 6) -> list[dict]:
    """Trend lunar per ASM: vânzări (PG) + vizite (SQLite) — ultimele N luni."""
    pg_rows = await conn.fetch(
        """
        SELECT
            ram.import_month,
            SUM(ram.total_sales)              AS total_sales,
            COALESCE(SUM(st.target_value), 0) AS total_target,
            COUNT(DISTINCT ram.site_code)      AS active_stores
        FROM reporting_agent_month ram
        JOIN stores s ON s.site_code = ram.site_code
        LEFT JOIN store_targets st
            ON st.site_code = ram.site_code AND st.import_month = ram.import_month
        WHERE s.asm = $1
          AND ram.import_month >= to_char(now() - ($2 || ' months')::interval, 'YYYY-MM')
        GROUP BY ram.import_month
        ORDER BY ram.import_month
        """,
        asm_name,
        str(months),
    )

    loop = asyncio.get_event_loop()
    sqlite_hist = await loop.run_in_executor(None, _query_visits_history, asm_name, months)
    sqlite_map = {r["month"]: r for r in sqlite_hist}

    # Forecast factor pentru luna curentă (parțială)
    current_month = await conn.fetchrow(
        """
        SELECT
            COALESCE(BOOL_OR(snap.is_month_final), true) AS is_final,
            EXTRACT(DAY FROM MAX(rid.sale_date))::INT AS last_sale_day,
            EXTRACT(DAY FROM (
                date_trunc('month', now()) + INTERVAL '1 month - 1 day'
            ))::INT AS days_in_month
        FROM import_snapshots snap
        LEFT JOIN (
            SELECT MAX(sale_date) AS sale_date
            FROM reporting_item_day
            WHERE import_month = to_char(now(), 'YYYY-MM')
        ) rid ON true
        WHERE snap.import_month = to_char(now(), 'YYYY-MM')
        """,
    )
    if current_month and not current_month["is_final"] and current_month["last_sale_day"]:
        last_day = int(current_month["last_sale_day"])
        days_in_month = int(current_month["days_in_month"] or last_day)
        forecast_factor = days_in_month / last_day if last_day > 0 else 1.0
    else:
        forecast_factor = 1.0
    this_month = __import__("datetime").date.today().strftime("%Y-%m")

    result = []
    for pg in pg_rows:
        m = pg["import_month"]
        sq = sqlite_map.get(m, {})
        total_sales = float(pg["total_sales"] or 0)
        total_target = float(pg["total_target"] or 0)
        is_current = m == this_month and forecast_factor > 1.001
        forecast_sales = total_sales * forecast_factor if is_current else total_sales
        forecast_target_pct = round(forecast_sales / total_target * 100, 1) if total_target > 0 else None
        result.append({
            "month": m,
            "total_sales": total_sales,
            "total_target": total_target,
            "target_pct": round(total_sales / total_target * 100, 1) if total_target > 0 else None,
            "forecast_sales": forecast_sales,
            "forecast_target_pct": forecast_target_pct,
            "is_forecast": is_current,
            "active_stores": pg["active_stores"],
            "total_visits": sq.get("total_visits", 0),
            "avg_completion": sq.get("avg_completion"),
            "avg_duration": sq.get("avg_duration"),
        })
    return result


@router.get("/asm-performance")
async def get_asm_perf(
    month: str = Query(...),
    regional: str | None = Query(None),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    effective_regional = regional
    if user.get("role") == "management" and not regional:
        effective_regional = user.get("full_name")
    async with pool.acquire() as conn:
        return await get_asm_performance(conn, month, effective_regional)


@router.get("/asm-performance/{asm_name}/history")
async def get_asm_perf_history(
    asm_name: str,
    months: int = Query(6, ge=1, le=24),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await get_asm_performance_history(conn, asm_name, months)


@router.get("/users")
async def get_assignable_users(user: dict = Depends(ALL_ROLES)):
    """Lista utilizatorilor activi cu rol ASM sau TL — pentru dropdown assignee în Tasks."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT full_name, role, username
            FROM users
            WHERE is_active = true AND role IN ('asm', 'tl')
            ORDER BY role, full_name
            """,
        )
        return [dict(r) for r in rows]
