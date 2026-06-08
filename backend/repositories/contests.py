from __future__ import annotations

from typing import Any

import asyncpg


class ContestsRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_agent_scores(
        self, where_sql: str, params: list[Any]
    ) -> list[asyncpg.Record]:
        """Puncte per agent: unitati focus + unitati peste prag de pret.

        Params asteptati: $1=month, $2=start, $3=end, $4=price_threshold,
        apoi clauzele de scope. Doar vanzari pozitive, non-cartela, non-return.
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH per_store AS (
                    SELECT
                        st.agent,
                        st.site_code,
                        s.locatie AS store_name,
                        s.firma,
                        COALESCE(SUM(
                            CASE WHEN fp.item_code IS NOT NULL AND st.quantity > 0
                                 THEN st.quantity ELSE 0 END
                        ), 0)::INT AS focus_units,
                        COALESCE(SUM(
                            CASE WHEN st.unit_price > $4 AND st.quantity > 0
                                 THEN st.quantity ELSE 0 END
                        ), 0)::INT AS price_units,
                        COALESCE(SUM(st.total_value), 0) AS sales_value
                    FROM sales_transactions st
                    JOIN stores s ON s.site_code = st.site_code
                    LEFT JOIN focus_products fp ON fp.item_code = st.item_code
                    WHERE {where_sql}
                    GROUP BY st.agent, st.site_code, s.locatie, s.firma
                )
                SELECT
                    agent,
                    (ARRAY_AGG(site_code ORDER BY (focus_units + price_units) DESC, sales_value DESC, store_name))[1] AS site_code,
                    (ARRAY_AGG(store_name ORDER BY (focus_units + price_units) DESC, sales_value DESC, store_name))[1] AS store_name,
                    (ARRAY_AGG(firma ORDER BY (focus_units + price_units) DESC, sales_value DESC, store_name))[1] AS firma,
                    COALESCE(SUM(focus_units), 0)::INT AS focus_units,
                    COALESCE(SUM(price_units), 0)::INT AS price_units
                FROM per_store
                GROUP BY agent
                """,
                *params,
            )

    async def fetch_scope_store_count(
        self, where_sql: str, params: list[Any]
    ) -> int:
        """Numarul de magazine din scope (pe tabela stores, non-TR)."""
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                f"SELECT COUNT(*)::INT FROM stores s WHERE {where_sql}",
                *params,
            )
            return int(value or 0)
