"""Read-only registry persistence for monthly Grile operations."""

from __future__ import annotations

from typing import Any

import asyncpg


async def fetch_active_registry(
    pool: asyncpg.Pool,
    *,
    month: str | None,
) -> list[dict[str, Any]]:
    """Return the active sheet/store cohort for a monthly operation."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                gs.site_code,
                gs.sheet_id,
                gs.registry_key,
                s.locatie,
                s.firma,
                s.asm,
                gs.template_version
            FROM grile_sheets gs
            JOIN stores s ON s.site_code = gs.site_code
            WHERE gs.is_active = true
              AND s.is_active = true
              AND ($1::TEXT IS NULL OR gs.active_from_month IS NULL OR gs.active_from_month <= $1)
            ORDER BY COALESCE(gs.registry_key, s.firma || '/' || s.locatie)
            """,
            month,
        )
    return [dict(row) for row in rows]
