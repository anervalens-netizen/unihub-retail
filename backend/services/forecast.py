"""Forecast helpers shared între CRM și HR.

Extras din routers/crm.py ca să rup importul cross-router hr.py → crm.py.
Routere-le nu mai depind unul de altul; ambele depind de services/.

Motivație: importul circular implicit (hr.py importa get_forecast_factor
din routers/crm.py) face greu de testat fiecare router izolat și crează
cuplaj artificial — orice modificare în crm.py necesită verificare în hr.py.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def business_forecast_factor_ctes(
    month_parameter: str = "$1",
    *,
    result_name: str = "forecast_meta",
    cutoff_parameter: str | None = None,
) -> str:
    """Canonical SQL CTEs for the current business-calendar forecast factor."""
    if cutoff_parameter is None:
        month_meta_sql = f"""
            SELECT
                COALESCE(BOOL_OR(snap.is_month_final), true) AS is_final,
                MAX(rid.sale_date) AS last_sale_date
            FROM import_snapshots snap
            LEFT JOIN (
                SELECT MAX(sale_date) AS sale_date
                FROM reporting_item_day
                WHERE import_month = {month_parameter}
            ) rid ON true
            WHERE snap.import_month = {month_parameter}
        """
    else:
        month_meta_sql = f"""
            SELECT
                false AS is_final,
                MAX(sale_date) AS last_sale_date
            FROM reporting_item_day
            WHERE import_month = {month_parameter}
              AND sale_date <= {cutoff_parameter}
        """
    return f"""
        forecast_month_meta AS (
            {month_meta_sql}
        ),
        forecast_latest_business_run AS (
            SELECT run.id
            FROM ai_forecast_runs run
            WHERE run.status = 'completed'
              AND run.metric = 'sales_value'
              AND run.horizon = 'current_month'
              AND run.forecast_month = {month_parameter}
            ORDER BY run.generated_at DESC, run.id DESC
            LIMIT 1
        ),
        forecast_business_weights AS (
            SELECT
                SUM(GREATEST(day.forecast_sales, 0)) AS total_weight,
                SUM(GREATEST(day.forecast_sales, 0)) FILTER (
                    WHERE day.forecast_date <= month_meta.last_sale_date
                ) AS elapsed_weight
            FROM ai_forecast_store_day day
            JOIN forecast_latest_business_run run ON run.id = day.run_id
            CROSS JOIN forecast_month_meta month_meta
        ),
        {result_name} AS (
            SELECT
                CASE
                    WHEN NOT month_meta.is_final
                     AND weights.total_weight > 0
                     AND weights.elapsed_weight > 0
                    THEN GREATEST(1::NUMERIC, weights.total_weight / weights.elapsed_weight)
                    ELSE 1::NUMERIC
                END AS forecast_factor
            FROM forecast_month_meta month_meta
            CROSS JOIN forecast_business_weights weights
        )
    """


async def get_forecast_factor(
    conn: Any,
    month: str,
    *,
    cutoff_date: date | None = None,
) -> float:
    """Returnează factorul ponderat de calendarul business al forecastului.

    Pentru o lună parțială folosim distribuția zilnică din ultima rulare AI
    finalizată, nu raportul implicit zile calendaristice/zi curentă. Dacă
    modelul business lipsește sau nu are greutate până la cutoff, nu inventăm
    extrapolare: factorul rămâne 1.0.
    """
    meta = await conn.fetchrow(
        f"""
        WITH {business_forecast_factor_ctes(cutoff_parameter="$2" if cutoff_date else None)}
        SELECT forecast_factor AS business_factor
        FROM forecast_meta
        """,
        month,
        *([cutoff_date] if cutoff_date else []),
    )
    return (
        float(meta["business_factor"])
        if meta and meta["business_factor"] is not None
        else 1.0
    )
