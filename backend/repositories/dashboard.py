from __future__ import annotations

from typing import Any
import asyncpg


class DashboardRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_summary(
        self,
        clauses: list[str],
        params: list[Any],
        cartela_clauses: list[str],
        current_scope: bool = False,
    ) -> asyncpg.Record | None:
        store_join = "JOIN stores s ON s.site_code = agg.site_code" if current_scope else ""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                WITH filtered_days AS (
                    SELECT agg.*
                    FROM reporting_agent_day agg
                    {store_join}
                    WHERE {" AND ".join(clauses)}
                ),
                sales_summary AS (
                    SELECT
                        fd.import_month AS month,
                        COALESCE(SUM(fd.total_sales), 0) AS total_sales,
                        COALESCE(SUM(fd.total_quantity), 0)::INT AS total_quantity,
                        COALESCE(SUM(fd.receipt_count), 0)::INT AS total_receipts,
                        ROUND(COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0), 2) AS proc_bon2acc,
                        ROUND(COALESCE(SUM(fd.focus_quantity), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0), 2) AS prc_focus_acc_qty,
                        COUNT(DISTINCT fd.site_code)::INT AS total_stores,
                        COUNT(DISTINCT fd.agent)::INT AS total_agents,
                        COUNT(DISTINCT fd.sale_date)::INT AS working_days,
                        ROUND(
                            COALESCE(SUM(fd.total_sales), 0) / NULLIF(COUNT(DISTINCT fd.sale_date), 0),
                            2
                        ) AS daily_average
                    FROM filtered_days fd
                    GROUP BY fd.import_month
                ),
                target_summary AS (
                    SELECT
                        stg.import_month AS month,
                        COALESCE(SUM(stg.target_value), 0) AS total_target
                    FROM store_targets stg
                    WHERE stg.import_month = $1
                      AND EXISTS (
                          SELECT 1
                          FROM filtered_days fd
                          WHERE fd.site_code = stg.site_code
                      )
                    GROUP BY stg.import_month
                ),
                month_meta AS (
                    SELECT 
                        import_month, 
                        is_month_final,
                        EXTRACT(DAY FROM (DATE(import_month || '-01') + INTERVAL '1 month' - INTERVAL '1 day'))::INT AS days_in_month
                    FROM import_snapshots
                    WHERE import_month = $1
                      AND status = 'completed'
                    ORDER BY created_at DESC
                    LIMIT 1
                ),
                last_sale AS (
                    SELECT MAX(sale_date) AS last_sale_date
                    FROM filtered_days
                ),
                cartele_summary AS (
                    SELECT
                        COALESCE(SUM(c.quantity), 0)::INT AS cartele_qty
                    FROM sales_transactions c
                    JOIN stores cs ON cs.site_code = c.site_code
                    WHERE c.import_month = $1
                      AND c.is_cartela = true
                      AND {" AND ".join(cartela_clauses)}
                )
                SELECT
                    ss.month,
                    ss.total_sales,
                    COALESCE(ts.total_target, 0) AS total_target,
                    CASE
                        WHEN COALESCE(ts.total_target, 0) > 0
                        THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                        ELSE NULL
                    END AS target_progress_pct,
                    CASE
                        WHEN COALESCE(mm.is_month_final, true) = false
                             AND ls.last_sale_date IS NOT NULL
                             AND EXTRACT(DAY FROM ls.last_sale_date) > 0
                        THEN ROUND(ss.total_sales / EXTRACT(DAY FROM ls.last_sale_date) * mm.days_in_month, 2)
                        ELSE ss.total_sales
                    END AS forecast_sales,
                    CASE
                        WHEN COALESCE(ts.total_target, 0) > 0
                             AND COALESCE(mm.is_month_final, true) = false
                             AND ls.last_sale_date IS NOT NULL
                             AND EXTRACT(DAY FROM ls.last_sale_date) > 0
                        THEN ROUND((ss.total_sales / EXTRACT(DAY FROM ls.last_sale_date) * mm.days_in_month) * 100.0 / ts.total_target, 2)
                        WHEN COALESCE(ts.total_target, 0) > 0
                        THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                        ELSE NULL
                    END AS forecast_target_progress_pct,
                    ss.total_quantity,
                    ss.total_receipts,
                    ss.proc_bon2acc,
                    ss.prc_focus_acc_qty,
                    ss.total_stores,
                    ss.total_agents,
                    ss.working_days,
                    ss.daily_average,
                    COALESCE(mm.is_month_final, true) AS is_month_final,
                    ls.last_sale_date,
                    CASE
                        WHEN ls.last_sale_date IS NOT NULL THEN EXTRACT(DAY FROM ls.last_sale_date)::INT
                        ELSE NULL
                    END AS imported_day_of_month,
                    mm.days_in_month,
                    cs.cartele_qty
                FROM sales_summary ss
                LEFT JOIN target_summary ts ON ts.month = ss.month
                LEFT JOIN month_meta mm ON mm.import_month = ss.month
                LEFT JOIN last_sale ls ON true
                LEFT JOIN cartele_summary cs ON true
                """,
                *params,
            )

    async def fetch_daily_sales(
        self, clauses: list[str], params: list[Any], current_scope: bool = False
    ) -> list[asyncpg.Record]:
        store_join = "JOIN stores s ON s.site_code = agg.site_code" if current_scope else ""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    agg.sale_date,
                    COALESCE(SUM(agg.total_sales), 0) AS total_sales,
                    COALESCE(SUM(agg.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(agg.receipt_count), 0)::INT AS receipt_count
                FROM reporting_agent_day agg
                {store_join}
                WHERE {" AND ".join(clauses)}
                GROUP BY agg.sale_date
                ORDER BY agg.sale_date ASC
                """,
                *params,
            )

    async def fetch_monthly_history(
        self, sales_clauses: list[str], params: list[Any], current_scope: bool = False
    ) -> list[asyncpg.Record]:
        store_join = "JOIN stores s ON s.site_code = agg.site_code" if current_scope else ""
        target_store_clauses = [
            clause.replace("agg.", "s.").replace("s.agent", "agg.agent")
            for clause in sales_clauses
            if ".agent" not in clause
        ]
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH recent_months AS (
                    SELECT TO_CHAR(m, 'YYYY-MM') AS import_month
                    FROM GENERATE_SERIES(
                        ($1 || '-01')::DATE - ($2 - 1) * INTERVAL '1 month',
                        ($1 || '-01')::DATE,
                        '1 month'::INTERVAL
                    ) m
                ),
                filtered_days AS MATERIALIZED (
                    SELECT
                        agg.import_month,
                        agg.sale_date,
                        agg.site_code,
                        agg.agent,
                        agg.total_sales,
                        agg.total_quantity,
                        agg.receipt_count,
                        agg.receipt_2plus_count,
                        agg.focus_quantity
                    FROM reporting_agent_day agg
                    {store_join}
                    WHERE agg.import_month >= TO_CHAR(($1 || '-01')::DATE - ($2 - 1) * INTERVAL '1 month', 'YYYY-MM')
                      AND agg.import_month <= $1
                      {" AND " + " AND ".join(sales_clauses) if sales_clauses else ""}
                ),
                sales_summary AS (
                    SELECT
                        fd.import_month AS month,
                        COALESCE(SUM(fd.total_sales), 0) AS total_sales,
                        COALESCE(SUM(fd.total_quantity), 0)::INT AS total_quantity,
                        COALESCE(SUM(fd.receipt_count), 0)::INT AS total_receipts,
                        ROUND(
                            COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0
                            / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0),
                            2
                        ) AS proc_bon2acc,
                        ROUND(
                            COALESCE(SUM(fd.focus_quantity), 0) * 100.0
                            / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0),
                            2
                        ) AS prc_focus_acc_qty,
                        COUNT(DISTINCT fd.site_code)::INT AS total_stores,
                        COUNT(DISTINCT fd.agent)::INT AS total_agents,
                        COUNT(DISTINCT fd.sale_date)::INT AS working_days,
                        ROUND(COALESCE(SUM(fd.total_sales), 0) / NULLIF(COUNT(DISTINCT fd.sale_date), 0), 2) AS daily_average
                    FROM filtered_days fd
                    GROUP BY fd.import_month
                ),
                target_summary AS (
                    SELECT
                        stg.import_month AS month,
                        COALESCE(SUM(stg.target_value), 0) AS total_target
                    FROM store_targets stg
                    JOIN stores s ON s.site_code = stg.site_code
                    WHERE stg.import_month IN (SELECT import_month FROM recent_months)
                      {" AND " + " AND ".join(target_store_clauses) if target_store_clauses else ""}
                    GROUP BY stg.import_month
                )
                SELECT
                    rm.import_month AS month,
                    COALESCE(ss.total_sales, 0) AS total_sales,
                    COALESCE(ts.total_target, 0) AS total_target,
                    CASE
                        WHEN COALESCE(ts.total_target, 0) > 0
                        THEN ROUND(COALESCE(ss.total_sales, 0) * 100.0 / ts.total_target, 2)
                        ELSE NULL
                    END AS target_progress_pct,
                    COALESCE(ss.total_quantity, 0) AS total_quantity,
                    COALESCE(ss.total_receipts, 0) AS total_receipts,
                    COALESCE(ss.proc_bon2acc, 0) AS proc_bon2acc,
                    COALESCE(ss.prc_focus_acc_qty, 0) AS prc_focus_acc_qty,
                    COALESCE(ss.total_stores, 0) AS total_stores,
                    COALESCE(ss.total_agents, 0) AS total_agents,
                    COALESCE(ss.working_days, 0) AS working_days,
                    COALESCE(ss.daily_average, 0) AS daily_average
                FROM recent_months rm
                LEFT JOIN sales_summary ss ON ss.month = rm.import_month
                LEFT JOIN target_summary ts ON ts.month = rm.import_month
                ORDER BY rm.import_month ASC
                """,
                *params,
            )

    async def fetch_year_history_agg(self, year: int, hist_clauses: list[str], hist_params: list[Any]) -> asyncpg.Record | None:
        where_hist = f"AND {' AND '.join(hist_clauses)}" if hist_clauses else ""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                SELECT COALESCE(SUM(has.total_value), 0) AS total_sales,
                       COALESCE(SUM(has.total_qty), 0)::INT AS total_quantity
                FROM historical_annual_sales has
                JOIN stores s ON s.site_code = has.site_code
                WHERE has.year = $1 {where_hist}
                """,
                *hist_params,
            )

    async def fetch_year_history_monthly(self, rep_clauses: list[str], rep_params: list[Any]) -> list[asyncpg.Record]:
        where_rep = f"AND {' AND '.join(rep_clauses)}" if rep_clauses else ""
        store_clauses = [
            clause.replace("agg.", "s.").replace("s.agent", "agg.agent")
            for clause in rep_clauses
            if ".agent" not in clause
        ]
        where_store = f"AND {' AND '.join(store_clauses)}" if store_clauses else ""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH all_months AS (
                    SELECT TO_CHAR(m, 'YYYY-MM') AS import_month
                    FROM GENERATE_SERIES(
                        ($1 || '-01')::DATE,
                        ($2 || '-01')::DATE,
                        '1 month'::INTERVAL
                    ) m
                ),
                sales_agg AS (
                    SELECT agg.import_month, agg.site_code,
                           SUM(agg.total_sales)    AS total_sales,
                           SUM(agg.total_quantity) AS total_quantity
                    FROM reporting_agent_month agg
                    JOIN stores s ON s.site_code = agg.site_code
                    WHERE agg.import_month >= $1 AND agg.import_month <= $2
                      {where_rep}
                    GROUP BY agg.import_month, agg.site_code
                ),
                month_sales AS (
                    SELECT import_month,
                           SUM(total_sales)          AS total_sales,
                           SUM(total_quantity)::INT  AS total_quantity
                    FROM sales_agg
                    GROUP BY import_month
                ),
                month_targets AS (
                    SELECT st.import_month, SUM(st.target_value) AS total_target
                    FROM store_targets st
                    JOIN stores s ON s.site_code = st.site_code
                    WHERE st.import_month >= $1 AND st.import_month <= $2
                      {where_store}
                    GROUP BY st.import_month
                )
                SELECT am.import_month,
                       COALESCE(ms.total_sales, 0) AS total_sales,
                       COALESCE(mt.total_target, 0) AS total_target,
                       COALESCE(ms.total_quantity, 0) AS total_quantity
                FROM all_months am
                LEFT JOIN month_sales ms ON ms.import_month = am.import_month
                LEFT JOIN month_targets mt ON mt.import_month = am.import_month
                ORDER BY am.import_month
                """,
                *rep_params,
            )
