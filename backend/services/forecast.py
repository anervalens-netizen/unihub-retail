"""Forecast helpers shared între CRM și HR.

Extras din routers/crm.py ca să rup importul cross-router hr.py → crm.py.
Routere-le nu mai depind unul de altul; ambele depind de services/.

Motivație: importul circular implicit (hr.py importa get_forecast_factor
din routers/crm.py) face greu de testat fiecare router izolat și crează
cuplaj artificial — orice modificare în crm.py necesită verificare în hr.py.
"""
from __future__ import annotations

from typing import Any


async def get_forecast_factor(conn: Any, month: str) -> float:
    """Returnează factorul ponderat de calendarul business al forecastului.

    Pentru o lună parțială folosim distribuția zilnică din ultima rulare AI
    finalizată, nu raportul implicit zile calendaristice/zi curentă. Dacă
    modelul business lipsește sau nu are greutate până la cutoff, nu inventăm
    extrapolare: factorul rămâne 1.0.
    """
    meta = await conn.fetchrow(
        """
        WITH month_meta AS (
            SELECT
                COALESCE(BOOL_OR(snap.is_month_final), true) AS is_final,
                MAX(rid.sale_date) AS last_sale_date
            FROM import_snapshots snap
            LEFT JOIN (
                SELECT MAX(sale_date) AS sale_date
                FROM reporting_item_day
                WHERE import_month = $1
            ) rid ON true
            WHERE snap.import_month = $1
        ),
        latest_business_run AS (
            SELECT run.id
            FROM ai_forecast_runs run
            WHERE run.status = 'completed'
              AND run.metric = 'sales_value'
              AND run.horizon = 'current_month'
              AND run.forecast_month = $1
            ORDER BY run.generated_at DESC, run.id DESC
            LIMIT 1
        ),
        business_weights AS (
            SELECT
                SUM(GREATEST(day.forecast_sales, 0)) AS total_weight,
                SUM(GREATEST(day.forecast_sales, 0)) FILTER (
                    WHERE day.forecast_date <= month_meta.last_sale_date
                ) AS elapsed_weight
            FROM ai_forecast_store_day day
            JOIN latest_business_run run ON run.id = day.run_id
            CROSS JOIN month_meta
        )
        SELECT
            month_meta.is_final,
            month_meta.last_sale_date,
            CASE
                WHEN business_weights.total_weight > 0
                 AND business_weights.elapsed_weight > 0
                THEN business_weights.total_weight / business_weights.elapsed_weight
                ELSE NULL
            END AS business_factor
        FROM month_meta
        CROSS JOIN business_weights
        """,
        month,
    )
    if meta and not meta["is_final"] and meta["last_sale_date"] and meta["business_factor"]:
        return max(1.0, float(meta["business_factor"]))
    return 1.0
