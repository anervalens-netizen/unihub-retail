from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from models import (
    AgentsOverviewResponse,
    AgentMovementPoint,
    AgentMovementResponse,
    AgentListItem,
    AgentListResponse,
    AgentProfileResponse,
    AgentHistoryPoint,
    AgentHistoryResponse,
    AgentEvaluationOption,
    AgentEvaluationResponse,
    AgentEvaluationRow,
    StoreCoverageResponse,
    StoreCoverageItem,
)
from repositories.agents import AgentsRepository
from services.filters import base_filter_values, scoped_clauses, where_clauses

def month_index_expr(col: str) -> str:
    return f"(CAST(SUBSTRING({col}, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING({col}, 6, 2) AS INTEGER))"


def get_prev_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


class AgentsService:
    def __init__(self, repo: AgentsRepository):
        self.repo = repo

    async def get_agents_overview(
        self, selected_month: str, firma: str | None, regional: str | None, asm: str | None, site_code: str | None, agent: str | None
    ) -> AgentsOverviewResponse:
        prev_month = get_prev_month(selected_month)
        clauses, params = where_clauses(
            selected_month, firma, regional, asm, site_code, agent, include_agent=True
        )
        where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
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

        row = await self.repo.get_overview_stats(query, params, prev_month)
        churn_count = await self.repo.get_churn_count(churn_query, params)

        active_count = row["active_count"] if row else 0
        new_count = row["new_count"] if row else 0
        reactivated_count = row["reactivated_count"] if row else 0
        left_this_month = row["left_count"] if row else 0
        prev_active_count = row["prev_active_count"] if row else 0
        stable_count = row["stable_count"] if row else 0
        total_unique = row["total_unique"] if row else 0
        avg_seniority = row["avg_seniority"] if row else 0

        retention_rate = None
        if prev_active_count > 0 and row is not None:
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
            churned_total_count=churn_count,
        )

    async def get_agent_evaluation(
        self,
        month: str | None,
        firma: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> AgentEvaluationResponse:
        def pct_points(value: Decimal | None, thresholds: tuple[Decimal, Decimal, Decimal]) -> int:
            if value is None:
                return 0
            if value >= thresholds[0]:
                return 3
            if value >= thresholds[1]:
                return 2
            if value >= thresholds[2]:
                return 1
            return 0

        def qualifier(points: int) -> str:
            if points == 18:
                return "Excelent"
            if points >= 14:
                return "Foarte Bun"
            if points >= 10:
                return "Bun"
            if points >= 6:
                return "Mediu"
            return "Scazut"

        query = """
            WITH current_month AS (
                SELECT MAX(import_month) AS month
                FROM reporting_agent_month
            ),
            current_agents AS (
                SELECT DISTINCT ON (ram.agent)
                    ram.agent,
                    ram.firma,
                    ram.site_code,
                    ram.locatie,
                    ram.regional,
                    ram.asm
                FROM reporting_agent_month ram
                JOIN current_month cm ON cm.month = ram.import_month
                WHERE ram.agent IS NOT NULL
                  AND TRIM(ram.agent) != ''
                  AND ram.agent != '-'
                  AND ram.agent NOT ILIKE 'TR%'
                ORDER BY ram.agent, ram.working_days DESC, ram.total_sales DESC, ram.site_code
            ),
            monthly_base AS (
                SELECT
                    ram.import_month AS month,
                    ca.firma,
                    ca.site_code,
                    ca.locatie,
                    ca.regional,
                    ca.asm,
                    ram.agent,
                    ram.total_sales,
                    ram.total_quantity,
                    ram.focus_quantity,
                    ram.receipt_count,
                    ram.receipt_2plus_count,
                    ram.working_days,
                    COALESCE(st.target_value, 0) AS store_target,
                    SUM(ram.working_days) OVER (PARTITION BY ram.import_month, ram.site_code) AS store_working_days
                FROM reporting_agent_month ram
                JOIN current_agents ca ON ca.agent = ram.agent
                LEFT JOIN store_targets st
                  ON st.import_month = ram.import_month
                 AND st.site_code = ram.site_code
                WHERE ram.import_month BETWEEN '2026-01' AND '2026-05'
                  AND ($1::TEXT IS NULL OR ram.import_month = $1)
                  AND ($2::TEXT IS NULL OR ca.firma = $2)
                  AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
                  AND ($4::TEXT IS NULL OR ca.site_code = $4)
                  AND ram.agent IS NOT NULL
                  AND TRIM(ram.agent) != ''
                  AND ram.agent != '-'
                  AND ram.agent NOT ILIKE 'TR%'
            ),
            monthly_targets AS (
                SELECT
                    *,
                    CASE
                        WHEN store_working_days > 0
                        THEN ROUND(store_target * working_days / store_working_days, 2)
                        ELSE 0
                    END AS target_value,
                    CASE WHEN working_days > 0 THEN ROUND(total_sales / working_days, 2) END AS daily_average,
                    CASE WHEN total_quantity > 0 THEN ROUND(total_sales / total_quantity, 2) END AS value_reper,
                    CASE WHEN receipt_count > 0 THEN ROUND(receipt_2plus_count * 100.0 / receipt_count, 2) END AS bonuri_pct,
                    CASE WHEN total_quantity > 0 THEN ROUND(focus_quantity * 100.0 / total_quantity, 2) END AS focus_pct
                FROM monthly_base
            ),
            agent_period AS (
                SELECT
                    CASE WHEN $1::TEXT IS NULL THEN '2026-01..2026-05' ELSE month END AS month,
                    firma,
                    site_code,
                    locatie,
                    regional,
                    asm,
                    agent,
                    COALESCE(SUM(total_sales), 0) AS total_sales,
                    COALESCE(SUM(total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(focus_quantity), 0)::INT AS focus_quantity,
                    COALESCE(SUM(receipt_count), 0)::INT AS receipt_count,
                    COALESCE(SUM(receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                    COALESCE(SUM(working_days), 0)::INT AS working_days,
                    COALESCE(SUM(store_target), 0) AS store_target,
                    COALESCE(SUM(store_working_days), 0)::INT AS store_working_days,
                    COALESCE(SUM(target_value), 0) AS target_value
                FROM monthly_targets
                GROUP BY
                    CASE WHEN $1::TEXT IS NULL THEN '2026-01..2026-05' ELSE month END,
                    firma,
                    site_code,
                    locatie,
                    regional,
                    asm,
                    agent
            ),
            agent_metrics AS (
                SELECT
                    *,
                    CASE WHEN target_value > 0 THEN ROUND(total_sales * 100.0 / target_value, 2) END AS target_pct,
                    CASE WHEN working_days > 0 THEN ROUND(total_sales / working_days, 2) END AS daily_average,
                    CASE WHEN total_quantity > 0 THEN ROUND(total_sales / total_quantity, 2) END AS value_reper,
                    CASE WHEN receipt_count > 0 THEN ROUND(receipt_2plus_count * 100.0 / receipt_count, 2) END AS bonuri_pct,
                    CASE WHEN total_quantity > 0 THEN ROUND(focus_quantity * 100.0 / total_quantity, 2) END AS focus_pct
                FROM agent_period
            ),
            peer_metrics AS (
                SELECT
                    *,
                    CASE
                        WHEN COUNT(*) OVER (PARTITION BY month, site_code) > 1
                        THEN ROUND(
                            (
                                SUM(COALESCE(daily_average, 0)) OVER (PARTITION BY month, site_code)
                                - COALESCE(daily_average, 0)
                            )
                            / NULLIF(COUNT(*) OVER (PARTITION BY month, site_code) - 1, 0),
                            2
                        )
                    END AS peer_daily_average
                FROM agent_metrics
            ),
            premium_lines AS (
                SELECT DISTINCT
                    st.id,
                    CASE WHEN $1::TEXT IS NULL THEN '2026-01..2026-05' ELSE st.import_month END AS month,
                    st.agent,
                    pgm.is_premium_glass AS is_premium,
                    st.quantity::INT AS qty
                FROM sales_transactions st
                JOIN current_agents ca ON ca.agent = st.agent
                JOIN v_premium_glass_item_models pgm ON pgm.item_code = st.item_code
                WHERE st.import_month BETWEEN '2026-01' AND '2026-05'
                  AND ($1::TEXT IS NULL OR st.import_month = $1)
                  AND ($2::TEXT IS NULL OR ca.firma = $2)
                  AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
                  AND ($4::TEXT IS NULL OR ca.site_code = $4)
                  AND LOWER(TRIM(COALESCE(st.category, ''))) = 'folii sticla'
                  AND st.quantity > 0
                  AND st.agent IS NOT NULL
                  AND TRIM(st.agent) != ''
                  AND st.agent != '-'
                  AND st.agent NOT ILIKE 'TR%'
            ),
            premium_by_agent AS (
                SELECT
                    month,
                    agent,
                    COALESCE(SUM(qty), 0)::INT AS glass_qty,
                    COALESCE(SUM(qty) FILTER (WHERE is_premium), 0)::INT AS premium_glass_qty
                FROM premium_lines
                GROUP BY month, agent
            )
            SELECT
                pm.*,
                COALESCE(pba.glass_qty, 0)::INT AS glass_qty,
                COALESCE(pba.premium_glass_qty, 0)::INT AS premium_glass_qty,
                CASE
                    WHEN COALESCE(pba.glass_qty, 0) > 0
                    THEN ROUND(COALESCE(pba.premium_glass_qty, 0) * 100.0 / pba.glass_qty, 2)
                END AS premium_glass_pct
            FROM peer_metrics pm
            LEFT JOIN premium_by_agent pba
              ON pba.month = pm.month
             AND pba.agent = pm.agent
            ORDER BY pm.month DESC, pm.asm, pm.locatie, pm.total_sales DESC, pm.agent
        """

        option_query = """
            WITH current_month AS (
                SELECT MAX(import_month) AS month
                FROM reporting_agent_month
            ),
            current_agents AS (
                SELECT DISTINCT ON (ram.agent)
                    ram.agent,
                    ram.firma,
                    ram.asm,
                    ram.site_code,
                    ram.locatie
                FROM reporting_agent_month ram
                JOIN current_month cm ON cm.month = ram.import_month
                WHERE ram.agent IS NOT NULL
                  AND TRIM(ram.agent) != ''
                  AND ram.agent != '-'
                  AND ram.agent NOT ILIKE 'TR%'
                ORDER BY ram.agent, ram.working_days DESC, ram.total_sales DESC, ram.site_code
            ),
            scoped AS (
                SELECT DISTINCT ram.import_month AS month, ca.firma, ca.asm, ca.site_code, ca.locatie
                FROM reporting_agent_month ram
                JOIN current_agents ca ON ca.agent = ram.agent
                WHERE ram.import_month BETWEEN '2026-01' AND '2026-05'
            )
            SELECT 'month' AS type, month AS value, month AS label FROM scoped
            UNION
            SELECT 'firma' AS type, firma AS value, firma AS label FROM scoped WHERE firma IS NOT NULL AND TRIM(firma) != ''
            UNION
            SELECT 'asm' AS type, asm AS value, asm AS label FROM scoped WHERE asm IS NOT NULL AND TRIM(asm) != ''
            UNION
            SELECT 'store' AS type, site_code AS value, locatie || ' (' || site_code || ')' AS label FROM scoped
            ORDER BY type, label
        """

        rows = await self.repo.get_agent_evaluation(query, [month, firma, asm, site_code])
        option_rows = await self.repo.get_agent_evaluation(option_query, [])

        months: list[AgentEvaluationOption] = []
        firmas: list[AgentEvaluationOption] = []
        asms: list[AgentEvaluationOption] = []
        stores: list[AgentEvaluationOption] = []
        seen_options: set[tuple[str, str]] = set()
        for row in option_rows:
            key = (row["type"], row["value"])
            if key in seen_options:
                continue
            seen_options.add(key)
            option = AgentEvaluationOption(value=row["value"], label=row["label"])
            if row["type"] == "month":
                months.append(option)
            elif row["type"] == "firma":
                firmas.append(option)
            elif row["type"] == "asm":
                asms.append(option)
            else:
                stores.append(option)

        items: list[AgentEvaluationRow] = []
        for row in rows:
            target_points = pct_points(row["target_pct"], (Decimal("100"), Decimal("90"), Decimal("80")))
            daily_points = 3 if row["daily_average"] is not None and row["peer_daily_average"] is not None and row["daily_average"] > row["peer_daily_average"] else 0
            value_reper_points = pct_points(row["value_reper"], (Decimal("100"), Decimal("95"), Decimal("90")))
            bonuri_points = pct_points(row["bonuri_pct"], (Decimal("35"), Decimal("30"), Decimal("25")))
            focus_points = pct_points(row["focus_pct"], (Decimal("8"), Decimal("7"), Decimal("6")))
            premium_points = pct_points(row["premium_glass_pct"], (Decimal("50"), Decimal("40"), Decimal("30")))
            segment_points = [
                target_points,
                daily_points,
                value_reper_points,
                bonuri_points,
                focus_points,
                premium_points,
            ]
            total_points = sum(segment_points)
            has_red_segment = any(point == 0 for point in segment_points)
            bonus_amount = 0
            if total_points == 18:
                bonus_amount = 300
            elif total_points >= 16:
                bonus_amount = 200
            elif total_points >= 14 and not has_red_segment:
                bonus_amount = 100

            items.append(
                AgentEvaluationRow(
                    month=row["month"],
                    firma=row["firma"],
                    site_code=row["site_code"],
                    locatie=row["locatie"],
                    regional=row["regional"],
                    asm=row["asm"],
                    agent=row["agent"],
                    total_sales=row["total_sales"],
                    total_quantity=row["total_quantity"],
                    working_days=row["working_days"],
                    store_target=row["store_target"],
                    store_working_days=row["store_working_days"],
                    target_value=row["target_value"],
                    target_pct=row["target_pct"],
                    daily_average=row["daily_average"],
                    peer_daily_average=row["peer_daily_average"],
                    value_reper=row["value_reper"],
                    receipt_count=row["receipt_count"],
                    receipt_2plus_count=row["receipt_2plus_count"],
                    bonuri_pct=row["bonuri_pct"],
                    focus_quantity=row["focus_quantity"],
                    focus_pct=row["focus_pct"],
                    glass_qty=row["glass_qty"],
                    premium_glass_qty=row["premium_glass_qty"],
                    premium_glass_pct=row["premium_glass_pct"],
                    target_points=target_points,
                    daily_points=daily_points,
                    value_reper_points=value_reper_points,
                    bonuri_points=bonuri_points,
                    focus_points=focus_points,
                    premium_glass_points=premium_points,
                    total_points=total_points,
                    has_red_segment=has_red_segment,
                    qualifier=qualifier(total_points),
                    bonus_amount=bonus_amount,
                )
            )

        return AgentEvaluationResponse(months=months, firmas=firmas, asms=asms, stores=stores, rows=items)

    async def get_agents_movement(
        self, selected_month: str, firma: str | None, regional: str | None, asm: str | None, site_code: str | None, agent: str | None
    ) -> AgentMovementResponse:
        params, positions = base_filter_values(
            selected_month, firma, regional, asm, site_code, agent
        )
        clauses = scoped_clauses(
            positions,
            site_alias="st",
            store_alias="st",
            agent_alias="st",
        )
        clauses.extend(["st.import_month >= '2025-01'", "st.import_month <= $1"])
        where_sql = "WHERE " + " AND ".join(clauses)

        query = f"""
            WITH scoped_active AS (
                SELECT DISTINCT st.import_month, st.agent
                FROM reporting_agent_month st
                {where_sql}
                  AND st.agent IS NOT NULL
                  AND st.agent != '-'
            ),
            months AS (
                SELECT DISTINCT import_month AS month
                FROM scoped_active
            ),
            monthly AS (
                SELECT import_month AS month, COUNT(*)::INT AS active
                FROM scoped_active
                GROUP BY import_month
            ),
            flagged AS (
                SELECT
                    sa.import_month AS month,
                    COUNT(DISTINCT sa.agent) FILTER (
                        WHERE lc.is_new AND sa.import_month != '2025-01'
                    )::INT AS new,
                    COUNT(DISTINCT sa.agent) FILTER (
                        WHERE lc.is_reactivated AND sa.import_month != '2025-01'
                    )::INT AS reactivated
                FROM scoped_active sa
                JOIN reporting_agent_lifecycle_month lc
                  ON lc.agent = sa.agent AND lc.import_month = sa.import_month
                GROUP BY sa.import_month
            ),
            churned AS (
                SELECT
                    m.month,
                    COUNT(pa.agent) FILTER (WHERE ca.agent IS NULL AND m.month != '2025-01')::INT AS churned
                FROM months m
                LEFT JOIN scoped_active pa
                  ON pa.import_month = to_char((TO_DATE(m.month, 'YYYY-MM') - INTERVAL '1 month'), 'YYYY-MM')
                LEFT JOIN scoped_active ca
                  ON ca.import_month = m.month AND ca.agent = pa.agent
                GROUP BY m.month
            ),
            previous_totals AS (
                SELECT
                    m.month,
                    COALESCE(pm.active, 0)::INT AS previous_active
                FROM months m
                LEFT JOIN monthly pm
                  ON pm.month = to_char((TO_DATE(m.month, 'YYYY-MM') - INTERVAL '1 month'), 'YYYY-MM')
            )
            SELECT
                m.month,
                COALESCE(mon.active, 0)::INT AS active,
                COALESCE(f.new, 0)::INT AS new,
                COALESCE(f.reactivated, 0)::INT AS reactivated,
                COALESCE(ch.churned, 0)::INT AS churned,
                CASE
                    WHEN m.month = '2025-01' THEN 0
                    ELSE COALESCE(mon.active, 0) - COALESCE(pt.previous_active, 0)
                END::INT AS net_growth,
                (m.month = '2025-01') AS is_baseline
            FROM months m
            LEFT JOIN monthly mon ON mon.month = m.month
            LEFT JOIN flagged f ON f.month = m.month
            LEFT JOIN churned ch ON ch.month = m.month
            LEFT JOIN previous_totals pt ON pt.month = m.month
            ORDER BY m.month ASC
        """
        rows = await self.repo.get_movement(query, params)
        history = [
            AgentMovementPoint(
                month=str(row["month"]),
                active=row["active"],
                new=row["new"],
                reactivated=row["reactivated"],
                churned=row["churned"],
                net_growth=row["net_growth"],
                is_baseline=row["is_baseline"],
            )
            for row in rows
        ]
        return AgentMovementResponse(history=history)

    async def get_agents_list(
        self, selected_month: str, search: str | None, firma: str | None, regional: str | None, asm: str | None, site_code: str | None
    ) -> AgentListResponse:
        clauses, params = where_clauses(
            selected_month, firma, regional, asm, site_code, None, include_agent=False
        )
        scope_clauses = [
            c.replace("import_month = $1", "import_month <= $1") for c in clauses
        ]
        scope_where = "WHERE " + " AND ".join(scope_clauses) if scope_clauses else ""
        selected_idx = month_index_expr("$1")

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

        rows = await self.repo.get_agents_list(query, params)
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

    async def get_agent_profile(self, agent: str, selected_month: str) -> AgentProfileResponse:
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

        row = await self.repo.get_agent_profile(query, agent, selected_month)
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        return AgentProfileResponse(**dict(row))

    async def get_agent_history(self, agent: str) -> AgentHistoryResponse:
        rows = await self.repo.get_agent_history(agent)
        history = [AgentHistoryPoint(**dict(row)) for row in rows]
        return AgentHistoryResponse(history=history)

    async def get_stores_coverage(
        self, selected_month: str, firma: str | None, regional: str | None, asm: str | None
    ) -> StoreCoverageResponse:
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

        where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
        selected_idx = month_index_expr("$1")

        query = f"""
            WITH store_agents AS (
                SELECT site_code, COUNT(DISTINCT agent)::INT as agent_count
                FROM reporting_agent_month
                WHERE import_month = $1
                  AND agent IS NOT NULL AND agent != '-'
                GROUP BY site_code
            ),
            curr_agents AS (
                SELECT site_code, array_agg(DISTINCT agent ORDER BY agent) AS agents
                FROM reporting_agent_month
                WHERE import_month = $1
                  AND agent IS NOT NULL AND agent != '-'
                GROUP BY site_code
            ),
            prev_agents AS (
                SELECT site_code, array_agg(DISTINCT agent ORDER BY agent) AS agents
                FROM reporting_agent_month
                WHERE import_month = to_char(
                    (TO_DATE($1, 'YYYY-MM') - INTERVAL '1 month'), 'YYYY-MM'
                )
                  AND agent IS NOT NULL AND agent != '-'
                GROUP BY site_code
            ),
            store_changes AS (
                SELECT
                    s.site_code,
                    s.locatie,
                    s.firma,
                    s.regional,
                    s.asm,
                    COALESCE(sa.agent_count, 0) as agent_count,
                    COALESCE(array_length(pa.agents, 1), 0)::INT AS previous_agent_count,
                    (
                        SELECT COUNT(*)::INT
                        FROM unnest(COALESCE(ca.agents, ARRAY[]::TEXT[])) AS curr(agent)
                        WHERE curr.agent <> ALL(COALESCE(pa.agents, ARRAY[]::TEXT[]))
                    ) AS added_agents_count,
                    (
                        SELECT COUNT(*)::INT
                        FROM unnest(COALESCE(pa.agents, ARRAY[]::TEXT[])) AS prev(agent)
                        WHERE prev.agent <> ALL(COALESCE(ca.agents, ARRAY[]::TEXT[]))
                    ) AS removed_agents_count,
                    CASE
                        WHEN s.last_seen_month = $1 THEN
                            CASE WHEN COALESCE(sa.agent_count, 0) > 0 THEN 'covered' ELSE 'uncovered' END
                        WHEN {selected_idx} - {month_index_expr("s.last_seen_month")} > 3 THEN 'closed'
                        ELSE 'inactive'
                    END as status,
                    ca.agents IS DISTINCT FROM pa.agents AS has_changes
                FROM stores s
                LEFT JOIN store_agents sa ON sa.site_code = s.site_code
                LEFT JOIN curr_agents ca ON ca.site_code = s.site_code
                LEFT JOIN prev_agents pa ON pa.site_code = s.site_code
                {where_sql}
            )
            SELECT
                *,
                CASE
                    WHEN NOT has_changes THEN NULL
                    WHEN previous_agent_count = 0 AND agent_count > 0 THEN 'agenti intrati'
                    WHEN previous_agent_count > 0 AND agent_count = 0 THEN 'toti agentii au iesit'
                    WHEN added_agents_count > 0 AND removed_agents_count > 0 THEN 'intrari si iesiri'
                    WHEN added_agents_count > 0 THEN 'agenti intrati'
                    WHEN removed_agents_count > 0 THEN 'agenti iesiti'
                    ELSE 'echipa modificata'
                END AS change_reason
            FROM store_changes
            ORDER BY agent_count ASC, locatie ASC
        """

        rows = await self.repo.get_stores_coverage(query, params)
        items = [StoreCoverageItem(**dict(row)) for row in rows]

        active_stores = [i for i in items if i.status == "covered"]
        uncovered_stores = [i for i in items if i.status == "uncovered"]
        closed_stores = [i for i in items if i.status == "closed"]
        modified_stores_count = sum(1 for i in items if i.has_changes)

        return StoreCoverageResponse(
            active_stores_count=len(active_stores),
            uncovered_stores_count=len(uncovered_stores),
            closed_stores_count=len(closed_stores),
            modified_stores_count=modified_stores_count,
            items=items,
        )
