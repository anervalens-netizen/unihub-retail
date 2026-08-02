from __future__ import annotations

import json
from typing import Any

import asyncpg


_RUN_COLUMNS = """
    id, run_month, source_snapshot_id, status, source, progress_current,
    progress_total, ok_count, problem_count, error_count, duration_ms,
    triggered_by_sub, error_message, started_at, heartbeat_at, finished_at,
    created_at
"""

_STORE_STATUS_COLUMNS = """
    run_id, site_code, completion_pct, last_edit, grila_target, grila_sales,
    db_target, db_sales_mtd, db_max_sale_date, fill_status, target_status,
    sales_status, tolerance, error_code, error_message, raw_summary
"""

_CURRENT_STATUS_COLUMNS = """
    run_month, site_code, source_run_id, source, completion_pct, last_edit,
    grila_target, grila_sales, db_target, db_sales_mtd, db_max_sale_date,
    fill_status, target_status, sales_status, tolerance, error_code,
    error_message, raw_summary, content_sha256, checked_by_sub, checked_at,
    generation, current_observation_id, last_success_observation_id,
    last_success_checked_at, last_error_observation_id, last_error_generation,
    last_error_checked_at, last_error_code, last_error_message
"""


class GrileRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

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
                await conn.execute(
                    """
                    UPDATE grile_runs SET status = 'failed',
                        error_message = 'Rezervare expirata inainte de finalizare',
                        finished_at = now(), heartbeat_at = now()
                    WHERE run_month = $1 AND status IN ('queued', 'running')
                      AND COALESCE(heartbeat_at, started_at, created_at) < now() - interval '2 hours'
                    """, run_month,
                )
                return await conn.fetchval(
                    """
                    INSERT INTO grile_runs (run_month, source, source_snapshot_id, triggered_by_sub, status, heartbeat_at)
                    VALUES ($1, $2, $3, $4, 'queued', now())
                    ON CONFLICT (run_month) WHERE status IN ('queued', 'running') DO NOTHING
                    RETURNING id
                    """, run_month, source, source_snapshot_id, triggered_by_sub,
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

    async def set_run_progress(self, run_id: int, current: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """UPDATE grile_runs SET progress_current = $2, heartbeat_at = now()
                   WHERE id = $1 AND status = 'running'""", run_id, current,
            )

    async def finalize_run(self, run_id: int, *, status: str, ok_count: int, problem_count: int, error_count: int, duration_ms: int, error_message: str | None = None) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE grile_runs SET status = $2, ok_count = $3, problem_count = $4,
                    error_count = $5, duration_ms = $6, error_message = $7,
                    progress_current = progress_total, finished_at = now(), heartbeat_at = now()
                WHERE id = $1
                """, run_id, status, ok_count, problem_count, error_count, duration_ms, error_message,
            )

    async def record_full_observation(self, run_id: int, row: dict[str, Any], *, generation: int, checked_by_sub: str | None = None) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO grile_store_status
                        (run_id, site_code, completion_pct, last_edit, grila_target, grila_sales,
                         db_target, db_sales_mtd, db_max_sale_date, fill_status, target_status,
                         sales_status, tolerance, error_code, error_message, raw_summary)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                    ON CONFLICT (run_id, site_code) DO UPDATE SET
                        completion_pct = EXCLUDED.completion_pct, last_edit = EXCLUDED.last_edit,
                        grila_target = EXCLUDED.grila_target, grila_sales = EXCLUDED.grila_sales,
                        db_target = EXCLUDED.db_target, db_sales_mtd = EXCLUDED.db_sales_mtd,
                        db_max_sale_date = EXCLUDED.db_max_sale_date, fill_status = EXCLUDED.fill_status,
                        target_status = EXCLUDED.target_status, sales_status = EXCLUDED.sales_status,
                        tolerance = EXCLUDED.tolerance, error_code = EXCLUDED.error_code,
                        error_message = EXCLUDED.error_message, raw_summary = EXCLUDED.raw_summary
                    """, run_id, *_status_params(row),
                )
                run_month = await conn.fetchval("SELECT run_month FROM grile_runs WHERE id = $1", run_id)
                if not isinstance(run_month, str):
                    raise RuntimeError("Grile run disappeared before observation persistence")
                return await _record_observation(conn, run_month=run_month, row=row, source="full", source_run_id=run_id, store_refresh_id=None, generation=generation, checked_by_sub=checked_by_sub)

    async def reserve_store_refresh(self, *, run_month: str, site_code: str, requested_by_sub: str) -> int | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE grile_store_refreshes SET status = 'failed', error_message = 'Refresh reservation expired',
                        finished_at = now(), heartbeat_at = now()
                    WHERE run_month = $1 AND site_code = $2 AND status IN ('queued', 'running')
                      AND COALESCE(heartbeat_at, started_at, created_at) < now() - interval '2 hours'
                    """, run_month, site_code,
                )
                active = await conn.fetchval(
                    """
                    SELECT id FROM grile_store_refreshes
                    WHERE run_month = $1 AND site_code = $2 AND status IN ('queued', 'running')
                    """, run_month, site_code,
                )
                if active is not None:
                    return None
                generation = await _allocate_generation(conn, run_month, site_code)
                return await conn.fetchval(
                    """
                    INSERT INTO grile_store_refreshes (run_month, site_code, generation, requested_by_sub, heartbeat_at)
                    VALUES ($1, $2, $3, $4, now())
                    ON CONFLICT (run_month, site_code) WHERE status IN ('queued', 'running') DO NOTHING
                    RETURNING id
                    """, run_month, site_code, generation, requested_by_sub,
                )

    async def fail_queued_store_refresh(self, refresh_id: int, error_message: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE grile_store_refreshes SET status = 'failed', error_message = $2,
                    finished_at = now(), heartbeat_at = now()
                WHERE id = $1 AND status = 'queued'
                """, refresh_id, error_message,
            )

    async def get_active_store_refresh(self, run_month: str, site_code: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, run_month, site_code, generation, status, requested_by_sub, error_message,
                       started_at, heartbeat_at, finished_at, created_at
                FROM grile_store_refreshes
                WHERE run_month = $1 AND site_code = $2 AND status IN ('queued', 'running')
                ORDER BY id DESC LIMIT 1
                """, run_month, site_code,
            )

    async def claim_store_refresh(self, refresh_id: int) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                UPDATE grile_store_refreshes SET status = 'running', started_at = now(), heartbeat_at = now()
                WHERE id = $1 AND status = 'queued'
                RETURNING id, run_month, site_code, generation, requested_by_sub
                """, refresh_id,
            )

    async def finish_store_refresh(self, refresh_id: int, *, status: str, error_message: str | None = None) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE grile_store_refreshes SET status = $2, error_message = $3,
                    finished_at = now(), heartbeat_at = now()
                WHERE id = $1 AND status = 'running'
                """, refresh_id, status, error_message,
            )

    async def record_store_refresh_observation(self, refresh_id: int, row: dict[str, Any]) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                refresh = await conn.fetchrow(
                    """
                    SELECT run_month, generation, requested_by_sub FROM grile_store_refreshes
                    WHERE id = $1 AND status = 'running' FOR UPDATE
                    """, refresh_id,
                )
                if refresh is None:
                    raise RuntimeError("Store refresh is not an active fenced operation")
                return await _record_observation(conn, run_month=refresh["run_month"], row=row, source="store", source_run_id=None, store_refresh_id=refresh_id, generation=int(refresh["generation"]), checked_by_sub=refresh["requested_by_sub"])

    async def get_current_status(self, month: str, site_code: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(f"SELECT {_CURRENT_STATUS_COLUMNS} FROM grile_store_current_status WHERE run_month = $1 AND site_code = $2", month, site_code)

    async def get_current_statuses(self, month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(f"SELECT {_CURRENT_STATUS_COLUMNS} FROM grile_store_current_status WHERE run_month = $1", month)

    async def get_latest_run(self, month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(f"SELECT {_RUN_COLUMNS} FROM grile_runs WHERE run_month = $1 ORDER BY created_at DESC LIMIT 1", month)

    async def get_run(self, run_id: int) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(f"SELECT {_RUN_COLUMNS} FROM grile_runs WHERE id = $1", run_id)

    async def get_running_run(self, month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(f"SELECT {_RUN_COLUMNS} FROM grile_runs WHERE run_month = $1 AND status IN ('queued', 'running') ORDER BY created_at DESC LIMIT 1", month)

    async def get_run_statuses(self, run_id: int) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(f"SELECT {_STORE_STATUS_COLUMNS} FROM grile_store_status WHERE run_id = $1", run_id)


def _status_params(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["site_code"], row.get("completion_pct"), row.get("last_edit"),
        row.get("grila_target"), row.get("grila_sales"), row.get("db_target"),
        row.get("db_sales_mtd"), row.get("db_max_sale_date"), row.get("fill_status"),
        row.get("target_status"), row.get("sales_status"), row.get("tolerance"),
        row.get("error_code"), row.get("error_message"),
        json.dumps(row.get("raw_summary")) if row.get("raw_summary") is not None else None,
    )


async def _allocate_generation(conn: asyncpg.Connection, run_month: str, site_code: str) -> int:
    return int(await conn.fetchval(
        """
        INSERT INTO grile_store_projection_generations (run_month, site_code, next_generation)
        VALUES ($1, $2, 1)
        ON CONFLICT (run_month, site_code) DO UPDATE
        SET next_generation = grile_store_projection_generations.next_generation + 1
        RETURNING next_generation
        """, run_month, site_code,
    ))


async def _record_observation(conn: asyncpg.Connection, *, run_month: str, row: dict[str, Any], source: str, source_run_id: int | None, store_refresh_id: int | None, generation: int, checked_by_sub: str | None) -> bool:
    observation = await conn.fetchrow(
        """
        INSERT INTO grile_store_observations (
            run_month, site_code, source, source_run_id, store_refresh_id, generation,
            completion_pct, last_edit, grila_target, grila_sales, db_target, db_sales_mtd,
            db_max_sale_date, fill_status, target_status, sales_status, tolerance,
            error_code, error_message, raw_summary, content_sha256, checked_by_sub
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
        RETURNING id, checked_at
        """,
        run_month, row["site_code"], source, source_run_id, store_refresh_id, generation,
        row.get("completion_pct"), row.get("last_edit"), row.get("grila_target"), row.get("grila_sales"),
        row.get("db_target"), row.get("db_sales_mtd"), row.get("db_max_sale_date"), row.get("fill_status"),
        row.get("target_status"), row.get("sales_status"), row.get("tolerance"), row.get("error_code"),
        row.get("error_message"), json.dumps(row.get("raw_summary")) if row.get("raw_summary") is not None else None,
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


async def _apply_success_projection(*, conn: asyncpg.Connection, run_month: str, row: dict[str, Any], source: str, source_run_id: int | None, generation: int, checked_by_sub: str | None, observation_id: int, checked_at: Any) -> bool:
    applied = await conn.fetchval(
        """
        INSERT INTO grile_store_current_status (
            run_month, site_code, source_run_id, source, completion_pct, last_edit,
            grila_target, grila_sales, db_target, db_sales_mtd, db_max_sale_date,
            fill_status, target_status, sales_status, tolerance, error_code, error_message,
            raw_summary, content_sha256, checked_by_sub, checked_at, generation,
            current_observation_id, last_success_observation_id, last_success_checked_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NULL,NULL,$16,$17,$18,$19,$20,$21,$22,$19)
        ON CONFLICT (run_month, site_code) DO UPDATE SET
            source_run_id = EXCLUDED.source_run_id, source = EXCLUDED.source,
            completion_pct = EXCLUDED.completion_pct, last_edit = EXCLUDED.last_edit,
            grila_target = EXCLUDED.grila_target, grila_sales = EXCLUDED.grila_sales,
            db_target = EXCLUDED.db_target, db_sales_mtd = EXCLUDED.db_sales_mtd,
            db_max_sale_date = EXCLUDED.db_max_sale_date, fill_status = EXCLUDED.fill_status,
            target_status = EXCLUDED.target_status, sales_status = EXCLUDED.sales_status,
            tolerance = EXCLUDED.tolerance, error_code = NULL, error_message = NULL,
            raw_summary = EXCLUDED.raw_summary, content_sha256 = EXCLUDED.content_sha256,
            checked_by_sub = EXCLUDED.checked_by_sub, checked_at = EXCLUDED.checked_at,
            generation = EXCLUDED.generation, current_observation_id = EXCLUDED.current_observation_id,
            last_success_observation_id = EXCLUDED.last_success_observation_id,
            last_success_checked_at = EXCLUDED.last_success_checked_at
        WHERE EXCLUDED.generation > grile_store_current_status.generation
           OR (EXCLUDED.generation = grile_store_current_status.generation
               AND EXCLUDED.checked_at > grile_store_current_status.checked_at)
        RETURNING true
        """,
        run_month, row["site_code"], source_run_id, source, row.get("completion_pct"), row.get("last_edit"),
        row.get("grila_target"), row.get("grila_sales"), row.get("db_target"), row.get("db_sales_mtd"),
        row.get("db_max_sale_date"), row.get("fill_status"), row.get("target_status"), row.get("sales_status"),
        row.get("tolerance"), json.dumps(row.get("raw_summary")) if row.get("raw_summary") is not None else None,
        row.get("content_sha256"), checked_by_sub, checked_at, generation, observation_id, observation_id,
    )
    return applied is True


async def _apply_error_projection(*, conn: asyncpg.Connection, run_month: str, row: dict[str, Any], source: str, source_run_id: int | None, generation: int, checked_by_sub: str | None, observation_id: int, checked_at: Any) -> bool:
    applied = await conn.fetchval(
        """
        INSERT INTO grile_store_current_status (
            run_month, site_code, source_run_id, source, completion_pct, last_edit,
            grila_target, grila_sales, db_target, db_sales_mtd, db_max_sale_date,
            fill_status, target_status, sales_status, tolerance, error_code, error_message,
            raw_summary, content_sha256, checked_by_sub, checked_at, generation,
            last_error_observation_id, last_error_generation, last_error_checked_at,
            last_error_code, last_error_message
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$22,$21,$16,$17)
        ON CONFLICT (run_month, site_code) DO UPDATE SET
            last_error_observation_id = EXCLUDED.last_error_observation_id,
            last_error_generation = EXCLUDED.last_error_generation,
            last_error_checked_at = EXCLUDED.last_error_checked_at,
            last_error_code = EXCLUDED.last_error_code,
            last_error_message = EXCLUDED.last_error_message
        WHERE EXCLUDED.last_error_generation > grile_store_current_status.last_error_generation
           OR (EXCLUDED.last_error_generation = grile_store_current_status.last_error_generation
               AND (grile_store_current_status.last_error_checked_at IS NULL
                    OR EXCLUDED.last_error_checked_at > grile_store_current_status.last_error_checked_at))
        RETURNING true
        """,
        run_month, row["site_code"], source_run_id, source, row.get("completion_pct"), row.get("last_edit"),
        row.get("grila_target"), row.get("grila_sales"), row.get("db_target"), row.get("db_sales_mtd"),
        row.get("db_max_sale_date"), row.get("fill_status"), row.get("target_status"), row.get("sales_status"),
        row.get("tolerance"), row.get("error_code"), row.get("error_message"),
        json.dumps(row.get("raw_summary")) if row.get("raw_summary") is not None else None,
        row.get("content_sha256"), checked_by_sub, checked_at, generation, observation_id,
    )
    return applied is True
