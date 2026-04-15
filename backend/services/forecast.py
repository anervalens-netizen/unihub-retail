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
    """Factor de extrapolare: zile_luna / ultima_zi_vanzari.

    Returnează 1.0 dacă luna e finalizată (nu mai extrapolăm).
    Folosit pentru a proiecta vânzările parțiale ale lunii curente la
    valoarea estimată finală — util pentru scoruri CRM și performanța ASM.
    """
    meta = await conn.fetchrow(
        """
        SELECT
            COALESCE(BOOL_OR(snap.is_month_final), true) AS is_final,
            EXTRACT(DAY FROM MAX(rid.sale_date))::INT AS last_sale_day,
            EXTRACT(DAY FROM (
                date_trunc('month', to_date($1 || '-01', 'YYYY-MM-DD'))
                + INTERVAL '1 month - 1 day'
            ))::INT AS days_in_month
        FROM import_snapshots snap
        LEFT JOIN (
            SELECT MAX(sale_date) AS sale_date
            FROM reporting_item_day
            WHERE import_month = $1
        ) rid ON true
        WHERE snap.import_month = $1
        """,
        month,
    )
    if meta and not meta["is_final"] and meta["last_sale_day"]:
        last_day = int(meta["last_sale_day"])
        days_in_month = int(meta["days_in_month"] or last_day)
        return days_in_month / last_day if last_day > 0 else 1.0
    return 1.0
