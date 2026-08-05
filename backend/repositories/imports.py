from __future__ import annotations

from datetime import date

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

    async def get_validated_sales_generation(
        self,
        *,
        source_sha256: str,
        cutoff_date: date,
    ) -> asyncpg.Record | None:
        """Recover the exact staged generation after ephemeral job-result loss."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, import_month, filename, is_month_final, rows_in_file,
                       rows_imported, coverage_report, generation_token,
                       manifest_sha256, manifest, source_spool_path
                FROM import_snapshots
                WHERE status = 'processing'
                  AND source_sha256 = $1
                  AND cutoff_date = $2
                  AND manifest->>'generation_state' = 'validated'
                  AND generation_token IS NOT NULL
                  AND manifest_sha256 IS NOT NULL
                  AND source_spool_path IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                source_sha256,
                cutoff_date,
            )
