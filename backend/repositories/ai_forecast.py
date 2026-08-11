from __future__ import annotations

from calendar import monthrange
from decimal import Decimal
from typing import Any, Literal

import asyncpg

from domain.filter_scope import FilterInput, normalize_filter_values


class AiForecastRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @staticmethod
    def _filter_clause(
        *,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: FilterInput,
    ) -> tuple[str, list[Any]]:
        clauses = ["s.locatie NOT ILIKE 'TR %'"]
        params: list[Any] = []
        site_codes = normalize_filter_values(site_code)
        if firma and not site_codes:
            params.append(firma)
            clauses.append(f"s.firma = ${len(params)}")
        if regional and not site_codes:
            params.append(regional)
            clauses.append(f"s.regional = ${len(params)}")
        if asm and not site_codes:
            params.append(asm)
            clauses.append(f"s.asm = ${len(params)}")
        if site_codes:
            params.append(site_codes)
            clauses.append(f"s.site_code = ANY(${len(params)}::TEXT[])")
        return " AND ".join(clauses), params

    @staticmethod
    def _actual_sum_expr(metric: Literal["sales_value", "units"], alias: str) -> str:
        if metric == "units":
            return f"SUM({alias}.total_quantity)::NUMERIC(14, 2)"
        return f"SUM({alias}.total_sales)::NUMERIC(14, 2)"

    async def fetch_latest_run(
        self,
        month: str,
        *,
        metric: Literal["sales_value", "units"],
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, forecast_month, source_month, metric, horizon, model_name, model_mode,
                       variant, generated_at, metadata
                FROM ai_forecast_runs
                WHERE status = 'completed'
                  AND metric = $2
                  AND horizon = 'current_month'
                  AND (forecast_month = $1 OR source_month = $1)
                ORDER BY
                  CASE WHEN forecast_month = $1 THEN 0 ELSE 1 END,
                  generated_at DESC,
                  id DESC
                LIMIT 1
                """,
                month,
                metric,
            )

    async def fetch_response_rows(
        self,
        *,
        run_id: int,
        forecast_month: str,
        metric: Literal["sales_value", "units"],
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: FilterInput,
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
        actual_month_expr = self._actual_sum_expr(metric, "ram")
        actual_day_expr = self._actual_sum_expr(metric, "agg")

        async with self.pool.acquire() as conn:
            actual_last_date = await conn.fetchval(
                """
                SELECT cutoff_date
                FROM reporting_sales_cutoff_v1
                WHERE import_month = $1
                """,
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
                    SELECT site_code, COALESCE({actual_month_expr}, 0)::NUMERIC(14, 2) AS actual_sales
                    FROM reporting_agent_month ram
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
                    SELECT agg.sale_date AS forecast_date, COALESCE({actual_day_expr}, 0)::NUMERIC(14, 2) AS actual_sales
                    FROM reporting_agent_day agg
                    JOIN forecast_stores fs ON fs.site_code = agg.site_code
                    WHERE agg.import_month = ${month_param}
                    GROUP BY agg.sale_date
                )
                SELECT
                    fd.forecast_date,
                    fd.forecast_sales,
                    COALESCE(ad.actual_sales, 0)::NUMERIC(14, 2) AS actual_sales,
                    (
                        ${actual_date_param}::DATE IS NOT NULL
                        AND fd.forecast_date <= ${actual_date_param}::DATE
                    ) AS has_actual
                FROM forecast_daily fd
                LEFT JOIN actual_daily ad ON ad.forecast_date = fd.forecast_date
                ORDER BY fd.forecast_date
                """,
                *filter_params,
                run_id,
                forecast_month,
                actual_last_date,
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
                    "has_actual": bool(row["has_actual"]),
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

    async def fetch_latest_rolling_runs(
        self,
        *,
        anchor_month: str,
        start_month: str,
        end_month: str,
        metric: Literal["sales_value", "units"],
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT DISTINCT ON (forecast_month)
                       id, forecast_month, source_month, metric, horizon, model_name, model_mode,
                       variant, generated_at, metadata
                FROM ai_forecast_runs
                WHERE status = 'completed'
                  AND metric = $1
                  AND horizon = 'rolling_12m'
                  AND forecast_month BETWEEN $2 AND $3
                  AND (
                      metadata->>'anchor_month' = $4
                      OR metadata->>'anchor_month' IS NULL
                  )
                ORDER BY
                  forecast_month,
                  CASE WHEN metadata->>'anchor_month' = $4 THEN 0 ELSE 1 END,
                  generated_at DESC,
                  id DESC
                """,
                metric,
                start_month,
                end_month,
                anchor_month,
            )

    async def fetch_rolling_rows(
        self,
        *,
        run_ids: list[int],
        metric: Literal["sales_value", "units"],
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: FilterInput,
    ) -> dict[str, Any] | None:
        if not run_ids:
            return None

        filter_sql, filter_params = self._filter_clause(
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
        )
        run_ids_param = len(filter_params) + 1
        actual_month_expr = self._actual_sum_expr(metric, "ram")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH forecast AS (
                    SELECT
                        r.id AS run_id,
                        r.forecast_month,
                        f.site_code,
                        s.locatie,
                        s.firma,
                        s.regional,
                        s.asm,
                        f.forecast_sales
                    FROM ai_forecast_store_month f
                    JOIN ai_forecast_runs r ON r.id = f.run_id
                    JOIN stores s ON s.site_code = f.site_code
                    WHERE f.run_id = ANY(${run_ids_param}::BIGINT[])
                      AND {filter_sql}
                ),
                actual_month AS (
                    SELECT
                        ram.import_month AS forecast_month,
                        ram.site_code,
                        COALESCE({actual_month_expr}, 0)::NUMERIC(14, 2) AS actual_sales
                    FROM reporting_agent_month ram
                    WHERE ram.import_month IN (SELECT DISTINCT forecast_month FROM forecast)
                    GROUP BY ram.import_month, ram.site_code
                ),
                month_presence AS (
                    SELECT import_month AS forecast_month, true AS has_actual
                    FROM reporting_agent_month
                    WHERE import_month IN (SELECT DISTINCT forecast_month FROM forecast)
                    GROUP BY import_month
                )
                SELECT
                    f.forecast_month,
                    f.site_code,
                    f.locatie,
                    f.firma,
                    f.regional,
                    f.asm,
                    f.forecast_sales,
                    COALESCE(a.actual_sales, 0)::NUMERIC(14, 2) AS actual_sales,
                    COALESCE(mp.has_actual, false) AS has_actual
                FROM forecast f
                LEFT JOIN actual_month a
                  ON a.forecast_month = f.forecast_month
                 AND a.site_code = f.site_code
                LEFT JOIN month_presence mp ON mp.forecast_month = f.forecast_month
                ORDER BY f.forecast_month, f.forecast_sales DESC, f.locatie
                """,
                *filter_params,
                run_ids,
            )

        if not rows:
            return None

        monthly_map: dict[str, dict[str, Any]] = {}
        manager_map: dict[str, dict[str, Any]] = {}
        store_map: dict[str, dict[str, Any]] = {}
        distinct_stores: set[str] = set()
        total_forecast = Decimal("0")
        total_actual = Decimal("0")
        has_any_actual = False

        for row in rows:
            forecast_month = row["forecast_month"]
            site_code_value = row["site_code"]
            forecast_sales = row["forecast_sales"]
            actual_sales = row["actual_sales"]
            has_actual = bool(row["has_actual"])
            distinct_stores.add(site_code_value)
            total_forecast += forecast_sales
            if has_actual:
                total_actual += actual_sales
                has_any_actual = True

            month_item = monthly_map.setdefault(
                forecast_month,
                {
                    "forecast_month": forecast_month,
                    "store_codes": set(),
                    "forecast_sales": Decimal("0"),
                    "actual_sales": Decimal("0"),
                    "has_actual": False,
                },
            )
            month_item["store_codes"].add(site_code_value)
            month_item["forecast_sales"] += forecast_sales
            if has_actual:
                month_item["actual_sales"] += actual_sales
                month_item["has_actual"] = True

            manager = row["asm"] or row["regional"] or "Fara manager"
            manager_item = manager_map.setdefault(
                manager,
                {
                    "manager": manager,
                    "store_codes": set(),
                    "forecast_sales": Decimal("0"),
                    "actual_sales": Decimal("0"),
                    "has_actual": False,
                },
            )
            manager_item["store_codes"].add(site_code_value)
            manager_item["forecast_sales"] += forecast_sales
            if has_actual:
                manager_item["actual_sales"] += actual_sales
                manager_item["has_actual"] = True

            store_item = store_map.setdefault(
                site_code_value,
                {
                    "site_code": site_code_value,
                    "locatie": row["locatie"],
                    "firma": row["firma"],
                    "regional": row["regional"],
                    "asm": row["asm"],
                    "forecast_sales": Decimal("0"),
                    "actual_sales": Decimal("0"),
                    "has_actual": False,
                },
            )
            store_item["forecast_sales"] += forecast_sales
            if has_actual:
                store_item["actual_sales"] += actual_sales
                store_item["has_actual"] = True

        def finalize_actual(item: dict[str, Any]) -> dict[str, Any]:
            has_actual = bool(item.pop("has_actual", False))
            store_codes = item.pop("store_codes", None)
            if store_codes is not None:
                item["store_count"] = len(store_codes)
            if not has_actual:
                item["actual_sales"] = None
            return item

        months = [finalize_actual(monthly_map[month]) for month in sorted(monthly_map)]
        managers = [finalize_actual(item) for item in manager_map.values()]
        stores = [finalize_actual(item) for item in store_map.values()]

        return {
            "summary": {
                "store_count": len(distinct_stores),
                "forecast_sales": total_forecast,
                "actual_sales": total_actual if has_any_actual else None,
            },
            "months": sorted(months, key=lambda item: item["forecast_month"]),
            "managers": sorted(managers, key=lambda item: item["forecast_sales"], reverse=True),
            "stores": sorted(stores, key=lambda item: item["forecast_sales"], reverse=True),
        }
