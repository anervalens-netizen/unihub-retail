from __future__ import annotations

from typing import Any
import asyncpg


class CampaignsRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_overview(self, focus_where_sql: str, totals_where_sql: str, focus_params: list[Any]) -> dict:
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
                    WHERE {focus_where_sql}
                ),
                overall_totals AS (
                    SELECT
                        COALESCE(SUM(tot.total_quantity), 0)::INT AS total_quantity
                    FROM reporting_agent_month tot
                    WHERE {totals_where_sql}
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
                *focus_params,
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
                WHERE {focus_where_sql}
                GROUP BY agg.item_code
                ORDER BY sales_total DESC, qty_total DESC, agg.item_code ASC
                LIMIT 8
                """,
                *focus_params,
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
                WHERE {focus_where_sql}
                GROUP BY agg.site_code
                ORDER BY sales_total DESC, qty_total DESC, locatie ASC
                LIMIT 8
                """,
                *focus_params,
            )
        return {
            "overview": overview_row,
            "products": product_rows,
            "stores": store_rows,
        }

    async def fetch_history(self, focus_clauses: list[str], totals_clauses: list[str], params: list[Any]) -> list[asyncpg.Record]:
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

    async def fetch_promo_total(self, promo_clauses: list[str], promo_params: list[Any]) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                SELECT COALESCE(SUM(agg.net_quantity), 0) AS total_qty
                FROM reporting_item_day agg
                WHERE {" AND ".join(promo_clauses)}
                """,
                *promo_params,
            )

    async def fetch_promo_store_rows(self, promo_clauses: list[str], promo_params: list[Any]) -> list[asyncpg.Record]:
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
                WHERE {" AND ".join(promo_clauses)}
                GROUP BY agg.site_code
                ORDER BY qty DESC
                """,
                *promo_params,
            )

    async def fetch_incentive_store_rows(self, inc_store_clauses: list[str], inc_store_params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT agg.site_code, MAX(agg.locatie) AS locatie,
                       MAX(agg.firma) AS firma,
                       agg.item_code,
                       COALESCE(SUM(agg.net_quantity), 0)::INT AS qty
                FROM reporting_item_month agg
                WHERE {" AND ".join(inc_store_clauses)}
                GROUP BY agg.site_code, agg.item_code
                """,
                *inc_store_params,
            )
