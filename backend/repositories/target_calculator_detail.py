from __future__ import annotations

from typing import Any

import asyncpg


class TargetCalculatorDetailRepositoryMixin:
    pool: asyncpg.Pool

    async def _get_store_scenario_row(
        self,
        conn: asyncpg.Connection,
        *,
        scenario_id: int,
        site_code: str,
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            SELECT
                ts.id, ts.target_month, ts.cohort_month, ts.total_target,
                tr.site_code, tr.locatie, tr.firma, tr.regional, tr.asm,
                tr.proposed_target, tr.final_target, tr.history
            FROM target_scenarios ts
            JOIN target_scenario_rows tr ON tr.scenario_id = ts.id
            WHERE ts.id = $1 AND tr.site_code = $2
            """,
            scenario_id,
            site_code,
        )

    async def _get_store_history(
        self,
        conn: asyncpg.Connection,
        *,
        site_code: str,
        cohort_month: str,
    ) -> list[asyncpg.Record]:
        rows = await conn.fetch(
            """
            WITH month_axis AS (
                SELECT to_char(
                    generate_series(
                        to_date($2 || '-01', 'YYYY-MM-DD') - INTERVAL '15 months',
                        to_date($2 || '-01', 'YYYY-MM-DD'),
                        INTERVAL '1 month'
                    ),
                    'YYYY-MM'
                ) AS import_month
            ),
            monthly_sales AS (
                SELECT
                    import_month,
                    site_code,
                    SUM(total_sales) AS total_sales,
                    SUM(total_quantity) AS total_quantity,
                    SUM(focus_quantity) AS focus_quantity,
                    SUM(receipt_count) AS receipt_count,
                    SUM(receipt_2plus_count) AS receipt_2plus_count,
                    COUNT(DISTINCT agent) FILTER (WHERE agent IS NOT NULL AND agent <> '-') AS active_agents,
                    MAX(working_days) AS working_days
                FROM reporting_agent_month
                WHERE site_code = $1
                  AND import_month IN (SELECT import_month FROM month_axis)
                GROUP BY import_month, site_code
            ),
            cartele AS (
                SELECT
                    import_month,
                    COALESCE(SUM(total_quantity), 0)::INT AS cartele_qty
                FROM reporting_cartela_day
                WHERE site_code = $1
                  AND import_month IN (SELECT import_month FROM month_axis)
                GROUP BY import_month
            ),
            daily_days AS (
                SELECT
                    import_month,
                    COUNT(DISTINCT sale_date)::INT AS working_days
                FROM reporting_agent_day
                WHERE site_code = $1
                  AND import_month IN (SELECT import_month FROM month_axis)
                GROUP BY import_month
            )
            SELECT
                ma.import_month,
                COALESCE(ms.total_sales, 0) AS total_sales,
                COALESCE(ms.total_quantity, 0) AS total_quantity,
                COALESCE(ms.focus_quantity, 0) AS focus_quantity,
                COALESCE(ms.receipt_count, 0) AS receipt_count,
                COALESCE(ms.receipt_2plus_count, 0) AS receipt_2plus_count,
                COALESCE(ms.active_agents, 0)::INT AS active_agents,
                COALESCE(dd.working_days, ms.working_days, 0)::INT AS working_days,
                COALESCE(c.cartele_qty, 0)::INT AS cartele_qty,
                COALESCE(st.target_value, 0) AS target_value
            FROM month_axis ma
            LEFT JOIN monthly_sales ms ON ms.import_month = ma.import_month
            LEFT JOIN cartele c ON c.import_month = ma.import_month
            LEFT JOIN daily_days dd ON dd.import_month = ma.import_month
            LEFT JOIN store_targets st ON st.import_month = ma.import_month AND st.site_code = $1
            ORDER BY ma.import_month
            """,
            site_code,
            cohort_month,
        )
        return list(rows)

    async def _get_store_agents(
        self,
        conn: asyncpg.Connection,
        *,
        site_code: str,
        cohort_month: str,
    ) -> list[asyncpg.Record]:
        rows = await conn.fetch(
            """
            WITH current_agents AS (
                SELECT
                    agent,
                    SUM(total_sales) AS total_sales,
                    SUM(total_quantity) AS total_quantity,
                    SUM(focus_quantity) AS focus_quantity,
                    SUM(receipt_count) AS receipt_count,
                    SUM(receipt_2plus_count) AS receipt_2plus_count
                FROM reporting_agent_month
                WHERE import_month = $2
                  AND site_code = $1
                  AND agent IS NOT NULL
                  AND agent <> '-'
                GROUP BY agent
            ),
            agent_history AS (
                SELECT
                    agent,
                    COUNT(DISTINCT import_month)::INT AS active_months_16,
                    SUM(total_sales) AS sales_16m
                FROM reporting_agent_month
                WHERE site_code = $1
                  AND import_month BETWEEN to_char(to_date($2 || '-01', 'YYYY-MM-DD') - INTERVAL '15 months', 'YYYY-MM')
                                       AND $2
                  AND agent IS NOT NULL
                  AND agent <> '-'
                GROUP BY agent
            ),
            store_total AS (
                SELECT COALESCE(SUM(total_sales), 0) AS total_sales
                FROM current_agents
            )
            SELECT
                ca.agent,
                ca.total_sales,
                ca.total_quantity,
                ca.focus_quantity,
                ca.receipt_count,
                ca.receipt_2plus_count,
                COALESCE(ah.active_months_16, 0)::INT AS active_months_16,
                COALESCE(ah.sales_16m, 0) AS sales_16m,
                CASE WHEN st.total_sales > 0 THEN ca.total_sales * 100.0 / st.total_sales ELSE 0 END AS sales_share_pct
            FROM current_agents ca
            CROSS JOIN store_total st
            LEFT JOIN agent_history ah ON ah.agent = ca.agent
            ORDER BY ca.total_sales DESC, ca.agent
            """,
            site_code,
            cohort_month,
        )
        return list(rows)

    async def get_store_detail(self, scenario_id: int, site_code: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            scenario_row = await self._get_store_scenario_row(
                conn,
                scenario_id=scenario_id,
                site_code=site_code,
            )
            if not scenario_row:
                return None
            history = await self._get_store_history(
                conn,
                site_code=site_code,
                cohort_month=scenario_row["cohort_month"],
            )
            agents = await self._get_store_agents(
                conn,
                site_code=site_code,
                cohort_month=scenario_row["cohort_month"],
            )
        return {
            "scenario": scenario_row,
            "history": history,
            "agents": agents,
        }
