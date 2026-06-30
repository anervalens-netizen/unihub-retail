from __future__ import annotations

from decimal import Decimal
from math import ceil
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
    AgentEvaluationV2Response,
    AgentEvaluationV2Row,
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


def _score_band(
    value: Decimal | None,
    thresholds: tuple[Decimal, Decimal, Decimal],
    weight: int,
) -> Decimal | None:
    if value is None:
        return None
    if value >= thresholds[2]:
        points = Decimal(3)
    elif value >= thresholds[1]:
        points = Decimal(2)
    elif value >= thresholds[0]:
        points = Decimal(1)
    else:
        points = Decimal(0)
    return (Decimal(weight) * points / Decimal(3)).quantize(Decimal("0.1"))


def _score_rating(score: Decimal | None, eligibility_status: str) -> str:
    if eligibility_status == "insuficient":
        return "Insuficient"
    if score is None:
        return "Fara scor"
    if score >= Decimal("85"):
        return "Excelent"
    if score >= Decimal("75"):
        return "Foarte Bun"
    if score >= Decimal("65"):
        return "Bun"
    if score >= Decimal("50"):
        return "Risc"
    return "Critic"


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
        months: str | None,
        firma: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> AgentEvaluationResponse:
        month_filter = months or month
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
            location_working_days AS (
                SELECT
                    import_month,
                    site_code,
                    COUNT(DISTINCT sale_date)::INT AS working_days
                FROM reporting_agent_day
                WHERE import_month >= '2025-01'
                GROUP BY import_month, site_code
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
                    COALESCE(lwd.working_days, 0) AS store_working_days
                FROM reporting_agent_month ram
                JOIN current_agents ca ON ca.agent = ram.agent
                LEFT JOIN location_working_days lwd
                  ON lwd.import_month = ram.import_month
                 AND lwd.site_code = ram.site_code
                LEFT JOIN store_targets st
                  ON st.import_month = ram.import_month
                 AND st.site_code = ram.site_code
                WHERE ram.import_month >= '2025-01'
                  AND ($1::TEXT IS NULL OR ram.import_month = ANY(string_to_array($1::TEXT, ',')))
                  AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
                  AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
                  AND ($4::TEXT IS NULL OR ca.site_code = ANY(string_to_array($4::TEXT, ',')))
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
                    CASE
                        WHEN $1::TEXT IS NULL THEN '2025-01..curent'
                        WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
                        ELSE month
                    END AS month,
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
                    CASE
                        WHEN $1::TEXT IS NULL THEN '2025-01..curent'
                        WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
                        ELSE month
                    END,
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
                    CASE
                        WHEN $1::TEXT IS NULL THEN '2025-01..curent'
                        WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
                        ELSE st.import_month
                    END AS month,
                    st.agent,
                    pgm.is_premium_glass AS is_premium,
                    st.quantity::INT AS qty
                FROM sales_transactions st
                JOIN current_agents ca ON ca.agent = st.agent
                JOIN premium_glass_item_models pgm ON pgm.item_code = st.item_code
                WHERE st.import_month >= '2025-01'
                  AND ($1::TEXT IS NULL OR st.import_month = ANY(string_to_array($1::TEXT, ',')))
                  AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
                  AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
                  AND ($4::TEXT IS NULL OR ca.site_code = ANY(string_to_array($4::TEXT, ',')))
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
                    ram.regional,
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
                SELECT DISTINCT ram.import_month AS month, ca.firma, ca.regional, ca.asm, ca.site_code, ca.locatie
                FROM reporting_agent_month ram
                JOIN current_agents ca ON ca.agent = ram.agent
                WHERE ram.import_month >= '2025-01'
            )
            SELECT 'month' AS type, month AS value, month AS label FROM scoped
            UNION
            SELECT 'firma' AS type, firma AS value, firma AS label FROM scoped WHERE firma IS NOT NULL AND TRIM(firma) != ''
            UNION
            SELECT 'asm' AS type, asm AS value, asm AS label FROM scoped WHERE asm IS NOT NULL AND TRIM(asm) != ''
            UNION
            SELECT 'store' AS type, site_code AS value, locatie || ' (' || site_code || ')' AS label
            FROM scoped
            WHERE ($1::TEXT IS NULL OR LOWER(firma) = LOWER($1))
              AND ($2::TEXT IS NULL OR asm = $2 OR regional = $2)
            ORDER BY type, label
        """

        rows = await self.repo.get_agent_evaluation(query, [month_filter, firma, asm, site_code])
        option_rows = await self.repo.get_agent_evaluation(option_query, [firma, asm])

        month_options: list[AgentEvaluationOption] = []
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
                month_options.append(option)
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
                )
            )

        return AgentEvaluationResponse(months=month_options, firmas=firmas, asms=asms, stores=stores, rows=items)

    async def get_agent_evaluation_v2(
        self,
        month: str | None,
        months: str | None,
        firma: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> AgentEvaluationV2Response:
        month_filter = months or month
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
            selected_months AS (
                SELECT DISTINCT ram.import_month
                FROM reporting_agent_month ram
                JOIN current_agents ca ON ca.agent = ram.agent
                WHERE ram.import_month >= '2025-01'
                  AND ($1::TEXT IS NULL OR ram.import_month = ANY(string_to_array($1::TEXT, ',')))
                  AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
                  AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
                  AND ($4::TEXT IS NULL OR ca.site_code = ANY(string_to_array($4::TEXT, ',')))
            ),
            selected_context AS (
                SELECT
                    MIN(import_month) AS min_month,
                    MAX(import_month) AS max_month,
                    COUNT(*)::INT AS period_month_count,
                    MIN(CAST(SUBSTRING(import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(import_month, 6, 2) AS INTEGER)) AS min_month_idx,
                    MAX(CAST(SUBSTRING(import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(import_month, 6, 2) AS INTEGER)) AS max_month_idx
                FROM selected_months
            ),
            sale_month_days AS (
                SELECT import_month, EXTRACT(DAY FROM MAX(sale_date))::INT AS last_sale_day
                FROM reporting_item_day
                WHERE import_month IN (SELECT import_month FROM selected_months)
                GROUP BY import_month
            ),
            month_meta AS (
                SELECT
                    sm.import_month,
                    COALESCE(BOOL_AND(snap.is_month_final), true) AS is_final,
                    COALESCE(smd.last_sale_day, 0) AS last_sale_day,
                    EXTRACT(DAY FROM (
                        date_trunc('month', to_date(sm.import_month || '-01', 'YYYY-MM-DD'))
                        + INTERVAL '1 month - 1 day'
                    ))::INT AS days_in_month,
                    CASE
                        WHEN COALESCE(BOOL_AND(snap.is_month_final), true) = false
                             AND COALESCE(smd.last_sale_day, 0) > 0
                        THEN
                            EXTRACT(DAY FROM (
                                date_trunc('month', to_date(sm.import_month || '-01', 'YYYY-MM-DD'))
                                + INTERVAL '1 month - 1 day'
                            ))::NUMERIC
                            / COALESCE(smd.last_sale_day, 1)::NUMERIC
                        ELSE 1::NUMERIC
                    END AS forecast_factor,
                    CASE
                        WHEN COALESCE(BOOL_AND(snap.is_month_final), true) = false
                             AND COALESCE(smd.last_sale_day, 0) > 0
                        THEN smd.last_sale_day
                        ELSE EXTRACT(DAY FROM (
                            date_trunc('month', to_date(sm.import_month || '-01', 'YYYY-MM-DD'))
                            + INTERVAL '1 month - 1 day'
                        ))::INT
                    END AS available_days
                FROM selected_months sm
                LEFT JOIN import_snapshots snap ON snap.import_month = sm.import_month
                LEFT JOIN sale_month_days smd ON smd.import_month = sm.import_month
                GROUP BY sm.import_month, smd.last_sale_day
            ),
            location_working_days AS (
                SELECT
                    rad.import_month,
                    rad.site_code,
                    COUNT(DISTINCT rad.sale_date)::INT AS working_days
                FROM reporting_agent_day rad
                WHERE rad.import_month IN (SELECT import_month FROM selected_months)
                GROUP BY rad.import_month, rad.site_code
            ),
            monthly_base AS (
                SELECT
                    ram.import_month AS raw_month,
                    CASE
                        WHEN $1::TEXT IS NULL THEN '2025-01..curent'
                        WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
                        ELSE ram.import_month
                    END AS month,
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
                    mm.forecast_factor,
                    (mm.is_final = false) AS is_partial,
                    mm.available_days,
                    mm.days_in_month,
                    COALESCE(lwd.working_days, 0) AS location_working_days
                FROM reporting_agent_month ram
                JOIN current_agents ca ON ca.agent = ram.agent
                JOIN month_meta mm ON mm.import_month = ram.import_month
                LEFT JOIN location_working_days lwd
                  ON lwd.import_month = ram.import_month
                 AND lwd.site_code = ram.site_code
                LEFT JOIN store_targets st
                  ON st.import_month = ram.import_month
                 AND st.site_code = ram.site_code
                WHERE ram.import_month >= '2025-01'
                  AND ($1::TEXT IS NULL OR ram.import_month = ANY(string_to_array($1::TEXT, ',')))
                  AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
                  AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
                  AND ($4::TEXT IS NULL OR ca.site_code = ANY(string_to_array($4::TEXT, ',')))
                  AND ram.agent IS NOT NULL
                  AND TRIM(ram.agent) != ''
                  AND ram.agent != '-'
                  AND ram.agent NOT ILIKE 'TR%'
            ),
            monthly_targets AS (
                SELECT
                    *,
                    CASE
                        WHEN location_working_days > 0
                        THEN ROUND(store_target * working_days / location_working_days, 2)
                        ELSE 0
                    END AS effective_target
                FROM monthly_base
            ),
            monthly_scored AS (
                SELECT
                    *,
                    CASE
                        WHEN effective_target > 0 THEN ROUND(total_sales * 100.0 / effective_target, 2)
                    END AS month_target_pct,
                    CASE
                        WHEN effective_target <= 0 THEN NULL
                        WHEN total_sales * 100.0 / effective_target >= 100 THEN 1::NUMERIC
                        WHEN total_sales * 100.0 / effective_target >= 90 THEN 0.6667::NUMERIC
                        WHEN total_sales * 100.0 / effective_target >= 80 THEN 0.3333::NUMERIC
                        ELSE 0::NUMERIC
                    END AS target_month_score_ratio,
                    CASE
                        WHEN effective_target <= 0 THEN 0::NUMERIC
                        WHEN is_partial AND days_in_month > 0
                        THEN LEAST(1::NUMERIC, GREATEST(0::NUMERIC, available_days::NUMERIC / days_in_month::NUMERIC))
                        ELSE 1::NUMERIC
                    END AS target_month_score_weight
                FROM monthly_targets
            ),
            agent_period AS (
                SELECT
                    month,
                    firma,
                    site_code,
                    locatie,
                    regional,
                    asm,
                    agent,
                    COALESCE(SUM(total_sales), 0) AS total_sales,
                    COALESCE(SUM(total_sales * forecast_factor), 0) AS forecast_sales,
                    COALESCE(SUM(total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(focus_quantity), 0)::INT AS focus_quantity,
                    COALESCE(SUM(receipt_count), 0)::INT AS receipt_count,
                    COALESCE(SUM(receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                    COALESCE(SUM(working_days), 0)::INT AS working_days,
                    COALESCE(SUM(effective_target), 0) AS target_value,
                    COALESCE(MAX(forecast_factor), 1) AS forecast_factor,
                    BOOL_OR(is_partial) AS is_partial,
                    COALESCE(SUM(available_days), 0)::INT AS available_days,
                    COUNT(*)::INT AS period_month_count,
                    COUNT(*) FILTER (WHERE is_partial)::INT AS partial_month_count,
                    COUNT(*) FILTER (WHERE NOT is_partial)::INT AS final_month_count,
                    COALESCE(SUM(
                        CASE
                            WHEN is_partial THEN CEIL(available_days * 0.4)::INT
                            ELSE 0
                        END
                    ), 0)::INT AS partial_min_working_days,
                    COALESCE(SUM(target_month_score_weight), 0) AS target_score_month_weight,
                    CASE
                        WHEN COALESCE(SUM(target_month_score_weight), 0) > 0
                        THEN ROUND(
                            SUM(target_month_score_ratio * target_month_score_weight)
                            / SUM(target_month_score_weight),
                            4
                        )
                    END AS target_score_ratio
                FROM monthly_scored
                GROUP BY month, firma, site_code, locatie, regional, asm, agent
            ),
            agent_metrics AS (
                SELECT
                    *,
                    'allocated_store_target'::TEXT AS target_source,
                    CASE WHEN target_value > 0 THEN ROUND(total_sales * 100.0 / target_value, 2) END AS target_pct,
                    CASE WHEN target_value > 0 THEN ROUND(forecast_sales * 100.0 / target_value, 2) END AS target_forecast_pct,
                    CASE WHEN working_days > 0 THEN ROUND(total_sales / working_days, 2) END AS daily_average,
                    CASE WHEN total_quantity > 0 THEN ROUND(total_sales / total_quantity, 2) END AS value_reper,
                    CASE WHEN receipt_count > 0 THEN ROUND(receipt_2plus_count * 100.0 / receipt_count, 2) END AS bonuri_pct,
                    CASE WHEN total_quantity > 0 THEN ROUND(focus_quantity * 100.0 / total_quantity, 2) END AS focus_pct
                FROM agent_period
            ),
            peer_refs AS (
                SELECT
                    am.*,
                    (
                        SELECT ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY other.daily_average)::NUMERIC, 2)
                        FROM agent_metrics other
                        WHERE other.month = am.month
                          AND other.site_code = am.site_code
                          AND other.agent <> am.agent
                          AND other.daily_average IS NOT NULL
                    ) AS peer_daily_median
                FROM agent_metrics am
            ),
            location_history AS (
                SELECT
                    ram.site_code,
                    ROUND(SUM(ram.total_sales) / NULLIF(SUM(ram.working_days), 0), 2) AS daily_average
                FROM reporting_agent_month ram
                CROSS JOIN selected_context sc
                WHERE sc.max_month_idx IS NOT NULL
                  AND (CAST(SUBSTRING(ram.import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(ram.import_month, 6, 2) AS INTEGER))
                      BETWEEN sc.max_month_idx - 3 AND sc.max_month_idx - 1
                GROUP BY ram.site_code
            ),
            manager_history AS (
                SELECT
                    c.asm,
                    ROUND(SUM(ram.total_sales) / NULLIF(SUM(ram.working_days), 0), 2) AS daily_average
                FROM reporting_agent_month ram
                JOIN v_retail_current_store_org c ON c.site_code = ram.site_code
                CROSS JOIN selected_context sc
                WHERE sc.max_month_idx IS NOT NULL
                  AND (CAST(SUBSTRING(ram.import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(ram.import_month, 6, 2) AS INTEGER))
                      BETWEEN sc.max_month_idx - 3 AND sc.max_month_idx - 1
                GROUP BY c.asm
            ),
            agent_history AS (
                SELECT
                    ram.agent,
                    ROUND(SUM(ram.total_sales) / NULLIF(SUM(ram.working_days), 0), 2) AS daily_average
                FROM reporting_agent_month ram
                CROSS JOIN selected_context sc
                WHERE sc.max_month_idx IS NOT NULL
                  AND (CAST(SUBSTRING(ram.import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(ram.import_month, 6, 2) AS INTEGER))
                      BETWEEN sc.max_month_idx - 3 AND sc.max_month_idx - 1
                GROUP BY ram.agent
            ),
            premium_lines AS (
                SELECT DISTINCT
                    st.id,
                    CASE
                        WHEN $1::TEXT IS NULL THEN '2025-01..curent'
                        WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
                        ELSE st.import_month
                    END AS month,
                    st.agent,
                    pgm.is_premium_glass AS is_premium,
                    st.quantity::INT AS qty
                FROM sales_transactions st
                JOIN current_agents ca ON ca.agent = st.agent
                JOIN premium_glass_item_models pgm ON pgm.item_code = st.item_code
                WHERE st.import_month >= '2025-01'
                  AND ($1::TEXT IS NULL OR st.import_month = ANY(string_to_array($1::TEXT, ',')))
                  AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
                  AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
                  AND ($4::TEXT IS NULL OR ca.site_code = ANY(string_to_array($4::TEXT, ',')))
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
                pr.*,
                CASE
                    WHEN pr.peer_daily_median IS NOT NULL THEN pr.peer_daily_median
                    WHEN lh.daily_average IS NOT NULL THEN lh.daily_average
                    ELSE mh.daily_average
                END AS daily_reference,
                CASE
                    WHEN pr.peer_daily_median IS NOT NULL THEN 'colegi'
                    WHEN lh.daily_average IS NOT NULL THEN 'istoric_locatie'
                    WHEN mh.daily_average IS NOT NULL THEN 'media_manager'
                    ELSE 'none'
                END AS daily_reference_type,
                CASE
                    WHEN COALESCE(
                        pr.peer_daily_median,
                        lh.daily_average,
                        mh.daily_average
                    ) > 0
                    THEN ROUND(
                        pr.daily_average * 100.0 / COALESCE(
                            pr.peer_daily_median,
                            lh.daily_average,
                            mh.daily_average
                        ),
                        2
                    )
                END AS daily_vs_reference_pct,
                COALESCE(pba.glass_qty, 0)::INT AS glass_qty,
                COALESCE(pba.premium_glass_qty, 0)::INT AS premium_glass_qty,
                CASE
                    WHEN COALESCE(pba.glass_qty, 0) > 0
                    THEN ROUND(COALESCE(pba.premium_glass_qty, 0) * 100.0 / pba.glass_qty, 2)
                END AS premium_glass_pct,
                CASE
                    WHEN ah.daily_average > 0 AND pr.daily_average IS NOT NULL
                    THEN ROUND((pr.daily_average - ah.daily_average) * 100.0 / ah.daily_average, 2)
                END AS trend_daily_pct
            FROM peer_refs pr
            LEFT JOIN location_history lh ON lh.site_code = pr.site_code
            LEFT JOIN manager_history mh ON mh.asm = pr.asm
            LEFT JOIN agent_history ah ON ah.agent = pr.agent
            LEFT JOIN premium_by_agent pba
              ON pba.month = pr.month
             AND pba.agent = pr.agent
            ORDER BY pr.is_partial DESC, pr.asm, pr.locatie, pr.total_sales DESC, pr.agent
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
                    ram.regional,
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
                SELECT DISTINCT ram.import_month AS month, ca.firma, ca.regional, ca.asm, ca.site_code, ca.locatie
                FROM reporting_agent_month ram
                JOIN current_agents ca ON ca.agent = ram.agent
                WHERE ram.import_month >= '2025-01'
            )
            SELECT 'month' AS type, month AS value, month AS label FROM scoped
            UNION
            SELECT 'firma' AS type, firma AS value, firma AS label FROM scoped WHERE firma IS NOT NULL AND TRIM(firma) != ''
            UNION
            SELECT 'asm' AS type, asm AS value, asm AS label FROM scoped WHERE asm IS NOT NULL AND TRIM(asm) != ''
            UNION
            SELECT 'store' AS type, site_code AS value, locatie || ' (' || site_code || ')' AS label
            FROM scoped
            WHERE ($1::TEXT IS NULL OR LOWER(firma) = LOWER($1))
              AND ($2::TEXT IS NULL OR asm = $2 OR regional = $2)
            ORDER BY type, label
        """

        rows = await self.repo.get_agent_evaluation(query, [month_filter, firma, asm, site_code])
        option_rows = await self.repo.get_agent_evaluation(option_query, [firma, asm])

        month_options: list[AgentEvaluationOption] = []
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
                month_options.append(option)
            elif row["type"] == "firma":
                firmas.append(option)
            elif row["type"] == "asm":
                asms.append(option)
            else:
                stores.append(option)

        items: list[AgentEvaluationV2Row] = []
        for row in rows:
            is_partial = bool(row["is_partial"])
            period_month_count = max(1, int(row["period_month_count"] or 1))
            partial_month_count = int(row["partial_month_count"] or 0)
            final_month_count = int(row["final_month_count"] or 0)
            available_days = int(row["available_days"] or 0)
            working_days = int(row["working_days"] or 0)
            receipt_count = int(row["receipt_count"] or 0)

            if period_month_count == 1:
                min_working_days = ceil(available_days * 0.4) if is_partial and available_days else 8
                min_receipts = 20 if is_partial else 30
            else:
                min_working_days = 8 * final_month_count + int(row["partial_min_working_days"] or 0)
                min_receipts = 30 * final_month_count + 20 * partial_month_count

            confidence_flags: list[str] = []
            if is_partial:
                confidence_flags.append("luna_partiala")
            if row["target_source"] == "partial_agent_target":
                confidence_flags.append("target_partial_din_grile")
            elif row["target_source"] == "allocated_store_target":
                confidence_flags.append("target_alocat_din_magazin")
            if row["daily_reference_type"] != "colegi":
                confidence_flags.append(f"reper_{row['daily_reference_type']}")
            if int(row["glass_qty"] or 0) < 5:
                confidence_flags.append("folii_volum_mic")
            if working_days < min_working_days or receipt_count < min_receipts:
                confidence_flags.append("volum_insuficient")

            eligibility_status = "insuficient" if "volum_insuficient" in confidence_flags else "eligibil"
            is_single_partial_month = is_partial and period_month_count == 1
            weights = (
                {"target": 10, "daily": 25, "bonuri": 20, "focus": 20, "premium": 10, "value": 15}
                if is_single_partial_month
                else {"target": 25, "daily": 20, "bonuri": 15, "focus": 15, "premium": 10, "value": 15}
            )
            target_score_ratio = row["target_score_ratio"]
            target_score = (
                (Decimal(weights["target"]) * target_score_ratio).quantize(Decimal("0.1"))
                if target_score_ratio is not None
                else None
            )
            daily_score = _score_band(row["daily_vs_reference_pct"], (Decimal("85"), Decimal("100"), Decimal("115")), weights["daily"])
            bonuri_score = _score_band(row["bonuri_pct"], (Decimal("25"), Decimal("30"), Decimal("35")), weights["bonuri"])
            focus_score = _score_band(row["focus_pct"], (Decimal("6"), Decimal("8"), Decimal("10")), weights["focus"])
            value_score = _score_band(row["value_reper"], (Decimal("90"), Decimal("95"), Decimal("100")), weights["value"])
            premium_score = (
                _score_band(row["premium_glass_pct"], (Decimal("30"), Decimal("40"), Decimal("50")), weights["premium"])
                if int(row["glass_qty"] or 0) >= 5
                else None
            )

            scored_components = [
                (target_score, weights["target"]),
                (daily_score, weights["daily"]),
                (bonuri_score, weights["bonuri"]),
                (focus_score, weights["focus"]),
                (premium_score, weights["premium"]),
                (value_score, weights["value"]),
            ]
            raw_score = sum((score for score, _weight in scored_components if score is not None), Decimal(0))
            applicable_weight = sum(weight for score, weight in scored_components if score is not None)
            total_score = (
                (raw_score * Decimal(100) / Decimal(applicable_weight)).quantize(Decimal("0.1"))
                if applicable_weight > 0
                else None
            )

            trend = row["trend_daily_pct"]
            if trend is None:
                trend_direction = "flat"
            elif trend >= Decimal("5"):
                trend_direction = "up"
            elif trend <= Decimal("-5"):
                trend_direction = "down"
            else:
                trend_direction = "flat"

            items.append(
                AgentEvaluationV2Row(
                    month=row["month"],
                    firma=row["firma"],
                    site_code=row["site_code"],
                    locatie=row["locatie"],
                    regional=row["regional"],
                    asm=row["asm"],
                    agent=row["agent"],
                    total_sales=row["total_sales"],
                    forecast_sales=row["forecast_sales"],
                    total_quantity=row["total_quantity"],
                    working_days=row["working_days"],
                    receipt_count=row["receipt_count"],
                    target_value=row["target_value"],
                    target_source=row["target_source"],
                    target_pct=row["target_pct"],
                    target_forecast_pct=row["target_forecast_pct"],
                    is_partial=is_partial,
                    period_month_count=period_month_count,
                    partial_month_count=partial_month_count,
                    final_month_count=final_month_count,
                    forecast_factor=row["forecast_factor"],
                    daily_average=row["daily_average"],
                    daily_reference=row["daily_reference"],
                    daily_reference_type=row["daily_reference_type"],
                    daily_vs_reference_pct=row["daily_vs_reference_pct"],
                    value_reper=row["value_reper"],
                    receipt_2plus_count=row["receipt_2plus_count"],
                    bonuri_pct=row["bonuri_pct"],
                    focus_quantity=row["focus_quantity"],
                    focus_pct=row["focus_pct"],
                    glass_qty=row["glass_qty"],
                    premium_glass_qty=row["premium_glass_qty"],
                    premium_glass_pct=row["premium_glass_pct"],
                    trend_daily_pct=trend,
                    trend_direction=trend_direction,
                    eligibility_status=eligibility_status,
                    confidence_flags=confidence_flags,
                    target_score=target_score,
                    daily_score=daily_score,
                    bonuri_score=bonuri_score,
                    focus_score=focus_score,
                    premium_glass_score=premium_score,
                    value_reper_score=value_score,
                    total_score=total_score,
                    rating=_score_rating(total_score, eligibility_status),
                )
            )

        return AgentEvaluationV2Response(
            months=month_options,
            firmas=firmas,
            asms=asms,
            stores=stores,
            rows=items,
        )

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
                    locatie AS store_name,
                    firma
                FROM reporting_agent_month
                WHERE import_month = $1
                ORDER BY agent, total_sales DESC
            )
            SELECT
                p.agent,
                ts.store_name,
                ts.firma,
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
                firma=row["firma"],
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
