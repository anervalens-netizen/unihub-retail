"""Per-store refresh lifecycle methods for the Grile repository."""
from __future__ import annotations

from typing import Any

import asyncpg

from repositories.grile_refresh_reservations import reserve_store_refresh_on_connection
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
)


class GrileStoreRefreshQueries:
    pool: asyncpg.Pool

    async def reserve_store_refresh(
        self,
        *,
        run_month: str,
        site_code: str,
        requested_by_sub: str,
    ) -> int | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await _reconcile_stale_store_refreshes_on_connection(
                    conn,
                    run_month=run_month,
                    site_code=site_code,
                    queued_lease_seconds=GRILE_STORE_REFRESH_QUEUED_LEASE_SECONDS,
                    running_lease_seconds=GRILE_STORE_REFRESH_RUNNING_LEASE_SECONDS,
                )
                return await reserve_store_refresh_on_connection(
                    conn,
                    run_month=run_month,
                    site_code=site_code,
                    requested_by_sub=requested_by_sub,
                )

    async def fail_queued_store_refresh(
        self,
        refresh_id: int,
        error_message: str,
        *,
        error_code: str = "queue_publish_failed",
    ) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE grile_store_refreshes
                SET status = 'failed', error_code = $2, error_message = $3,
                    projection_applied = false,
                    finished_at = now(), heartbeat_at = now()
                WHERE id = $1 AND status = 'queued'
                """,
                refresh_id,
                error_code,
                error_message[:500],
            )
        return result == "UPDATE 1"

    async def get_active_store_refresh(
        self,
        run_month: str,
        site_code: str,
    ) -> asyncpg.Record | None:
        await self.reconcile_store_refreshes(run_month=run_month, site_code=site_code)
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, run_month, site_code, generation, status,
                       requested_by_sub, projection_applied, error_code,
                       error_message, started_at, heartbeat_at, finished_at, created_at
                FROM grile_store_refreshes
                WHERE run_month = $1 AND site_code = $2
                  AND status IN ('queued', 'running')
                ORDER BY id DESC
                LIMIT 1
                """,
                run_month,
                site_code,
            )

    async def get_store_refresh(self, refresh_id: int) -> asyncpg.Record | None:
        await self.reconcile_store_refreshes(refresh_id=refresh_id)
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, run_month, site_code, generation, status,
                       requested_by_sub, projection_applied, error_code,
                       error_message, started_at, heartbeat_at, finished_at, created_at
                FROM grile_store_refreshes
                WHERE id = $1
                """,
                refresh_id,
            )

    async def reconcile_store_refreshes(
        self,
        *,
        refresh_id: int | None = None,
        run_month: str | None = None,
        site_code: str | None = None,
        queued_lease_seconds: int = GRILE_STORE_REFRESH_QUEUED_LEASE_SECONDS,
        running_lease_seconds: int = GRILE_STORE_REFRESH_RUNNING_LEASE_SECONDS,
    ) -> list[int]:
        if queued_lease_seconds <= 0 or running_lease_seconds <= 0:
            raise ValueError("Grile store refresh leases must be positive")
        async with self.pool.acquire() as conn:
            rows = await _reconcile_stale_store_refreshes_on_connection(
                conn,
                refresh_id=refresh_id,
                run_month=run_month,
                site_code=site_code,
                queued_lease_seconds=queued_lease_seconds,
                running_lease_seconds=running_lease_seconds,
            )
        return [int(row["id"]) for row in rows]

    async def claim_store_refresh(self, refresh_id: int) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                UPDATE grile_store_refreshes
                SET status = 'running', started_at = now(), heartbeat_at = now(),
                    projection_applied = NULL, error_code = NULL, error_message = NULL
                WHERE id = $1 AND status = 'queued'
                RETURNING id, run_month, site_code, generation, requested_by_sub,
                          created_at, started_at, heartbeat_at
                """,
                refresh_id,
            )

    async def heartbeat_store_refresh(self, refresh_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE grile_store_refreshes
                SET heartbeat_at = now()
                WHERE id = $1 AND status = 'running'
                """,
                refresh_id,
            )
        return result == "UPDATE 1"

    async def finish_store_refresh(
        self,
        refresh_id: int,
        *,
        status: str,
        projection_applied: bool | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("Invalid terminal Grile store refresh status")
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE grile_store_refreshes
                SET status = $2, projection_applied = $3, error_code = $4,
                    error_message = $5, finished_at = now(), heartbeat_at = now()
                WHERE id = $1 AND status = 'running'
                """,
                refresh_id,
                status,
                projection_applied,
                error_code,
                error_message[:500] if error_message is not None else None,
            )
        return result == "UPDATE 1"

    async def complete_store_refresh(
        self,
        refresh_id: int,
        row: dict[str, Any],
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Persist the observation and terminal operation state atomically."""
        if status not in {"completed", "failed"}:
            raise ValueError("Invalid terminal Grile store refresh status")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                refresh = await conn.fetchrow(
                    """
                    SELECT run_month, generation, requested_by_sub
                    FROM grile_store_refreshes
                    WHERE id = $1 AND status = 'running'
                    FOR UPDATE
                    """,
                    refresh_id,
                )
                if refresh is None:
                    raise RuntimeError("Store refresh is not an active fenced operation")
                projection_applied = await _record_observation(
                    conn,
                    run_month=refresh["run_month"],
                    row=row,
                    source="store",
                    source_run_id=None,
                    store_refresh_id=refresh_id,
                    generation=int(refresh["generation"]),
                    checked_by_sub=refresh["requested_by_sub"],
                )
                result = await conn.execute(
                    """
                    UPDATE grile_store_refreshes
                    SET status = $2, projection_applied = $3, error_code = $4,
                        error_message = $5, finished_at = now(), heartbeat_at = now()
                    WHERE id = $1 AND status = 'running'
                    """,
                    refresh_id,
                    status,
                    projection_applied,
                    error_code,
                    error_message[:500] if error_message is not None else None,
                )
                if result != "UPDATE 1":
                    raise RuntimeError(
                        "Store refresh lost its fence before terminal publication"
                    )
                return projection_applied

    async def record_store_refresh_observation(
        self,
        refresh_id: int,
        row: dict[str, Any],
    ) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                refresh = await conn.fetchrow(
                    """
                    SELECT run_month, generation, requested_by_sub
                    FROM grile_store_refreshes
                    WHERE id = $1 AND status = 'running'
                    FOR UPDATE
                    """,
                    refresh_id,
                )
                if refresh is None:
                    raise RuntimeError("Store refresh is not an active fenced operation")
                return await _record_observation(
                    conn,
                    run_month=refresh["run_month"],
                    row=row,
                    source="store",
                    source_run_id=None,
                    store_refresh_id=refresh_id,
                    generation=int(refresh["generation"]),
                    checked_by_sub=refresh["requested_by_sub"],
                )
