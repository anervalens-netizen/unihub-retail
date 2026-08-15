"""Shared SQL constants and projection transitions for Grile persistence."""
from __future__ import annotations

import json
from typing import Any

import asyncpg


GRILE_RUN_QUEUED_LEASE_SECONDS = 2 * 60 * 60
GRILE_RUN_RUNNING_LEASE_SECONDS = 5 * 60
GRILE_RUN_LEASE_EXPIRED = "grile_run_lease_expired"
GRILE_STORE_REFRESH_QUEUED_LEASE_SECONDS = 2 * 60 * 60
GRILE_STORE_REFRESH_RUNNING_LEASE_SECONDS = 5 * 60
GRILE_STORE_REFRESH_LEASE_EXPIRED = "grile_store_refresh_lease_expired"


_RUN_COLUMNS = """
    id, run_month, source_snapshot_id, status, source, progress_current,
    progress_total, ok_count, problem_count, error_count, duration_ms,
    triggered_by_sub, error_message, started_at, heartbeat_at, finished_at,
    created_at
"""

_STORE_STATUS_COLUMNS = """
    run_id, site_code, completion_pct, last_edit, grila_target, grila_sales,
    db_target, db_sales_mtd, db_max_sale_date, fill_status, target_status,
    sales_status, tolerance, completion_algorithm_version, completion_as_of,
    error_code, error_message, raw_summary
"""

_CURRENT_STATUS_COLUMNS = """
    run_month, site_code, source_run_id, source, completion_pct, last_edit,
    grila_target, grila_sales, db_target, db_sales_mtd, db_max_sale_date,
    fill_status, target_status, sales_status, tolerance,
    completion_algorithm_version, completion_as_of, error_code,
    error_message, raw_summary, content_sha256, checked_by_sub, checked_at,
    generation, current_observation_id, last_success_observation_id,
    last_success_checked_at, last_error_observation_id, last_error_generation,
    last_error_checked_at, last_error_code, last_error_message
"""

def _status_params(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["site_code"], row.get("completion_pct"), row.get("last_edit"),
        row.get("grila_target"), row.get("grila_sales"), row.get("db_target"),
        row.get("db_sales_mtd"), row.get("db_max_sale_date"), row.get("fill_status"),
        row.get("target_status"), row.get("sales_status"), row.get("tolerance"),
        row.get("completion_algorithm_version", 1), row.get("completion_as_of"),
        row.get("error_code"), row.get("error_message"),
        json.dumps(row.get("raw_summary")) if row.get("raw_summary") is not None else None,
    )

async def _reconcile_stale_runs_on_connection(
    conn: asyncpg.Connection,
    *,
    run_month: str | None,
    queued_lease_seconds: int,
    running_lease_seconds: int,
) -> list[asyncpg.Record]:
    """Terminalize abandoned reservations through a fenced, append-only-safe CAS."""
    return await conn.fetch(
        """
        WITH candidates AS (
            SELECT candidate.id
            FROM grile_runs AS candidate
            WHERE candidate.status IN ('queued', 'running')
              AND ($1::text IS NULL OR candidate.run_month = $1)
              AND (
                    (
                        candidate.status = 'queued'
                        AND COALESCE(candidate.heartbeat_at, candidate.created_at)
                            < now() - ($2::integer * interval '1 second')
                    )
                    OR (
                        candidate.status = 'running'
                        AND COALESCE(candidate.heartbeat_at, candidate.started_at, candidate.created_at)
                            < now() - ($3::integer * interval '1 second')
                    )
              )
            FOR UPDATE SKIP LOCKED
        )
        UPDATE grile_runs AS operation
        SET status = 'failed',
            error_message = $4,
            finished_at = now(),
            heartbeat_at = now()
        FROM candidates
        WHERE operation.id = candidates.id
          AND operation.status IN ('queued', 'running')
        RETURNING operation.id
        """,
        run_month,
        queued_lease_seconds,
        running_lease_seconds,
        GRILE_RUN_LEASE_EXPIRED,
    )

async def _reconcile_stale_store_refreshes_on_connection(
    conn: asyncpg.Connection,
    *,
    refresh_id: int | None = None,
    run_month: str | None = None,
    site_code: str | None = None,
    queued_lease_seconds: int,
    running_lease_seconds: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        WITH candidates AS (
            SELECT candidate.id
            FROM grile_store_refreshes AS candidate
            WHERE candidate.status IN ('queued', 'running')
              AND ($1::bigint IS NULL OR candidate.id = $1)
              AND ($2::text IS NULL OR candidate.run_month = $2)
              AND ($3::text IS NULL OR candidate.site_code = $3)
              AND (
                    (
                        candidate.status = 'queued'
                        AND COALESCE(candidate.heartbeat_at, candidate.created_at)
                            < now() - ($4::integer * interval '1 second')
                    )
                    OR (
                        candidate.status = 'running'
                        AND COALESCE(
                            candidate.heartbeat_at,
                            candidate.started_at,
                            candidate.created_at
                        ) < now() - ($5::integer * interval '1 second')
                    )
              )
            FOR UPDATE SKIP LOCKED
        )
        UPDATE grile_store_refreshes AS operation
        SET status = 'failed', error_code = $6, error_message = $6,
            projection_applied = false, finished_at = now(), heartbeat_at = now()
        FROM candidates
        WHERE operation.id = candidates.id
          AND operation.status IN ('queued', 'running')
        RETURNING operation.id
        """,
        refresh_id,
        run_month,
        site_code,
        queued_lease_seconds,
        running_lease_seconds,
        GRILE_STORE_REFRESH_LEASE_EXPIRED,
    )

async def _record_observation(conn: asyncpg.Connection, *, run_month: str, row: dict[str, Any], source: str, source_run_id: int | None, store_refresh_id: int | None, generation: int, checked_by_sub: str | None) -> bool:
    observation = await conn.fetchrow(
        """
        INSERT INTO grile_store_observations (
            run_month, site_code, source, source_run_id, store_refresh_id, generation,
            completion_pct, last_edit, grila_target, grila_sales, db_target, db_sales_mtd,
            db_max_sale_date, fill_status, target_status, sales_status, tolerance,
            completion_algorithm_version, completion_as_of,
            error_code, error_message, raw_summary, content_sha256, checked_by_sub
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
            $19,$20,$21,$22,$23,$24
        )
        RETURNING id, checked_at
        """,
        run_month, row["site_code"], source, source_run_id, store_refresh_id, generation,
        row.get("completion_pct"), row.get("last_edit"), row.get("grila_target"), row.get("grila_sales"),
        row.get("db_target"), row.get("db_sales_mtd"), row.get("db_max_sale_date"), row.get("fill_status"),
        row.get("target_status"), row.get("sales_status"), row.get("tolerance"),
        row.get("completion_algorithm_version", 1), row.get("completion_as_of"),
        row.get("error_code"), row.get("error_message"),
        json.dumps(row.get("raw_summary")) if row.get("raw_summary") is not None else None,
        row.get("content_sha256"), checked_by_sub,
    )
    if observation is None:  # pragma: no cover
        raise RuntimeError("Failed to retain immutable Grile observation")
    kwargs = dict(
        conn=conn, run_month=run_month, row=row, source=source, source_run_id=source_run_id,
        generation=generation, checked_by_sub=checked_by_sub, observation_id=int(observation["id"]),
        checked_at=observation["checked_at"],
    )
    if row.get("error_code"):
        return await _apply_error_projection(**kwargs)
    return await _apply_success_projection(**kwargs)


async def _apply_success_projection(
    *,
    conn: asyncpg.Connection,
    run_month: str,
    row: dict[str, Any],
    source: str,
    source_run_id: int | None,
    generation: int,
    checked_by_sub: str | None,
    observation_id: int,
    checked_at: Any,
) -> bool:
    applied = await conn.fetchval(
        """
        INSERT INTO grile_store_current_status (
            run_month, site_code, source_run_id, source, completion_pct, last_edit,
            grila_target, grila_sales, db_target, db_sales_mtd, db_max_sale_date,
            fill_status, target_status, sales_status, tolerance,
            completion_algorithm_version, completion_as_of,
            error_code, error_message, raw_summary, content_sha256,
            checked_by_sub, checked_at, generation, current_observation_id,
            last_success_observation_id, last_success_checked_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
            NULL,NULL,$18,$19,$20,$21,$22,$23,$23,$21
        )
        ON CONFLICT (run_month, site_code) DO UPDATE SET
            source_run_id = EXCLUDED.source_run_id,
            source = EXCLUDED.source,
            completion_pct = EXCLUDED.completion_pct,
            last_edit = EXCLUDED.last_edit,
            grila_target = EXCLUDED.grila_target,
            grila_sales = EXCLUDED.grila_sales,
            db_target = EXCLUDED.db_target,
            db_sales_mtd = EXCLUDED.db_sales_mtd,
            db_max_sale_date = EXCLUDED.db_max_sale_date,
            fill_status = EXCLUDED.fill_status,
            target_status = EXCLUDED.target_status,
            sales_status = EXCLUDED.sales_status,
            tolerance = EXCLUDED.tolerance,
            completion_algorithm_version = EXCLUDED.completion_algorithm_version,
            completion_as_of = EXCLUDED.completion_as_of,
            error_code = NULL,
            error_message = NULL,
            raw_summary = EXCLUDED.raw_summary,
            content_sha256 = EXCLUDED.content_sha256,
            checked_by_sub = EXCLUDED.checked_by_sub,
            checked_at = EXCLUDED.checked_at,
            generation = EXCLUDED.generation,
            current_observation_id = EXCLUDED.current_observation_id,
            last_success_observation_id = EXCLUDED.last_success_observation_id,
            last_success_checked_at = EXCLUDED.last_success_checked_at
        WHERE EXCLUDED.generation > grile_store_current_status.generation
           OR (
                EXCLUDED.generation = grile_store_current_status.generation
                AND EXCLUDED.checked_at > grile_store_current_status.checked_at
           )
        RETURNING true
        """,
        run_month,
        row["site_code"],
        source_run_id,
        source,
        row.get("completion_pct"),
        row.get("last_edit"),
        row.get("grila_target"),
        row.get("grila_sales"),
        row.get("db_target"),
        row.get("db_sales_mtd"),
        row.get("db_max_sale_date"),
        row.get("fill_status"),
        row.get("target_status"),
        row.get("sales_status"),
        row.get("tolerance"),
        row.get("completion_algorithm_version", 1),
        row.get("completion_as_of"),
        json.dumps(row.get("raw_summary")) if row.get("raw_summary") is not None else None,
        row.get("content_sha256"),
        checked_by_sub,
        checked_at,
        generation,
        observation_id,
    )
    return applied is True

async def _apply_error_projection(
    *,
    conn: asyncpg.Connection,
    run_month: str,
    row: dict[str, Any],
    source: str,
    source_run_id: int | None,
    generation: int,
    checked_by_sub: str | None,
    observation_id: int,
    checked_at: Any,
) -> bool:
    applied = await conn.fetchval(
        """
        INSERT INTO grile_store_current_status (
            run_month, site_code, source_run_id, source, completion_pct, last_edit,
            grila_target, grila_sales, db_target, db_sales_mtd, db_max_sale_date,
            fill_status, target_status, sales_status, tolerance,
            completion_algorithm_version, completion_as_of,
            error_code, error_message, raw_summary, content_sha256,
            checked_by_sub, checked_at, generation,
            last_error_observation_id, last_error_generation, last_error_checked_at,
            last_error_code, last_error_message
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
            $18,$19,$20,$21,$22,$23,$24,$25,$24,$23,$18,$19
        )
        ON CONFLICT (run_month, site_code) DO UPDATE SET
            last_error_observation_id = EXCLUDED.last_error_observation_id,
            last_error_generation = EXCLUDED.last_error_generation,
            last_error_checked_at = EXCLUDED.last_error_checked_at,
            last_error_code = EXCLUDED.last_error_code,
            last_error_message = EXCLUDED.last_error_message
        WHERE EXCLUDED.last_error_generation >= grile_store_current_status.generation
          AND (
                EXCLUDED.last_error_generation > grile_store_current_status.last_error_generation
                OR (
                    EXCLUDED.last_error_generation = grile_store_current_status.last_error_generation
                    AND (
                        grile_store_current_status.last_error_checked_at IS NULL
                        OR EXCLUDED.last_error_checked_at > grile_store_current_status.last_error_checked_at
                    )
                )
          )
        RETURNING true
        """,
        run_month,
        row["site_code"],
        source_run_id,
        source,
        row.get("completion_pct"),
        row.get("last_edit"),
        row.get("grila_target"),
        row.get("grila_sales"),
        row.get("db_target"),
        row.get("db_sales_mtd"),
        row.get("db_max_sale_date"),
        row.get("fill_status"),
        row.get("target_status"),
        row.get("sales_status"),
        row.get("tolerance"),
        row.get("completion_algorithm_version", 1),
        row.get("completion_as_of"),
        row.get("error_code"),
        row.get("error_message"),
        json.dumps(row.get("raw_summary")) if row.get("raw_summary") is not None else None,
        row.get("content_sha256"),
        checked_by_sub,
        checked_at,
        generation,
        observation_id,
    )
    return applied is True
