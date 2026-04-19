from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from db.connection import get_pool
from services.forecast import get_forecast_factor

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
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await list_leave_requests(conn, status, agent_name)


@router.post("/leave-requests")
async def post_leave_request(body: LeaveRequestCreate):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await create_leave_request(conn, body.model_dump())


@router.patch("/leave-requests/{request_id}")
async def patch_leave_request(
    request_id: int,
    body: LeaveStatusUpdate,
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status invalid. Folosește 'approved' sau 'rejected'.")
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await update_leave_status(conn, request_id, body.status)


@router.get("/performance/{agent_name}")
async def get_performance(agent_name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await get_agent_performance(conn, agent_name)


async def get_asm_performance(conn: Any, month: str, regional: str | None) -> list[dict]:
    pg_rows = await conn.fetch(
        """
        WITH asm_targets AS (
            SELECT s.asm, SUM(st.target_value) AS total_target
            FROM store_targets st
            JOIN stores s ON s.site_code = st.site_code
            WHERE st.import_month = $1
            GROUP BY s.asm
        )
        SELECT
            s.asm,
            s.regional,
            SUM(ram.total_sales)                                         AS total_sales,
            COALESCE(at.total_target, 0)                                 AS total_target,
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
        LEFT JOIN asm_targets at ON at.asm = s.asm
        WHERE ram.import_month = $1
          AND ($2::text IS NULL OR s.regional = $2)
        GROUP BY s.asm, s.regional, at.total_target
        ORDER BY total_sales DESC
        """,
        month,
        regional,
    )

    snapshot_rows = await conn.fetch(
        "SELECT * FROM visits_snapshot WHERE month = $1", month
    )
    sqlite_map = {r["asm"]: dict(r) for r in snapshot_rows}

    forecast_factor = await get_forecast_factor(conn, month)
    is_partial = forecast_factor > 1.001

    result = []
    for pg in pg_rows:
        asm = pg["asm"]
        sq = sqlite_map.get(asm, {})
        total_sales = float(pg["total_sales"] or 0)
        total_target = float(pg["total_target"] or 0)
        forecast_sales = total_sales * forecast_factor
        result.append({
            "asm": asm,
            "regional": pg["regional"],
            "total_sales": total_sales,
            "total_target": total_target,
            "target_pct": round(total_sales / total_target * 100, 1) if total_target > 0 else None,
            "forecast_sales": forecast_sales,
            "forecast_target_pct": round(forecast_sales / total_target * 100, 1) if total_target > 0 else None,
            "is_forecast": is_partial,
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
    pg_rows = await conn.fetch(
        """
        WITH asm_month_targets AS (
            SELECT st.import_month, SUM(st.target_value) AS total_target
            FROM store_targets st
            JOIN stores s ON s.site_code = st.site_code
            WHERE s.asm = $1
              AND st.import_month >= to_char(now() - ($2 || ' months')::interval, 'YYYY-MM')
            GROUP BY st.import_month
        )
        SELECT
            ram.import_month,
            SUM(ram.total_sales)               AS total_sales,
            COALESCE(amt.total_target, 0)      AS total_target,
            COUNT(DISTINCT ram.site_code)       AS active_stores
        FROM reporting_agent_month ram
        JOIN stores s ON s.site_code = ram.site_code
        LEFT JOIN asm_month_targets amt ON amt.import_month = ram.import_month
        WHERE s.asm = $1
          AND ram.import_month >= to_char(now() - ($2 || ' months')::interval, 'YYYY-MM')
        GROUP BY ram.import_month, amt.total_target
        ORDER BY ram.import_month
        """,
        asm_name,
        str(months),
    )

    snapshot_hist = await conn.fetch(
        """
        SELECT * FROM visits_snapshot
        WHERE asm = $1
          AND month >= to_char(now() - ($2 || ' months')::interval, 'YYYY-MM')
        ORDER BY month
        """,
        asm_name,
        str(months),
    )
    sqlite_map = {r["month"]: dict(r) for r in snapshot_hist}

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
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await get_asm_performance(conn, month, regional)


@router.get("/asm-performance/{asm_name}/history")
async def get_asm_perf_history(
    asm_name: str,
    months: int = Query(6, ge=1, le=24),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await get_asm_performance_history(conn, asm_name, months)
