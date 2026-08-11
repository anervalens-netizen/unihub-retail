"""Small Dashboard cutoff queries shared by period-comparison projections."""

from __future__ import annotations

from typing import Any


async def fetch_period_comparison_cutoff_day(conn: Any, month: str) -> int:
    row = await conn.fetchrow(
        """
        WITH month_meta AS (
            SELECT BOOL_OR(is_month_final) AS is_final
            FROM import_snapshots
            WHERE import_month = $1
              AND status = 'completed'
        ),
        last_sale AS (
            SELECT EXTRACT(DAY FROM MAX(sale_date))::INT AS last_sale_day
            FROM reporting_agent_day
            WHERE import_month = $1
        )
        SELECT
            COALESCE(mm.is_final, true) AS is_final,
            ls.last_sale_day,
            EXTRACT(DAY FROM (
                date_trunc('month', to_date($1 || '-01', 'YYYY-MM-DD'))
                + INTERVAL '1 month - 1 day'
            ))::INT AS days_in_month
        FROM last_sale ls
        LEFT JOIN month_meta mm ON true
        """,
        month,
    )
    if not row:
        return 31
    days_in_month = int(row["days_in_month"] or 31)
    if row["is_final"]:
        return days_in_month
    last_sale_day = row["last_sale_day"]
    return max(1, min(int(last_sale_day), days_in_month)) if last_sale_day else days_in_month


async def resolve_period_comparison_cutoff_day(
    conn: Any,
    month: str,
    cutoff_day: int | None,
) -> int:
    if cutoff_day is not None:
        return cutoff_day
    return await fetch_period_comparison_cutoff_day(conn, month)
