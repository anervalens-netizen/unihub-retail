from __future__ import annotations

import asyncpg


class ImportsRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_import_history(self) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, import_month, filename, upload_date, is_month_final, rows_in_file,
                       rows_imported, status, error_message, coverage_report, created_at,
                       finished_at,
                       CASE
                           WHEN finished_at IS NULL THEN NULL
                           ELSE ROUND(EXTRACT(EPOCH FROM (finished_at - created_at))::numeric, 3)
                       END AS duration_seconds
                FROM import_snapshots
                ORDER BY created_at DESC
                """
            )
