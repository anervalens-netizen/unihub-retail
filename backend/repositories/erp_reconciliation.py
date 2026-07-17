from __future__ import annotations

from datetime import date
from typing import Any

import asyncpg


class ErpReconciliationRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_reference(self, import_month: str, cutoff_date: date) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            snapshot = await conn.fetchrow(
                """
                SELECT id, import_month, filename, created_at
                FROM import_snapshots
                WHERE import_month = $1 AND status = 'completed'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                import_month,
            )
            stores = await conn.fetch(
                """
                SELECT
                    rad.site_code,
                    MAX(s.locatie) AS locatie,
                    COALESCE(SUM(rad.total_sales), 0) AS total_sales,
                    COALESCE(SUM(rad.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(rad.focus_quantity), 0)::INT AS focus_quantity,
                    COALESCE(SUM(rad.receipt_count), 0)::INT AS receipt_count,
                    COALESCE(SUM(rad.receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                    COALESCE(st.target_value, 0) AS target_value,
                    COUNT(DISTINCT rad.agent)::INT AS agent_count
                FROM reporting_agent_day rad
                JOIN stores s ON s.site_code = rad.site_code
                LEFT JOIN store_targets st
                  ON st.import_month = rad.import_month
                 AND st.site_code = rad.site_code
                WHERE rad.import_month = $1
                  AND rad.sale_date <= $2
                  AND s.is_active = TRUE
                  AND s.locatie NOT ILIKE 'TR %'
                GROUP BY rad.site_code, st.target_value
                ORDER BY rad.site_code
                """,
                import_month,
                cutoff_date,
            )
            agents = await conn.fetch(
                """
                SELECT
                    rad.site_code,
                    rad.agent,
                    MAX(s.locatie) AS locatie,
                    COALESCE(SUM(rad.total_sales), 0) AS total_sales,
                    COALESCE(SUM(rad.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(rad.focus_quantity), 0)::INT AS focus_quantity,
                    COALESCE(SUM(rad.receipt_count), 0)::INT AS receipt_count,
                    COALESCE(SUM(rad.receipt_2plus_count), 0)::INT AS receipt_2plus_count
                FROM reporting_agent_day rad
                JOIN stores s ON s.site_code = rad.site_code
                WHERE rad.import_month = $1
                  AND rad.sale_date <= $2
                  AND s.is_active = TRUE
                  AND s.locatie NOT ILIKE 'TR %'
                GROUP BY rad.site_code, rad.agent
                ORDER BY rad.site_code, rad.agent
                """,
                import_month,
                cutoff_date,
            )
            receipt_rows = await conn.fetch(
                """
                WITH receipts AS (
                    SELECT
                        st.site_code,
                        st.agent,
                        st.sale_date,
                        st.bon_nr,
                        COALESCE(SUM(st.quantity), 0)::INT AS net_quantity
                    FROM sales_transactions st
                    JOIN stores s ON s.site_code = st.site_code
                    WHERE st.import_month = $1
                      AND st.sale_date <= $2
                      AND NOT st.is_cartela
                      AND s.is_active = TRUE
                      AND s.locatie NOT ILIKE 'TR %'
                    GROUP BY st.site_code, st.agent, st.sale_date, st.bon_nr
                )
                SELECT
                    site_code,
                    agent,
                    COUNT(*)::INT AS all_receipts,
                    COUNT(*) FILTER (WHERE net_quantity > 0)::INT AS positive_receipts,
                    COUNT(*) FILTER (WHERE net_quantity <= 0)::INT AS return_only_receipts
                FROM receipts
                GROUP BY site_code, agent
                ORDER BY site_code, agent
                """,
                import_month,
                cutoff_date,
            )
            focus_rows = await conn.fetch(
                """
                SELECT
                    COALESCE(
                        NULLIF(TRIM(st.subcategory), ''),
                        NULLIF(TRIM(st.category), ''),
                        'Necategorizat'
                    ) AS focus_subcategory,
                    COALESCE(SUM(st.quantity), 0)::INT AS quantity
                FROM sales_transactions st
                JOIN focus_products fp ON fp.item_code = st.item_code
                JOIN stores s ON s.site_code = st.site_code
                WHERE st.import_month = $1
                  AND st.sale_date <= $2
                  AND NOT st.is_cartela
                  AND s.is_active = TRUE
                  AND s.locatie NOT ILIKE 'TR %'
                GROUP BY COALESCE(
                    NULLIF(TRIM(st.subcategory), ''),
                    NULLIF(TRIM(st.category), ''),
                    'Necategorizat'
                )
                """,
                import_month,
                cutoff_date,
            )
            category_rows = await conn.fetch(
                """
                SELECT
                    st.category,
                    st.subcategory,
                    COALESCE(SUM(st.quantity), 0)::INT AS quantity
                FROM sales_transactions st
                JOIN stores s ON s.site_code = st.site_code
                WHERE st.import_month = $1
                  AND st.sale_date <= $2
                  AND NOT st.is_cartela
                  AND s.is_active = TRUE
                  AND s.locatie NOT ILIKE 'TR %'
                GROUP BY st.category, st.subcategory
                """,
                import_month,
                cutoff_date,
            )
            retail_cutoff_date = await conn.fetchval(
                """
                SELECT MAX(rad.sale_date)
                FROM reporting_agent_day rad
                JOIN stores s ON s.site_code = rad.site_code
                WHERE rad.import_month = $1
                  AND s.is_active = TRUE
                  AND s.locatie NOT ILIKE 'TR %'
                """,
                import_month,
            )
        return {
            "snapshot": snapshot,
            "stores": stores,
            "agents": agents,
            "receipt_rows": receipt_rows,
            "focus_rows": focus_rows,
            "category_rows": category_rows,
            "retail_cutoff_date": retail_cutoff_date,
        }
