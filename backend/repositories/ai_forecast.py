from __future__ import annotations

from calendar import monthrange
from decimal import Decimal
from typing import Any

import asyncpg


class AiForecastRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @staticmethod
    def _filter_clause(
        *,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> tuple[str, list[Any]]:
        clauses = ["s.locatie NOT ILIKE 'TR %'"]
        params: list[Any] = []
        if firma:
            params.append(firma)
            clauses.append(f"s.firma = ${len(params)}")
        if regional:
            params.append(regional)
            clauses.append(f"s.regional = ${len(params)}")
        if asm:
            params.append(asm)
            clauses.append(f"s.asm = ${len(params)}")
        if site_code:
            params.append(site_code)
            clauses.append(f"s.site_code = ${len(params)}")
        return " AND ".join(clauses), params

    async def fetch_latest_run(self, month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, forecast_month, source_month, model_name, model_mode,
                       variant, generated_at, metadata
                FROM ai_forecast_runs
                WHERE status = 'completed'
                  AND (forecast_month = $1 OR source_month = $1)
                ORDER BY
                  CASE WHEN forecast_month = $1 THEN 0 ELSE 1 END,
                  generated_at DESC,
                  id DESC
                LIMIT 1
                """,
                month,
            )

    async def fetch_response_rows(
        self,
        *,
        run_id: int,
        forecast_month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> dict[str, Any] | None:
        filter_sql, filter_params = self._filter_clause(
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
        )
        run_param = len(filter_params) + 1
        month_param = len(filter_params) + 2
        actual_date_param = len(filter_params) + 3

        async with self.pool.acquire() as conn:
            actual_last_date = await conn.fetchval(
                "SELECT MAX(sale_date) FROM reporting_agent_day WHERE import_month = $1",
                forecast_month,
            )
            rows = await conn.fetch(
                f"""
                WITH forecast AS (
                    SELECT
                        f.site_code,
                        s.locatie,
                        s.firma,
                        s.regional,
                        s.asm,
                        f.forecast_sales
                    FROM ai_forecast_store_month f
                    JOIN stores s ON s.site_code = f.site_code
                    WHERE f.run_id = ${run_param}
                      AND {filter_sql}
                ),
                actual_month AS (
                    SELECT site_code, COALESCE(SUM(total_sales), 0)::NUMERIC(14, 2) AS actual_sales
                    FROM reporting_agent_month
                    WHERE import_month = ${month_param}
                    GROUP BY site_code
                ),
                expected AS (
                    SELECT site_code, COALESCE(SUM(forecast_sales), 0)::NUMERIC(14, 2) AS expected_sales_to_date
                    FROM ai_forecast_store_day
                    WHERE run_id = ${run_param}
                      AND (${actual_date_param}::DATE IS NOT NULL AND forecast_date <= ${actual_date_param}::DATE)
                    GROUP BY site_code
                )
                SELECT
                    f.site_code,
                    f.locatie,
                    f.firma,
                    f.regional,
                    f.asm,
                    f.forecast_sales,
                    COALESCE(e.expected_sales_to_date, 0)::NUMERIC(14, 2) AS expected_sales_to_date,
                    COALESCE(a.actual_sales, 0)::NUMERIC(14, 2) AS actual_sales
                FROM forecast f
                LEFT JOIN actual_month a ON a.site_code = f.site_code
                LEFT JOIN expected e ON e.site_code = f.site_code
                ORDER BY f.forecast_sales DESC, f.locatie
                """,
                *filter_params,
                run_id,
                forecast_month,
                actual_last_date,
            )
            daily = await conn.fetch(
                f"""
                WITH forecast_stores AS (
                    SELECT f.site_code
                    FROM ai_forecast_store_month f
                    JOIN stores s ON s.site_code = f.site_code
                    WHERE f.run_id = ${run_param}
                      AND {filter_sql}
                ),
                forecast_daily AS (
                    SELECT d.forecast_date, COALESCE(SUM(d.forecast_sales), 0)::NUMERIC(14, 2) AS forecast_sales
                    FROM ai_forecast_store_day d
                    JOIN forecast_stores fs ON fs.site_code = d.site_code
                    WHERE d.run_id = ${run_param}
                    GROUP BY d.forecast_date
                ),
                actual_daily AS (
                    SELECT agg.sale_date AS forecast_date, COALESCE(SUM(agg.total_sales), 0)::NUMERIC(14, 2) AS actual_sales
                    FROM reporting_agent_day agg
                    JOIN forecast_stores fs ON fs.site_code = agg.site_code
                    WHERE agg.import_month = ${month_param}
                    GROUP BY agg.sale_date
                )
                SELECT
                    fd.forecast_date,
                    fd.forecast_sales,
                    COALESCE(ad.actual_sales, 0)::NUMERIC(14, 2) AS actual_sales
                FROM forecast_daily fd
                LEFT JOIN actual_daily ad ON ad.forecast_date = fd.forecast_date
                ORDER BY fd.forecast_date
                """,
                *filter_params,
                run_id,
                forecast_month,
            )

        if not rows:
            return None

        store_rows = []
        manager_map: dict[str, dict[str, Any]] = {}
        total_forecast = Decimal("0")
        total_expected = Decimal("0")
        total_actual = Decimal("0")
        for row in rows:
            forecast_sales = row["forecast_sales"]
            expected_sales = row["expected_sales_to_date"]
            actual_sales = row["actual_sales"]
            total_forecast += forecast_sales
            total_expected += expected_sales
            total_actual += actual_sales
            store_rows.append(dict(row))
            manager = row["asm"] or row["regional"] or "Fara manager"
            item = manager_map.setdefault(
                manager,
                {
                    "manager": manager,
                    "store_count": 0,
                    "forecast_sales": Decimal("0"),
                    "expected_sales_to_date": Decimal("0"),
                    "actual_sales": Decimal("0"),
                },
            )
            item["store_count"] += 1
            item["forecast_sales"] += forecast_sales
            item["expected_sales_to_date"] += expected_sales
            item["actual_sales"] += actual_sales

        year, month_number = map(int, forecast_month.split("-"))
        days_in_month = monthrange(year, month_number)[1]
        cumulative_forecast = Decimal("0")
        cumulative_actual = Decimal("0")
        daily_rows = []
        for row in daily:
            cumulative_forecast += row["forecast_sales"]
            cumulative_actual += row["actual_sales"]
            daily_rows.append(
                {
                    "forecast_date": row["forecast_date"],
                    "forecast_sales": row["forecast_sales"],
                    "actual_sales": row["actual_sales"],
                    "cumulative_forecast": cumulative_forecast,
                    "cumulative_actual": cumulative_actual,
                }
            )

        return {
            "actual_last_date": actual_last_date,
            "days_in_month": days_in_month,
            "summary": {
                "forecast_month": forecast_month,
                "days_elapsed": actual_last_date.day if actual_last_date else 0,
                "days_in_month": days_in_month,
                "store_count": len(store_rows),
                "forecast_sales": total_forecast,
                "expected_sales_to_date": total_expected,
                "actual_sales": total_actual,
            },
            "managers": sorted(manager_map.values(), key=lambda item: item["forecast_sales"], reverse=True),
            "stores": store_rows,
            "daily": daily_rows,
        }
