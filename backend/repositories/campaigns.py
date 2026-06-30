from __future__ import annotations

from datetime import date
from typing import Any

import asyncpg

from services.filters import build_scoped_params, scoped_clauses


def build_campaign_clauses(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    *,
    alias: str,
) -> tuple[list[str], list[Any]]:
    params, positions = build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses = scoped_clauses(
        positions,
        site_alias=alias,
        store_alias=alias,
        agent_alias=alias,
        month_alias=f"{alias}.import_month",
        month_position=1,
    )
    return clauses, params


def build_campaign_history_clauses(
    month: str,
    months_back: int,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[list[str], list[str], list[Any]]:
    params, positions = build_scoped_params(
        [month, months_back],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    focus_clauses = ["agg.import_month IN (SELECT import_month FROM recent_months)"]
    totals_clauses = ["tot.import_month IN (SELECT import_month FROM recent_months)"]
    for key, focus_column, totals_column in [
        ("firma", "agg.firma", "tot.firma"),
        ("regional", "agg.regional", "tot.regional"),
        ("asm", "agg.asm", "tot.asm"),
        ("site_code", "agg.site_code", "tot.site_code"),
        ("agent", "agg.agent", "tot.agent"),
    ]:
        if key in positions:
            focus_clauses.append(f"{focus_column} = ANY(string_to_array(${positions[key]}::TEXT, ','))")
            totals_clauses.append(f"{totals_column} = ANY(string_to_array(${positions[key]}::TEXT, ','))")
    return focus_clauses, totals_clauses, params


def _promo_scope(
    start: date,
    end: date,
    item_codes: list[str],
    month: str,
    *,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[list[str], list[Any]]:
    params, positions = build_scoped_params(
        [start, end, item_codes, month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses = [
        "agg.import_month = $4",
        "agg.sale_date BETWEEN $1 AND $2",
        "agg.item_code = ANY($3::TEXT[])",
    ]
    clauses.extend(
        scoped_clauses(
            positions,
            site_alias="agg",
            store_alias="agg",
            agent_alias="agg",
        )
    )
    return clauses, params


def _incentive_scope(
    item_codes: list[str],
    month: str,
    *,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[list[str], list[Any]]:
    params, positions = build_scoped_params(
        [item_codes, month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses = [
        "agg.item_code = ANY($1::TEXT[])",
        "agg.import_month = $2",
    ]
    clauses.extend(
        scoped_clauses(
            positions,
            site_alias="agg",
            store_alias="agg",
            agent_alias="agg",
        )
    )
    return clauses, params


class CampaignsRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_overview(
        self,
        month: str,
        *,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> dict:
        focus_clauses, params = build_campaign_clauses(
            month,
            firma,
            regional,
            asm,
            site_code,
            agent,
            alias="agg",
        )
        totals_clauses, _ = build_campaign_clauses(
            month,
            firma,
            regional,
            asm,
            site_code,
            agent,
            alias="tot",
        )
        async with self.pool.acquire() as conn:
            overview_row = await conn.fetchrow(
                f"""
                WITH focus_totals AS (
                    SELECT
                        COALESCE(SUM(agg.total_sales), 0) AS total_focus_sales,
                        COALESCE(SUM(agg.total_quantity), 0)::INT AS total_focus_qty,
                        COUNT(DISTINCT agg.item_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_focus_products,
                        COUNT(DISTINCT agg.site_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_focus_stores
                    FROM reporting_focus_item_month agg
                    WHERE {" AND ".join(focus_clauses)}
                ),
                overall_totals AS (
                    SELECT
                        COALESCE(SUM(tot.total_quantity), 0)::INT AS total_quantity
                    FROM reporting_agent_month tot
                    WHERE {" AND ".join(totals_clauses)}
                )
                SELECT
                    $1::TEXT AS month,
                    ft.total_focus_sales,
                    ft.total_focus_qty,
                    ROUND(ft.total_focus_qty * 100.0 / NULLIF(ot.total_quantity, 0), 2) AS focus_share_pct,
                    ft.active_focus_products,
                    ft.active_focus_stores
                FROM focus_totals ft
                CROSS JOIN overall_totals ot
                """,
                *params,
            )
            product_rows = await conn.fetch(
                f"""
                SELECT
                    agg.item_code,
                    MAX(agg.item_name) AS item_name,
                    COALESCE(SUM(agg.total_quantity), 0)::INT AS qty_total,
                    COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                    COUNT(DISTINCT agg.site_code)::INT AS store_count
                FROM reporting_focus_item_month agg
                WHERE {" AND ".join(focus_clauses)}
                GROUP BY agg.item_code
                ORDER BY sales_total DESC, qty_total DESC, agg.item_code ASC
                LIMIT 8
                """,
                *params,
            )
            store_rows = await conn.fetch(
                f"""
                SELECT
                    agg.site_code,
                    MAX(agg.locatie) AS locatie,
                    COALESCE(SUM(agg.total_quantity), 0)::INT AS qty_total,
                    COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                    COUNT(DISTINCT agg.item_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_products
                FROM reporting_focus_item_month agg
                WHERE {" AND ".join(focus_clauses)}
                GROUP BY agg.site_code
                ORDER BY sales_total DESC, qty_total DESC, locatie ASC
                LIMIT 8
                """,
                *params,
            )
        return {
            "overview": overview_row,
            "products": product_rows,
            "stores": store_rows,
        }

    async def fetch_history(
        self,
        month: str,
        months_back: int,
        *,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> list[asyncpg.Record]:
        focus_clauses, totals_clauses, params = build_campaign_history_clauses(
            month,
            months_back,
            firma,
            regional,
            asm,
            site_code,
            agent,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH recent_months AS (
                    SELECT import_month
                    FROM (
                        SELECT DISTINCT import_month
                        FROM import_snapshots
                        WHERE import_month <= $1
                          AND status = 'completed'
                        ORDER BY import_month DESC
                        LIMIT $2
                    ) months
                ),
                focus_summary AS (
                    SELECT
                        agg.import_month AS month,
                        COALESCE(SUM(agg.total_sales), 0) AS total_focus_sales,
                        COALESCE(SUM(agg.total_quantity), 0)::INT AS total_focus_qty,
                        COUNT(DISTINCT agg.item_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_focus_products,
                        COUNT(DISTINCT agg.site_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_focus_stores
                    FROM reporting_focus_item_month agg
                    WHERE {" AND ".join(focus_clauses)}
                    GROUP BY agg.import_month
                ),
                total_summary AS (
                    SELECT
                        tot.import_month AS month,
                        COALESCE(SUM(tot.total_quantity), 0)::INT AS total_quantity
                    FROM reporting_agent_month tot
                    WHERE {" AND ".join(totals_clauses)}
                    GROUP BY tot.import_month
                )
                SELECT
                    fs.month,
                    fs.total_focus_sales,
                    fs.total_focus_qty,
                    ROUND(
                        fs.total_focus_qty * 100.0
                        / NULLIF(ts.total_quantity, 0),
                        2
                    ) AS focus_share_pct,
                    fs.active_focus_products,
                    fs.active_focus_stores
                FROM focus_summary fs
                LEFT JOIN total_summary ts ON ts.month = fs.month
                ORDER BY fs.month ASC
                """,
                *params,
            )

    async def fetch_promo_total(
        self,
        start: date,
        end: date,
        item_codes: list[str],
        month: str,
        *,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> asyncpg.Record | None:
        clauses, params = _promo_scope(
            start,
            end,
            item_codes,
            month,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                SELECT COALESCE(SUM(agg.net_quantity), 0) AS total_qty
                FROM reporting_item_day agg
                WHERE {" AND ".join(clauses)}
                """,
                *params,
            )

    async def fetch_promo_store_rows(
        self,
        start: date,
        end: date,
        item_codes: list[str],
        month: str,
        *,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> list[asyncpg.Record]:
        clauses, params = _promo_scope(
            start,
            end,
            item_codes,
            month,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    agg.site_code,
                    MAX(agg.locatie) AS locatie,
                    MAX(agg.firma) AS firma,
                    COALESCE(SUM(agg.positive_quantity), 0)::INT AS qty,
                    COALESCE(SUM(agg.net_quantity), 0)::INT AS total_qty
                FROM reporting_item_day agg
                WHERE {" AND ".join(clauses)}
                GROUP BY agg.site_code
                ORDER BY qty DESC
                """,
                *params,
            )

    async def fetch_incentive_store_rows(
        self,
        item_codes: list[str],
        month: str,
        *,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> list[asyncpg.Record]:
        clauses, params = _incentive_scope(
            item_codes,
            month,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=None,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT agg.site_code, MAX(agg.locatie) AS locatie,
                       MAX(agg.firma) AS firma,
                       agg.item_code,
                       COALESCE(SUM(agg.net_quantity), 0)::INT AS qty
                FROM reporting_item_month agg
                WHERE {" AND ".join(clauses)}
                GROUP BY agg.site_code, agg.item_code
                """,
                *params,
            )

    async def fetch_incentive_agent_rows(
        self,
        item_codes: list[str],
        month: str,
        *,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> list[asyncpg.Record]:
        clauses, params = _incentive_scope(
            item_codes,
            month,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT agg.agent, agg.site_code,
                       MAX(agg.locatie) AS locatie,
                       MAX(agg.firma) AS firma,
                       agg.item_code,
                       COALESCE(SUM(agg.net_quantity), 0)::INT AS qty
                FROM reporting_item_month agg
                WHERE {" AND ".join(clauses)}
                  AND agg.agent IS NOT NULL AND agg.agent != '-'
                GROUP BY agg.agent, agg.site_code, agg.item_code
                """,
                *params,
            )
