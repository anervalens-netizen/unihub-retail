from __future__ import annotations

import asyncio

_IMPORT_RECOVERY_SQL_1 = """
                UPDATE import_snapshots
                SET owner_id = gen_random_uuid(),
                    lease_until = now() + interval '2 hours',
                    heartbeat_at = now(),
                    finished_at = NULL,
                    error_message = 'Promovarea a fost întreruptă de restart; retry permis',
                    rows_imported = COALESCE(NULLIF(manifest->>'rows_imported', '')::integer, rows_imported),
                    manifest = jsonb_set(manifest, '{generation_state}', '"validated"'::jsonb, true)
                WHERE status = 'processing'
                  AND manifest->>'generation_state' = 'promoting'
                  AND source_artifact_state IS NULL
                  AND (
                        (lease_until IS NOT NULL AND lease_until <= now())
                        OR (lease_until IS NULL AND COALESCE(heartbeat_at, created_at) < now() - interval '1 hour')
                  )
                RETURNING id
                """

_IMPORT_RECOVERY_SQL_2 = """
                UPDATE import_snapshots
                SET status = 'failed',
                    rows_imported = 0,
                    error_message = 'Import intrerupt de restartul workerului; retry permis',
                    heartbeat_at = now(),
                    finished_at = now()
                WHERE status = 'processing'
                  AND COALESCE(manifest->>'generation_state', '') NOT IN ('validated', 'promoting')
                  AND COALESCE(source_artifact_state, '') NOT IN ('artifact_retaining', 'artifact_retained')
                  AND (
                        (lease_until IS NOT NULL AND lease_until <= now())
                        OR (lease_until IS NULL AND COALESCE(heartbeat_at, created_at) < now() - interval '1 hour')
                  )
                RETURNING id
                """

_IMPORT_RECOVERY_SQL_3 = """
            SELECT id, generation_token, owner_id, import_month, source_spool_path,
                   source_sha256, source_artifact_bytes
            FROM import_snapshots
            WHERE status = 'processing'
              AND source_artifact_state IN ('artifact_retaining', 'artifact_retained')
            """

_IMPORT_RECOVERY_SQL_4 = """
                    UPDATE import_snapshots
                    SET source_spool_path = $4,
                        source_artifact_retained_path = $4,
                        source_artifact_state = 'artifact_retained',
                        source_artifact_sha256 = $5,
                        source_artifact_bytes = $6,
                        source_artifact_retained_at = COALESCE(source_artifact_retained_at, now()),
                        heartbeat_at = now(),
                        manifest = CASE
                            WHEN manifest->>'generation_state' = 'promoting'
                            THEN jsonb_set(manifest, '{generation_state}', '"validated"'::jsonb, true)
                            ELSE manifest
                        END,
                        status = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN status ELSE 'failed'
                        END,
                        rows_imported = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN rows_imported ELSE 0
                        END,
                        error_message = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN error_message
                            ELSE 'Import interrupted before validation; exact-source retry permitted'
                        END,
                        finished_at = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN finished_at ELSE now()
                        END,
                        lease_until = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN now() + interval '2 hours' ELSE now()
                        END
                    WHERE id = $1 AND generation_token = $2::uuid
                      AND owner_id = $3::uuid AND status = 'processing'
                      AND source_artifact_state IN ('artifact_retaining', 'artifact_retained')
                    RETURNING id
                    """

_IMPORT_RECOVERY_SQL_5 = """
                    UPDATE import_snapshots
                    SET status = 'failed', rows_imported = 0,
                        error_message = $4, finished_at = now(), heartbeat_at = now(),
                        lease_until = now(), source_artifact_state = 'recovery_required'
                    WHERE id = $1 AND generation_token = $2::uuid
                      AND owner_id = $3::uuid AND status = 'processing'
                    """

_IMPORT_RECOVERY_SQL_6 = """
                    UPDATE import_snapshots
                    SET source_artifact_state = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_state ELSE NULL
                        END,
                        source_artifact_sha256 = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_sha256 ELSE NULL
                        END,
                        source_artifact_bytes = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_bytes ELSE NULL
                        END,
                        source_artifact_retained_at = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_retained_at ELSE NULL
                        END,
                        source_artifact_retained_path = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_retained_path ELSE NULL
                        END,
                        manifest = CASE
                            WHEN manifest->>'generation_state' = 'promoting'
                            THEN jsonb_set(manifest, '{generation_state}', '"validated"'::jsonb, true)
                            ELSE manifest
                        END,
                        error_message = $4,
                        heartbeat_at = now(),
                        lease_until = now()
                    WHERE id = $1 AND generation_token = $2::uuid
                      AND owner_id = $3::uuid AND status = 'processing'
                    """

_IMPORT_RECOVERY_SQL_7 = """
            SELECT DISTINCT COALESCE(s.source_artifact_retained_path, s.source_spool_path) AS path
            FROM import_snapshots s
            WHERE s.id IN (
                SELECT snapshot_id FROM sales_generation_heads
                UNION SELECT previous_snapshot_id FROM sales_generation_heads
                UNION SELECT from_snapshot_id FROM sales_generation_promotions
                UNION SELECT to_snapshot_id FROM sales_generation_promotions
                UNION SELECT id FROM import_snapshots
                      WHERE status = 'processing'
                        AND source_artifact_state = 'artifact_retained'
            )
              AND COALESCE(s.source_artifact_retained_path, s.source_spool_path) IS NOT NULL
            """

import asyncpg

from services.jobs import (
    SalesImportArtifactConflictError,
    SalesImportArtifactError,
    cleanup_sales_import_retained_artifacts,
    retain_sales_import_spool_file,
    verify_sales_import_artifact,
)

async def reconcile_interrupted_imports(pool: asyncpg.Pool) -> list[int]:
    """Close leases left by a worker stop before ARQ retries queued imports.
    Startup only closes an expired staging lease (or a legacy reservation stale
    for more than one hour). A validated generation is deliberately retained
    for explicit promotion after a worker restart; a stale promoting claim is
    returned to validated so the operator can retry it safely.
    """
    artifact_recovered = await _reconcile_sales_artifacts(pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            recovered = await conn.fetch(
                _IMPORT_RECOVERY_SQL_1
            )
            closed = await conn.fetch(
                _IMPORT_RECOVERY_SQL_2
            )
    return [*artifact_recovered, *[int(row["id"]) for row in [*recovered, *closed]]]


async def _reconcile_sales_artifacts(pool: asyncpg.Pool) -> list[int]:
    """Retry only fenced artifact work; never promote a generation at startup."""
    async with pool.acquire() as conn:
        candidates = await conn.fetch(
            _IMPORT_RECOVERY_SQL_3
        )
    reconciled: list[int] = []
    for candidate in candidates:
        snapshot_id = int(candidate["id"])
        try:
            retained = await asyncio.to_thread(
                retain_sales_import_spool_file,
                str(candidate["source_spool_path"]),
                import_month=str(candidate["import_month"]),
                snapshot_id=snapshot_id,
                expected_digest=str(candidate["source_sha256"]),
                expected_bytes=(
                    int(candidate["source_artifact_bytes"])
                    if candidate["source_artifact_bytes"] is not None
                    else None
                ),
            )
            size = await asyncio.to_thread(
                verify_sales_import_artifact,
                str(retained),
                str(candidate["source_sha256"]),
                int(candidate["source_artifact_bytes"])
                if candidate["source_artifact_bytes"] is not None
                else None,
            )
            async with pool.acquire() as conn:
                updated = await conn.fetchval(
                    _IMPORT_RECOVERY_SQL_4,
                    snapshot_id,
                    str(candidate["generation_token"]),
                    str(candidate["owner_id"]),
                    str(retained),
                    str(candidate["source_sha256"]),
                    size,
                )
            if updated is not None:
                reconciled.append(snapshot_id)
        except (SalesImportArtifactConflictError, SalesImportArtifactError) as exc:
            async with pool.acquire() as conn:
                await conn.execute(
                    _IMPORT_RECOVERY_SQL_5,
                    snapshot_id,
                    str(candidate["generation_token"]),
                    str(candidate["owner_id"]),
                    f"Sales artifact recovery required: {type(exc).__name__}",
                )
            reconciled.append(snapshot_id)
        except OSError as exc:
            # Transient filesystem failures leave the validated candidate
            # retryable through an exact-source re-upload. No auto-promotion.
            async with pool.acquire() as conn:
                await conn.execute(
                    _IMPORT_RECOVERY_SQL_6,
                    snapshot_id,
                    str(candidate["generation_token"]),
                    str(candidate["owner_id"]),
                    f"Sales artifact retain retryable: {type(exc).__name__}",
                )
            reconciled.append(snapshot_id)

    async with pool.acquire() as conn:
        roots = await conn.fetch(
            _IMPORT_RECOVERY_SQL_7
        )
    keep_paths = {str(row["path"]) for row in roots}
    await asyncio.to_thread(cleanup_sales_import_retained_artifacts, keep_paths)
    return reconciled
