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
                SELECT
                    st.agent,
                    COALESCE(SUM(
                        CASE WHEN fp.item_code IS NOT NULL AND st.quantity > 0
                             THEN st.quantity ELSE 0 END
                    ), 0)::INT AS focus_units,
                    COALESCE(SUM(
                        CASE WHEN st.unit_price > $4 AND st.quantity > 0
                             THEN st.quantity ELSE 0 END
                    ), 0)::INT AS price_units
                FROM sales_transactions st
                JOIN stores s ON s.site_code = st.site_code
                LEFT JOIN focus_products fp ON fp.item_code = st.item_code
                WHERE {where_sql}
                GROUP BY st.agent
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
