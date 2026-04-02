from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from db.connection import get_pool
from dependencies import get_current_user
from routers.dashboard_filters import where_clauses
from models import (
    AgentsOverviewResponse,
    AgentMovementPoint,
    AgentMovementResponse,
    AgentListItem,
    AgentListResponse,
    AgentProfileResponse,
    AgentHistoryPoint,
    AgentHistoryResponse,
    StoreCoverageResponse,
    StoreCoverageItem,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def month_index_expr(col: str) -> str:
    return f"(CAST(SUBSTRING({col}, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING({col}, 6, 2) AS INTEGER))"


def get_prev_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


@router.get("/overview", response_model=AgentsOverviewResponse)
async def get_agents_overview(
    selected_month: str = Query(...),
    firma: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    site_code: str | None = Query(None),
    agent: str | None = Query(None),
    user: dict[str, Any] = Depends(get_current_user),
):
    pool = await get_pool()
    prev_month = get_prev_month(selected_month)

    clauses, params = where_clauses(
        user, selected_month, firma, regional, asm, site_code, agent, include_agent=True
    )
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""

    # 1. Snapshot: Active, New, Reactivated
    # We also need Retention and LeftThisMonth
    # For retention we need to know who was active last month under SAME filters

    # We need filters without the month for some queries
    base_clauses = [c for c in clauses if "import_month =" not in c]
    base_where = "WHERE " + " AND ".join(base_clauses) if base_clauses else ""

    query = f"""
        WITH 
        current_active AS (
            SELECT DISTINCT agent FROM reporting_agent_month {where_sql}
        ),
        prev_active AS (
            SELECT DISTINCT agent FROM reporting_agent_month 
            {base_where} {" AND " if base_where else "WHERE "} import_month = ${len(params) + 1}
        ),
        stats AS (
            SELECT 
                COUNT(DISTINCT ca.agent)::INT as active_count,
                COUNT(DISTINCT ca.agent) FILTER (WHERE lc.is_new)::INT as new_count,
                COUNT(DISTINCT ca.agent) FILTER (WHERE lc.is_reactivated)::INT as reactivated_count,
                COUNT(DISTINCT ca.agent) FILTER (WHERE 
                    (SELECT COUNT(*)::INT FROM reporting_agent_lifecycle_month l2 WHERE l2.agent = ca.agent AND l2.import_month <= $1) > 6
                )::INT as stable_count
            FROM current_active ca
            JOIN reporting_agent_lifecycle_month lc ON lc.agent = ca.agent AND lc.import_month = $1
        ),
        retention AS (
            SELECT 
                COUNT(DISTINCT pa.agent)::INT as prev_active_count,
                COUNT(DISTINCT pa.agent) FILTER (WHERE ca.agent IS NOT NULL)::INT as stayed_count,
                COUNT(DISTINCT pa.agent) FILTER (WHERE ca.agent IS NULL)::INT as left_count
            FROM prev_active pa
            LEFT JOIN current_active ca ON ca.agent = pa.agent
        ),
        global_stats AS (
            SELECT 
                COUNT(DISTINCT agent)::INT as total_unique,
                AVG(active_months)::NUMERIC as avg_seniority
            FROM (
                SELECT agent, COUNT(*)::NUMERIC as active_months
                FROM reporting_agent_lifecycle_month
                WHERE agent IN (SELECT agent FROM reporting_agent_month {base_where} {" AND " if base_where else "WHERE "} import_month <= $1)
                AND import_month <= $1
                GROUP BY agent
            ) g
        )
        SELECT * FROM stats, retention, global_stats
    """

    churned_clauses = [
        c.replace("import_month = $1", "import_month <= $1") for c in clauses
    ]
    churn_where_sql = (
        "WHERE " + " AND ".join(churned_clauses) if churned_clauses else ""
    )

    selected_idx = month_index_expr("$1")
    last_seen_idx = month_index_expr("last_seen")

    churn_query = f"""
        WITH historical_agents AS (
            SELECT agent, MAX(import_month) as last_seen
            FROM reporting_agent_month
            {churn_where_sql}
            GROUP BY agent
        )
        SELECT COUNT(*)::INT as churned_total_count
        FROM historical_agents
        WHERE {selected_idx} - {last_seen_idx} >= 2
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params, prev_month)
        churn_row = await conn.fetchrow(churn_query, *params)

    active_count = row["active_count"] if row else 0
    new_count = row["new_count"] if row else 0
    reactivated_count = row["reactivated_count"] if row else 0
    left_this_month = row["left_count"] if row else 0
    prev_active_count = row["prev_active_count"] if row else 0
    stable_count = row["stable_count"] if row else 0
    total_unique = row["total_unique"] if row else 0
    avg_seniority = row["avg_seniority"] if row else 0

    retention_rate = None
    if prev_active_count > 0:
        retention_rate = (
            Decimal(row["stayed_count"]) / Decimal(prev_active_count) * 100
        ).quantize(Decimal("0.1"))

    stability_rate = None
    if active_count > 0:
        stability_rate = (Decimal(stable_count) / Decimal(active_count) * 100).quantize(
            Decimal("0.1")
        )

    return AgentsOverviewResponse(
        active_count=active_count,
        new_count=new_count,
        reactivated_count=reactivated_count,
        left_this_month_count=left_this_month,
        retention_rate=retention_rate,
        total_unique_agents=total_unique,
        avg_seniority_months=Decimal(avg_seniority).quantize(Decimal("0.1"))
        if avg_seniority
        else None,
        stability_rate=stability_rate,
        churned_total_count=churn_row["churned_total_count"] if churn_row else 0,
    )


@router.get("/movement", response_model=AgentMovementResponse)
async def get_agents_movement(
    selected_month: str = Query(...),
    firma: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    site_code: str | None = Query(None),
    agent: str | None = Query(None),
    user: dict[str, Any] = Depends(get_current_user),
):
    pool = await get_pool()

    # We use a trick: where_clauses with no month filter, so we get the base filters.
    # Actually, where_clauses requires a month. We can just pass selected_month, and replace 'import_month = $1' with 'import_month <= $1'
    clauses, params = where_clauses(
        user, selected_month, firma, regional, asm, site_code, agent, include_agent=True
    )

    # modify the month clause
    where_sql = "WHERE " + " AND ".join(
        [
            c.replace("import_month = $1", "st.import_month <= $1")
            if "import_month" in c
            else c
            for c in clauses
        ]
    )

    query = f"""
        SELECT 
            st.import_month as month,
            COUNT(DISTINCT lc.agent)::INT as active,
            COUNT(DISTINCT lc.agent) FILTER (WHERE lc.is_new)::INT as new,
            COUNT(DISTINCT lc.agent) FILTER (WHERE lc.is_reactivated)::INT as reactivated
        FROM reporting_agent_month st
        JOIN reporting_agent_lifecycle_month lc 
          ON lc.agent = st.agent AND lc.import_month = st.import_month
        {where_sql}
        GROUP BY st.import_month
        ORDER BY st.import_month ASC
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    history = [
        AgentMovementPoint(
            month=str(row["month"]),
            active=row["active"],
            new=row["new"],
            reactivated=row["reactivated"],
            churned=0,  # placeholder for now
            net_growth=row["new"],  # new - churned (churned=0 placeholder)
        )
        for row in rows
    ]

    return AgentMovementResponse(history=history)


@router.get("/list", response_model=AgentListResponse)
async def get_agents_list(
    selected_month: str = Query(...),
    search: str | None = Query(None),
    firma: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    site_code: str | None = Query(None),
    user: dict[str, Any] = Depends(get_current_user),
):
    pool = await get_pool()

    # We use where_clauses with include_agent=False
    clauses, params = where_clauses(
        user, selected_month, firma, regional, asm, site_code, None, include_agent=False
    )

    # Modify for <= selected_month
    scope_clauses = [
        c.replace("import_month = $1", "import_month <= $1") for c in clauses
    ]
    scope_where = "WHERE " + " AND ".join(scope_clauses) if scope_clauses else ""

    selected_idx = month_index_expr("$1")
    last_seen_idx = month_index_expr("MAX(import_month)")

    search_clause = ""
    if search:
        search_clause = f" AND p.agent ILIKE ${len(params) + 1}"
        params.append(f"%{search}%")

    query = f"""
        WITH scope_agents AS (
            SELECT agent, MAX(import_month) as last_seen
            FROM reporting_agent_month
            {scope_where}
            GROUP BY agent
        ),
        top_store AS (
            SELECT DISTINCT ON (agent)
                agent,
                locatie AS store_name
            FROM reporting_agent_month
            WHERE import_month = $1
            ORDER BY agent, total_sales DESC
        )
        SELECT
            p.agent,
            ts.store_name,
            (lc.import_month IS NOT NULL) AS active_in_month,
            COALESCE(lc.is_new, false) AS is_new,
            COALESCE(lc.is_reactivated, false) AS is_reactivated,
            COALESCE(lc.total_sales, 0) AS total_sales,
            COALESCE(lc.total_quantity, 0) AS total_quantity,
            CASE
                WHEN {selected_idx} - {month_index_expr("sa.last_seen")} >= 2 THEN 'churned'
                WHEN {selected_idx} - {month_index_expr("sa.last_seen")} = 1 THEN 'inactive_recent'
                ELSE 'active'
            END as current_status
        FROM scope_agents sa
        JOIN reporting_agent_profile p ON p.agent = sa.agent
        LEFT JOIN reporting_agent_lifecycle_month lc
          ON lc.agent = sa.agent AND lc.import_month = $1
        LEFT JOIN top_store ts ON ts.agent = sa.agent
        WHERE 1=1 {search_clause}
        ORDER BY active_in_month DESC, lc.total_sales DESC NULLS LAST, p.agent ASC
        LIMIT 200
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    items = [
        AgentListItem(
            agent=row["agent"],
            store_name=row["store_name"],
            active_in_month=row["active_in_month"],
            is_new=row["is_new"],
            is_reactivated=row["is_reactivated"],
            total_sales=row["total_sales"],
            total_quantity=row["total_quantity"],
            current_status=row["current_status"],
        )
        for row in rows
    ]

    return AgentListResponse(items=items)


@router.get("/profile", response_model=AgentProfileResponse)
async def get_agent_profile(
    agent: str = Query(...),
    selected_month: str = Query(...),
    user: dict[str, Any] = Depends(get_current_user),
):
    pool = await get_pool()

    selected_idx = month_index_expr("$2")
    last_seen_idx = month_index_expr("last_seen_month")

    query = f"""
        SELECT 
            agent,
            first_seen_month,
            last_seen_month,
            active_months_count,
            distinct_store_count,
            distinct_firma_count,
            distinct_regional_count,
            distinct_asm_count,
            GREATEST({selected_idx} - {last_seen_idx}, 0)::INT AS months_since_last_seen,
            reactivation_count,
            longest_active_streak,
            career_total_sales,
            career_total_quantity,
            avg_monthly_sales,
            best_month,
            best_month_sales,
            CASE
                WHEN {selected_idx} - {last_seen_idx} >= 2 THEN 'churned'
                WHEN {selected_idx} - {last_seen_idx} = 1 THEN 'inactive_recent'
                ELSE 'active'
            END AS current_status
        FROM reporting_agent_profile
        WHERE agent = $1
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, agent, selected_month)

    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")

    return AgentProfileResponse(**dict(row))


@router.get("/history", response_model=AgentHistoryResponse)
async def get_agent_history(
    agent: str = Query(...),
    user: dict[str, Any] = Depends(get_current_user),
):
    pool = await get_pool()

    query = """
        SELECT 
            import_month as month,
            total_sales,
            total_quantity,
            receipt_count,
            active_store_count,
            is_active
        FROM reporting_agent_lifecycle_month
        WHERE agent = $1
        ORDER BY import_month ASC
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, agent)

    history = [AgentHistoryPoint(**dict(row)) for row in rows]

    return AgentHistoryResponse(history=history)


@router.get("/stores-coverage", response_model=StoreCoverageResponse)
async def get_stores_coverage(
    selected_month: str = Query(...),
    firma: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    user: dict[str, Any] = Depends(get_current_user),
):
    pool = await get_pool()

    # Base filters
    params: list[Any] = [selected_month]
    clauses: list[str] = []

    if firma and firma != "Toate":
        params.append(firma)
        clauses.append(f"s.firma = ${len(params)}")
    if regional and regional != "Toti":
        params.append(regional)
        clauses.append(f"s.regional = ${len(params)}")
    if asm and asm != "Toti":
        params.append(asm)
        clauses.append(f"s.asm = ${len(params)}")

    # TL scope
    from routers.shared import build_scope_filter

    scope_sql, scope_params = build_scope_filter(
        user, base_alias="s", param_start=len(params) + 1
    )
    if scope_sql:
        clauses.append(scope_sql)
        params.extend(scope_params)

    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""

    selected_idx = month_index_expr("$1")

    query = f"""
        WITH store_agents AS (
            SELECT site_code, COUNT(DISTINCT agent)::INT as agent_count
            FROM reporting_agent_month
            WHERE import_month = $1
            GROUP BY site_code
        ),
        store_status AS (
            SELECT 
                s.site_code,
                s.locatie,
                s.firma,
                s.regional,
                s.asm,
                COALESCE(sa.agent_count, 0) as agent_count,
                CASE 
                    WHEN s.last_seen_month = $1 THEN 
                        CASE WHEN COALESCE(sa.agent_count, 0) > 0 THEN 'covered' ELSE 'uncovered' END
                    WHEN {selected_idx} - {month_index_expr("s.last_seen_month")} > 3 THEN 'closed'
                    ELSE 'inactive'
                END as status
            FROM stores s
            LEFT JOIN store_agents sa ON sa.site_code = s.site_code
            {where_sql}
        )
        SELECT * FROM store_status
        ORDER BY agent_count ASC, locatie ASC
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    items = [StoreCoverageItem(**dict(row)) for row in rows]

    active_stores = [i for i in items if i.status in ("covered", "uncovered")]
    uncovered_stores = [i for i in items if i.status == "uncovered"]
    closed_stores = [i for i in items if i.status == "closed"]

    return StoreCoverageResponse(
        active_stores_count=len(active_stores),
        uncovered_stores_count=len(uncovered_stores),
        closed_stores_count=len(closed_stores),
        items=items,
    )
