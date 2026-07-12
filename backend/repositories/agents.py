from __future__ import annotations

from typing import Any
import asyncpg

from repositories.agent_evaluation import (
    AGENT_EVALUATION_OPTIONS_QUERY,
    AGENT_EVALUATION_V2_QUERY,
)


class AgentsRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_overview_stats(self, query: str, params: list[Any], prev_month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *params, prev_month)

    async def get_churn_count(self, query: str, params: list[Any]) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
            return row["churned_total_count"] if row else 0

    async def get_movement(self, query: str, params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *params)

    async def get_agents_list(self, query: str, params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *params)
            
    async def get_agent_profile(self, query: str, agent: str, selected_month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, agent, selected_month)

    async def get_agent_history(self, agent: str) -> list[asyncpg.Record]:
        query = """
            SELECT
                import_month as month,
                total_sales,
                total_quantity,
                receipt_count,
                active_store_count,
                is_active
            FROM reporting_agent_lifecycle_month
            WHERE agent = $1
            ORDER BY import_month ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, agent)

    async def get_stores_coverage(self, query: str, params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *params)

    async def get_agent_evaluation(self, query: str, params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *params)

    async def get_agent_evaluation_v2(
        self,
        month_filter: str | None,
        firma: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                AGENT_EVALUATION_V2_QUERY,
                month_filter,
                firma,
                asm,
                site_code,
            )

    async def get_agent_evaluation_options(
        self,
        firma: str | None,
        asm: str | None,
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(AGENT_EVALUATION_OPTIONS_QUERY, firma, asm)
