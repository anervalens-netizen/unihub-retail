from __future__ import annotations

import json
from typing import Any

import asyncpg


MAX_SAVED_VIEWS_PER_OWNER = 50


class SavedViewsRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @staticmethod
    def _select_columns() -> str:
        return """
            id,
            module_id,
            name,
            state::text AS state_json,
            schema_version,
            created_at::text,
            updated_at::text
        """

    async def list_views(self, owner_subject: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT {self._select_columns()}
                FROM saved_views
                WHERE owner_subject = $1
                ORDER BY updated_at DESC, lower(name) ASC, id ASC
                """,
                owner_subject,
            )

    async def create_view(
        self,
        owner_subject: str,
        *,
        module_id: str,
        name: str,
        state: dict[str, Any],
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    owner_subject,
                )
                count = int(
                    await conn.fetchval(
                        "SELECT COUNT(*) FROM saved_views WHERE owner_subject = $1",
                        owner_subject,
                    )
                    or 0
                )
                if count >= MAX_SAVED_VIEWS_PER_OWNER:
                    return None
                return await conn.fetchrow(
                    f"""
                    INSERT INTO saved_views (owner_subject, module_id, name, state, schema_version)
                    VALUES ($1, $2, $3, $4::jsonb, 1)
                    RETURNING {self._select_columns()}
                    """,
                    owner_subject,
                    module_id,
                    name,
                    json.dumps(state, ensure_ascii=True, separators=(",", ":")),
                )

    async def update_view(
        self,
        owner_subject: str,
        view_id: int,
        *,
        name: str | None,
        module_id: str | None,
        state: dict[str, Any] | None,
    ) -> asyncpg.Record | None:
        state_json = (
            json.dumps(state, ensure_ascii=True, separators=(",", ":"))
            if state is not None
            else None
        )
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                UPDATE saved_views
                SET name = COALESCE($3, name),
                    module_id = COALESCE($4, module_id),
                    state = COALESCE($5::jsonb, state),
                    updated_at = now()
                WHERE id = $1 AND owner_subject = $2
                RETURNING {self._select_columns()}
                """,
                view_id,
                owner_subject,
                name,
                module_id,
                state_json,
            )

    async def delete_view(self, owner_subject: str, view_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM saved_views WHERE id = $1 AND owner_subject = $2",
                view_id,
                owner_subject,
            )
        return result == "DELETE 1"
