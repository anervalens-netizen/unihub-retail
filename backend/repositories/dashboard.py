from __future__ import annotations

from typing import Any
import asyncpg


class DashboardRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_summary(self, clauses: list[str], params: list[Any]) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                WITH filtered_days AS (
                    SELECT *
                    FROM reporting_agent_day agg
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
                    SELECT import_month, is_month_final, days_in_month
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
                    FROM cartela_sales c
                    WHERE c.import_month = $1
                      AND EXISTS (
                          SELECT 1
                          FROM filtered_days fd
                          WHERE fd.site_code = c.site_code
                            AND fd.agent = c.agent
                            AND fd.import_month = c.import_month
                      )
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

    async def fetch_daily_sales(self, clauses: list[str], params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    agg.sale_date,
                    COALESCE(SUM(agg.total_sales), 0) AS total_sales,
                    COALESCE(SUM(agg.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(agg.receipt_count), 0)::INT AS receipt_count
                FROM reporting_agent_day agg
                WHERE {" AND ".join(clauses)}
                GROUP BY agg.sale_date
                ORDER BY agg.sale_date ASC
                """,
                *params,
            )

    async def fetch_monthly_history(self, sales_clauses: list[str], params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH recent_months AS (
                    SELECT import_month
                    FROM (
                        SELECT import_month
                        FROM import_snapshots
                        WHERE import_month <= $1
                          AND status = 'completed'
                        ORDER BY import_month DESC
                        LIMIT $2
                    ) months
                ),
                filtered_days AS MATERIALIZED (
                    SELECT *
                    FROM reporting_agent_day agg
                    WHERE {" AND ".join(sales_clauses)}
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
                    WHERE stg.import_month IN (SELECT import_month FROM recent_months)
                      AND EXISTS (
                          SELECT 1
                          FROM filtered_days fd
                          WHERE fd.import_month = stg.import_month
                            AND fd.site_code = stg.site_code
                      )
                    GROUP BY stg.import_month
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
                    ss.total_quantity,
                    ss.total_receipts,
                    ss.proc_bon2acc,
                    ss.prc_focus_acc_qty,
                    ss.total_stores,
                    ss.total_agents,
                    ss.working_days,
                    ss.daily_average
                FROM sales_summary ss
                LEFT JOIN target_summary ts ON ts.month = ss.month
                ORDER BY ss.month ASC
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
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH sales_agg AS (
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
                    WHERE st.import_month >= $1 AND st.import_month <= $2
                      AND EXISTS (
                          SELECT 1 FROM sales_agg sa
                          WHERE sa.import_month = st.import_month
                            AND sa.site_code = st.site_code
                      )
                    GROUP BY st.import_month
                )
                SELECT ms.import_month,
                       ms.total_sales,
                       COALESCE(mt.total_target, 0) AS total_target,
                       ms.total_quantity
                FROM month_sales ms
                LEFT JOIN month_targets mt ON mt.import_month = ms.import_month
                ORDER BY ms.import_month
                """,
                *rep_params,
            )
