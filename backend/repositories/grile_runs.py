"""Run reservation and observation methods for the Grile repository."""
from __future__ import annotations

from typing import Any

import asyncpg

from repositories.grile_refresh_reservations import allocate_generation as _allocate_generation
from repositories.grile_persistence import (
    GRILE_RUN_QUEUED_LEASE_SECONDS,
    GRILE_RUN_RUNNING_LEASE_SECONDS,
    GRILE_STORE_REFRESH_QUEUED_LEASE_SECONDS,
    GRILE_STORE_REFRESH_RUNNING_LEASE_SECONDS,
    _CURRENT_STATUS_COLUMNS,
    _RUN_COLUMNS,
    _STORE_STATUS_COLUMNS,
    _record_observation,
    _reconcile_stale_runs_on_connection,
    _reconcile_stale_store_refreshes_on_connection,
    _status_params,
)


class GrileRunQueries:
    pool: asyncpg.Pool

    async def get_active_sheets(self, month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT gs.site_code, gs.sheet_id, gs.registry_key, gs.template_version
                FROM grile_sheets gs
                JOIN stores s ON s.site_code = gs.site_code
                WHERE gs.is_active = true AND s.is_active = true
                  AND (gs.active_from_month IS NULL OR gs.active_from_month <= $1)
                ORDER BY gs.site_code
                """, month,
            )

    async def get_active_sheet(self, site_code: str, month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT gs.site_code, gs.sheet_id, gs.registry_key, gs.template_version
                FROM grile_sheets gs JOIN stores s ON s.site_code = gs.site_code
                WHERE gs.site_code = $1 AND gs.is_active = true AND s.is_active = true
                  AND (gs.active_from_month IS NULL OR gs.active_from_month <= $2)
                """, site_code, month,
            )

    async def count_active_sheets(self, month: str) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT count(*) FROM grile_sheets gs JOIN stores s ON s.site_code = gs.site_code
                WHERE gs.is_active = true AND s.is_active = true
                  AND (gs.active_from_month IS NULL OR gs.active_from_month <= $1)
                """, month,
            )

    async def get_sheet_map(self, month: str) -> dict[str, str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT gs.site_code, gs.sheet_id FROM grile_sheets gs
                JOIN stores s ON s.site_code = gs.site_code
                WHERE gs.is_active = true AND s.is_active = true
                  AND (gs.active_from_month IS NULL OR gs.active_from_month <= $1)
                """, month,
            )
            return {r["site_code"]: r["sheet_id"] for r in rows}

    async def get_latest_data_month(self) -> str | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT COALESCE((SELECT MAX(import_month) FROM reporting_item_month),
                                (SELECT MAX(import_month) FROM store_targets))
                """
            )

    async def get_expected_by_site(self, month: str) -> dict[str, dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT st.site_code, st.target_value AS db_target,
                       COALESCE(sales.sales_mtd, 0) AS db_sales_mtd,
                       sales_days.max_sale_date AS db_max_sale_date
                FROM store_targets st
                LEFT JOIN (
                    SELECT site_code, SUM(total_sales) AS sales_mtd
                    FROM reporting_item_month WHERE import_month = $1 GROUP BY site_code
                ) sales ON sales.site_code = st.site_code
                LEFT JOIN (
                    SELECT site_code, MAX(sale_date) AS max_sale_date
                    FROM reporting_item_day WHERE import_month = $1 GROUP BY site_code
                ) sales_days ON sales_days.site_code = st.site_code
                WHERE st.import_month = $1
                """, month,
            )
            return {r["site_code"]: {"db_target": r["db_target"], "db_sales_mtd": r["db_sales_mtd"], "db_max_sale_date": r["db_max_sale_date"]} for r in rows}

    async def get_hierarchy(self) -> dict[str, dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.site_code, s.locatie, s.firma, s.regional, s.asm,
                       tl.name AS team_leader_name
                FROM stores s LEFT JOIN team_leaders tl ON tl.id = s.team_leader_id
                """
            )
            return {r["site_code"]: {"locatie": r["locatie"], "firma": r["firma"], "regional": r["regional"], "asm": r["asm"], "team_leader_name": r["team_leader_name"]} for r in rows}

    async def reserve_run(self, *, run_month: str, source: str, source_snapshot_id: int | None, triggered_by_sub: str | None) -> int | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await _reconcile_stale_runs_on_connection(
                    conn,
                    run_month=run_month,
                    queued_lease_seconds=GRILE_RUN_QUEUED_LEASE_SECONDS,
                    running_lease_seconds=GRILE_RUN_RUNNING_LEASE_SECONDS,
                )
                return await conn.fetchval(
                    """
                    INSERT INTO grile_runs (run_month, source, source_snapshot_id, triggered_by_sub, status, heartbeat_at)
                    VALUES ($1, $2, $3, $4, 'queued', now())
                    ON CONFLICT (run_month) WHERE status IN ('queued', 'running') DO NOTHING
                    RETURNING id
                    """, run_month, source, source_snapshot_id, triggered_by_sub,
                )

    async def reserve_sales_import_run(
        self, *, run_month: str, source_snapshot_id: int
    ) -> int | None:
        """Reserve the post-import run through the narrow DB authority boundary."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT reserve_sales_import_grile_run($1, $2)",
                run_month,
                source_snapshot_id,
            )

    async def start_run(self, run_id: int, progress_total: int) -> bool:
        """Compatibility CAS for legacy reservation callers and tests."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE grile_runs SET status = 'running', progress_total = $2,
                    started_at = now(), heartbeat_at = now()
                WHERE id = $1 AND status = 'queued'
                """, run_id, progress_total,
            )
        return result == "UPDATE 1"

    async def claim_run(self, run_id: int, *, progress_total: int, site_codes: list[str]) -> dict[str, int] | None:
        """CAS queued->running and allocate every full-run store fence before Google I/O."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                run_month = await conn.fetchval(
                    """
                    UPDATE grile_runs SET status = 'running', progress_total = $2,
                        started_at = now(), heartbeat_at = now()
                    WHERE id = $1 AND status = 'queued'
                    RETURNING run_month
                    """, run_id, progress_total,
                )
                if not isinstance(run_month, str):
                    return None
                generations: dict[str, int] = {}
                for site_code in site_codes:
                    generation = await _allocate_generation(conn, run_month, site_code)
                    await conn.execute(
                        """INSERT INTO grile_run_store_generations (run_id, site_code, generation)
                           VALUES ($1, $2, $3)""", run_id, site_code, generation,
                    )
                    generations[site_code] = generation
                return generations

    async def heartbeat_run(self, run_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE grile_runs SET heartbeat_at = now()
                WHERE id = $1 AND status = 'running'
                """,
                run_id,
            )
        return result == "UPDATE 1"

    async def set_run_progress(self, run_id: int, current: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE grile_runs SET progress_current = $2, heartbeat_at = now()
                   WHERE id = $1 AND status = 'running'""", run_id, current,
            )
        return result == "UPDATE 1"

    async def finalize_run(self, run_id: int, *, status: str, ok_count: int, problem_count: int, error_count: int, duration_ms: int, error_message: str | None = None) -> bool:
        if status not in {"completed", "failed"}:
            raise ValueError("Grile run terminal status must be completed or failed")
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE grile_runs SET status = $2, ok_count = $3, problem_count = $4,
                    error_count = $5, duration_ms = $6, error_message = $7,
                    progress_current = CASE WHEN $2 = 'completed' THEN progress_total ELSE progress_current END,
                    finished_at = now(), heartbeat_at = now()
                WHERE id = $1 AND status IN ('queued', 'running')
                """, run_id, status, ok_count, problem_count, error_count, duration_ms, error_message,
            )
        return result == "UPDATE 1"

    async def fail_run(self, run_id: int, *, error_message: str, duration_ms: int | None = None) -> bool:
        """CAS any active run to failed without inventing progress or replacing observations."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE grile_runs AS operation
                SET status = 'failed', error_message = $2,
                    duration_ms = COALESCE($3, operation.duration_ms),
                    finished_at = now(), heartbeat_at = now()
                WHERE operation.id = $1 AND operation.status IN ('queued', 'running')
                """,
                run_id,
                error_message[:500],
                duration_ms,
            )
        return result == "UPDATE 1"

    async def reconcile_stale_runs(
        self,
        *,
        run_month: str | None = None,
        queued_lease_seconds: int = GRILE_RUN_QUEUED_LEASE_SECONDS,
        running_lease_seconds: int = GRILE_RUN_RUNNING_LEASE_SECONDS,
    ) -> list[int]:
        if queued_lease_seconds <= 0 or running_lease_seconds <= 0:
            raise ValueError("Grile run leases must be positive")
        async with self.pool.acquire() as conn:
            rows = await _reconcile_stale_runs_on_connection(
                conn,
                run_month=run_month,
                queued_lease_seconds=queued_lease_seconds,
                running_lease_seconds=running_lease_seconds,
            )
        return [int(row["id"]) for row in rows]

    async def record_full_observation(self, run_id: int, row: dict[str, Any], *, generation: int, checked_by_sub: str | None = None) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO grile_store_status
                        (run_id, site_code, completion_pct, last_edit, grila_target, grila_sales,
                         db_target, db_sales_mtd, db_max_sale_date, fill_status, target_status,
                         sales_status, tolerance, completion_algorithm_version, completion_as_of,
                         error_code, error_message, raw_summary)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                    ON CONFLICT (run_id, site_code) DO UPDATE SET
                        completion_pct = EXCLUDED.completion_pct, last_edit = EXCLUDED.last_edit,
                        grila_target = EXCLUDED.grila_target, grila_sales = EXCLUDED.grila_sales,
                        db_target = EXCLUDED.db_target, db_sales_mtd = EXCLUDED.db_sales_mtd,
                        db_max_sale_date = EXCLUDED.db_max_sale_date, fill_status = EXCLUDED.fill_status,
                        target_status = EXCLUDED.target_status, sales_status = EXCLUDED.sales_status,
                        tolerance = EXCLUDED.tolerance,
                        completion_algorithm_version = EXCLUDED.completion_algorithm_version,
                        completion_as_of = EXCLUDED.completion_as_of,
                        error_code = EXCLUDED.error_code,
                        error_message = EXCLUDED.error_message, raw_summary = EXCLUDED.raw_summary
                    """, run_id, *_status_params(row),
                )
                run_month = await conn.fetchval("SELECT run_month FROM grile_runs WHERE id = $1", run_id)
                if not isinstance(run_month, str):
                    raise RuntimeError("Grile run disappeared before observation persistence")
                return await _record_observation(conn, run_month=run_month, row=row, source="full", source_run_id=run_id, store_refresh_id=None, generation=generation, checked_by_sub=checked_by_sub)
