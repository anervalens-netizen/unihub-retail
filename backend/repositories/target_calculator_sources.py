from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg

from retail_filters import distribution_location_clause


class TargetCalculatorSourcesRepositoryMixin:
    pool: asyncpg.Pool

    async def get_latest_sales_month(self, before_month: str | None = None) -> str | None:
        condition = "WHERE import_month < $1" if before_month else ""
        params = (before_month,) if before_month else ()
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT MAX(import_month) FROM reporting_agent_month {condition}",
                *params,
            )

    async def get_target_total(self, month: str) -> Decimal:
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT COALESCE(SUM(target_value), 0) FROM store_targets WHERE import_month = $1",
                month,
            )
        return Decimal(value or 0)

    async def get_active_cohort(self, cohort_month: str, target_month: str | None = None) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    ram.site_code,
                    s.locatie,
                    s.firma,
                    s.regional,
                    s.asm
                FROM reporting_agent_month ram
                JOIN stores s ON s.site_code = ram.site_code
                WHERE ram.import_month = $1
                  AND s.is_active = TRUE
                  AND {distribution_location_clause("s")}
                  AND NOT EXISTS (
                      SELECT 1
                      FROM target_calculator_store_exclusions tcse
                      WHERE tcse.site_code = ram.site_code
                        AND ($2::TEXT IS NULL OR tcse.effective_from_month <= $2)
                  )
                GROUP BY ram.site_code, s.locatie, s.firma, s.regional, s.asm
                ORDER BY s.regional, s.locatie, ram.site_code
                """,
                cohort_month,
                target_month,
            )

    async def get_target_rule_exception_master(self, site_codes: list[str]) -> list[asyncpg.Record]:
        """Resolve Target rule exception keys by exact canonical master code only."""
        if not site_codes:
            return []
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT site_code, locatie
                FROM stores
                WHERE site_code = ANY($1::TEXT[])
                ORDER BY site_code
                """,
                site_codes,
            )

    async def get_source_metrics(
        self,
        site_codes: list[str],
        months: list[str],
    ) -> list[asyncpg.Record]:
        if not site_codes or not months:
            return []
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH requested_months AS (
                    SELECT unnest($1::text[]) AS import_month
                ),
                requested_stores AS (
                    SELECT unnest($2::text[]) AS site_code
                ),
                sales AS (
                    SELECT import_month, site_code, SUM(total_sales) AS realized
                    FROM reporting_agent_month
                    WHERE import_month = ANY($1::text[])
                      AND site_code = ANY($2::text[])
                    GROUP BY import_month, site_code
                ),
                historical_sales AS (
                    SELECT hms.import_month, hms.site_code, SUM(hms.total_value) AS realized
                    FROM historical_monthly_sales hms
                    WHERE hms.import_month = ANY($1::text[])
                      AND hms.site_code = ANY($2::text[])
                      AND NOT EXISTS (
                          SELECT 1
                          FROM sales s
                          WHERE s.import_month = hms.import_month
                            AND s.site_code = hms.site_code
                      )
                    GROUP BY hms.import_month, hms.site_code
                ),
                combined_sales AS (
                    SELECT import_month, site_code, realized FROM sales
                    UNION ALL
                    SELECT import_month, site_code, realized FROM historical_sales
                )
                SELECT
                    m.import_month,
                    st.site_code,
                    COALESCE(t.target_value, 0) AS target,
                    COALESCE(s.realized, 0) AS realized
                FROM requested_months m
                CROSS JOIN requested_stores st
                LEFT JOIN store_targets t
                  ON t.import_month = m.import_month AND t.site_code = st.site_code
                LEFT JOIN combined_sales s
                  ON s.import_month = m.import_month AND s.site_code = st.site_code
                ORDER BY m.import_month, st.site_code
                """,
                months,
                site_codes,
            )

    async def _get_pnl_inputs(
        self,
        conn: asyncpg.Connection,
        *,
        site_codes: list[str],
        target_date: date,
    ) -> tuple[list[date], list[asyncpg.Record]]:
        required_categories = ["v11", "c11", "c4", "c5", "c6"]
        expected_pairs = len(site_codes) * len(required_categories)
        pnl_month_records = await conn.fetch(
            """
            WITH resolved AS (
                SELECT
                    COALESCE(link.site_code, pnl.source_site_code) AS site_code,
                    pnl.period,
                    pnl.category_code
                FROM store_pnl_monthly pnl
                LEFT JOIN store_pnl_site_links link
                  ON link.company_name = pnl.company_name
                 AND link.source_site_code = pnl.source_site_code
                WHERE pnl.data_kind = 'actual'
                  AND pnl.period < $1
                  AND pnl.category_code = ANY($2::TEXT[])
                  AND COALESCE(link.site_code, pnl.source_site_code) = ANY($3::TEXT[])
            )
            SELECT period
            FROM resolved
            GROUP BY period
            HAVING COUNT(DISTINCT (site_code, category_code)) = $4
            ORDER BY period DESC
            LIMIT 3
            """,
            target_date,
            required_categories,
            site_codes,
            expected_pairs,
        )
        pnl_months = sorted(record["period"] for record in pnl_month_records)
        if len(pnl_months) != 3:
            return pnl_months, []
        pnl_rows = await conn.fetch(
            """
            SELECT
                COALESCE(link.site_code, pnl.source_site_code) AS site_code,
                pnl.category_code,
                SUM(pnl.amount)::NUMERIC(16, 2) AS amount
            FROM store_pnl_monthly pnl
            LEFT JOIN store_pnl_site_links link
              ON link.company_name = pnl.company_name
             AND link.source_site_code = pnl.source_site_code
            WHERE pnl.data_kind = 'actual'
              AND pnl.period = ANY($1::DATE[])
              AND pnl.category_code = ANY($2::TEXT[])
              AND COALESCE(link.site_code, pnl.source_site_code) = ANY($3::TEXT[])
            GROUP BY COALESCE(link.site_code, pnl.source_site_code), pnl.category_code
            ORDER BY site_code, pnl.category_code
            """,
            pnl_months,
            required_categories,
            site_codes,
        )
        return pnl_months, list(pnl_rows)

    async def _get_forecast_inputs(
        self,
        conn: asyncpg.Connection,
        *,
        site_codes: list[str],
        target_month: str,
    ) -> tuple[asyncpg.Record | None, list[asyncpg.Record]]:
        forecast_run = await conn.fetchrow(
            """
            SELECT id, forecast_month, source_month, model_name, model_mode,
                   variant, generated_at::TEXT, metadata
            FROM ai_forecast_runs
            WHERE status = 'completed'
              AND metric = 'sales_value'
              AND horizon = 'current_month'
              AND forecast_month = $1
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            target_month,
        )
        if not forecast_run:
            return None, []
        forecast_rows = await conn.fetch(
            """
            WITH requested_stores AS (
                SELECT DISTINCT UNNEST($2::TEXT[]) AS site_code
            ), realized_coverage AS (
                SELECT
                    reporting.site_code,
                    MAX(reporting.sale_date) AS cutoff_date
                FROM reporting_agent_day reporting
                WHERE reporting.import_month = $3
                  AND reporting.site_code = ANY($2::TEXT[])
                GROUP BY reporting.site_code
            )
            SELECT
                requested_stores.site_code,
                forecast.forecast_sales,
                (forecast.site_code IS NOT NULL) AS forecast_present,
                realized_coverage.cutoff_date,
                (realized_coverage.site_code IS NOT NULL) AS realized_present
            FROM requested_stores
            LEFT JOIN ai_forecast_store_month forecast
              ON forecast.run_id = $1
             AND forecast.site_code = requested_stores.site_code
            LEFT JOIN realized_coverage
              ON realized_coverage.site_code = requested_stores.site_code
            ORDER BY requested_stores.site_code
            """,
            forecast_run["id"],
            site_codes,
            forecast_run["source_month"],
        )
        return forecast_run, list(forecast_rows)

    async def get_profitability_inputs(
        self,
        *,
        site_codes: list[str],
        target_month: str,
    ) -> dict[str, Any]:
        if not site_codes:
            return {
                "pnl_months": [],
                "pnl_rows": [],
                "forecast_run": None,
                "forecast_rows": [],
            }
        target_date = date.fromisoformat(f"{target_month}-01")
        async with self.pool.acquire() as conn:
            pnl_months, pnl_rows = await self._get_pnl_inputs(
                conn,
                site_codes=site_codes,
                target_date=target_date,
            )
            forecast_run, forecast_rows = await self._get_forecast_inputs(
                conn,
                site_codes=site_codes,
                target_month=target_month,
            )
        return {
            "pnl_months": [period.strftime("%Y-%m") for period in pnl_months],
            "pnl_rows": pnl_rows,
            "forecast_run": forecast_run,
            "forecast_rows": forecast_rows,
        }

    async def get_effective_target_rule_set(self, target_month: str) -> asyncpg.Record | None:
        """Return the single effective-dated Target rule-set for a calculation month."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, version, effective_from_month, effective_to_month, rules, rules_sha256
                FROM target_calculator_effective_rule_sets
                WHERE effective_from_month <= $1
                  AND (effective_to_month IS NULL OR effective_to_month > $1)
                ORDER BY effective_from_month DESC, version DESC
                LIMIT 1
                """,
                target_month,
            )
