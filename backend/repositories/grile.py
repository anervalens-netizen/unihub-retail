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


class GrileRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ---------- grile_sheets (maparea read-only site_code -> sheet_id) ----------

    async def get_active_sheets(self) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT gs.site_code, gs.sheet_id, gs.registry_key
                FROM grile_sheets gs
                JOIN stores s ON s.site_code = gs.site_code
                WHERE gs.is_active = true
                ORDER BY gs.site_code
                """
            )

    async def count_active_sheets(self) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT count(*) FROM grile_sheets WHERE is_active = true"
            )

    async def get_sheet_map(self) -> dict[str, str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT site_code, sheet_id FROM grile_sheets")
            return {r["site_code"]: r["sheet_id"] for r in rows}

    async def get_latest_data_month(self) -> str | None:
        """Ultima luna operationala din vanzari sau targete.

        La inceput de luna targetele pot fi publicate inaintea primului import
        de vanzari. Default-ul Grile trebuie sa urmeze luna noua in acel caz,
        nu sa ramana blocat pe luna anterioara.
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT max(month)
                FROM (
                    SELECT max(import_month) AS month FROM reporting_item_month
                    UNION ALL
                    SELECT max(import_month) AS month FROM store_targets
                ) months
                """
            )

    # ---------- expected din retail DB (target + vanzari MTD) ----------

    async def get_expected_by_site(self, month: str) -> dict[str, dict[str, Any]]:
        """site_code -> {db_target, db_sales_mtd, db_max_sale_date} pentru luna."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    st.site_code,
                    st.target_value AS db_target,
                    COALESCE(sales.sales_mtd, 0) AS db_sales_mtd,
                    sales_days.max_sale_date AS db_max_sale_date
                FROM store_targets st
                LEFT JOIN (
                    SELECT site_code, SUM(total_sales) AS sales_mtd
                    FROM reporting_item_month
                    WHERE import_month = $1
                    GROUP BY site_code
                ) sales ON sales.site_code = st.site_code
                LEFT JOIN (
                    SELECT site_code, MAX(sale_date) AS max_sale_date
                    FROM reporting_item_day
                    WHERE import_month = $1
                    GROUP BY site_code
                ) sales_days ON sales_days.site_code = st.site_code
                WHERE st.import_month = $1
                """,
                month,
            )
            out: dict[str, dict[str, Any]] = {}
            for r in rows:
                out[r["site_code"]] = {
                    "db_target": r["db_target"],
                    "db_sales_mtd": r["db_sales_mtd"],
                    "db_max_sale_date": r["db_max_sale_date"],
                }
            return out

    # ---------- ierarhia (din DB live, fara sidecar) ----------

    async def get_hierarchy(self) -> dict[str, dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.site_code, s.locatie, s.firma, s.regional, s.asm,
                       tl.name AS team_leader_name
                FROM stores s
                LEFT JOIN team_leaders tl ON tl.id = s.team_leader_id
                """
            )
            return {
                r["site_code"]: {
                    "locatie": r["locatie"],
                    "firma": r["firma"],
                    "regional": r["regional"],
                    "asm": r["asm"],
                    # None cand magazinul nu are TL — UI nu mai afiseaza "Fara Team Leader"
                    "team_leader_name": r["team_leader_name"],
                }
                for r in rows
            }

    # ---------- runs ----------

    async def reserve_run(
        self,
        *,
        run_month: str,
        source: str,
        source_snapshot_id: int | None,
        triggered_by_sub: str | None,
    ) -> int | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE grile_runs
                    SET status = 'failed',
                        error_message = 'Rezervare expirata inainte de finalizare',
                        finished_at = now(),
                        heartbeat_at = now()
                    WHERE run_month = $1
                      AND status IN ('queued', 'running')
                      AND COALESCE(heartbeat_at, started_at, created_at)
                          < now() - interval '2 hours'
                    """,
                    run_month,
                )
                return await conn.fetchval(
                    """
                    INSERT INTO grile_runs (
                        run_month, source, source_snapshot_id,
                        triggered_by_sub, status, heartbeat_at
                    )
                    VALUES ($1, $2, $3, $4, 'queued', now())
                    ON CONFLICT (run_month)
                        WHERE status IN ('queued', 'running')
                    DO NOTHING
                    RETURNING id
                    """,
                    run_month,
                    source,
                    source_snapshot_id,
                    triggered_by_sub,
                )

    async def start_run(self, run_id: int, progress_total: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE grile_runs
                SET status = 'running',
                    progress_total = $2,
                    started_at = now(),
                    heartbeat_at = now()
                WHERE id = $1 AND status = 'queued'
                """,
                run_id,
                progress_total,
            )
        return result == "UPDATE 1"

    async def set_run_progress(self, run_id: int, current: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE grile_runs
                SET progress_current = $2, heartbeat_at = now()
                WHERE id = $1 AND status = 'running'
                """,
                run_id, current,
            )

    async def finalize_run(
        self,
        run_id: int,
        *,
        status: str,
        ok_count: int,
        problem_count: int,
        error_count: int,
        duration_ms: int,
        error_message: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE grile_runs
                SET status = $2, ok_count = $3, problem_count = $4, error_count = $5,
                    duration_ms = $6, error_message = $7,
                    progress_current = progress_total, finished_at = now(),
                    heartbeat_at = now()
                WHERE id = $1
                """,
                run_id, status, ok_count, problem_count, error_count, duration_ms, error_message,
            )

    async def upsert_store_status(self, run_id: int, row: dict[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO grile_store_status
                    (run_id, site_code, completion_pct, last_edit,
                     grila_target, grila_sales, db_target, db_sales_mtd, db_max_sale_date,
                     fill_status, target_status, sales_status, tolerance,
                     error_code, error_message, raw_summary)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                ON CONFLICT (run_id, site_code) DO UPDATE SET
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
                    error_code = EXCLUDED.error_code,
                    error_message = EXCLUDED.error_message,
                    raw_summary = EXCLUDED.raw_summary
                """,
                run_id,
                row["site_code"],
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
                row.get("error_code"),
                row.get("error_message"),
                json.dumps(row.get("raw_summary")) if row.get("raw_summary") is not None else None,
            )

    async def get_latest_run(self, month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                SELECT {_RUN_COLUMNS} FROM grile_runs
                WHERE run_month = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                month,
            )

    async def get_run(self, run_id: int) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"SELECT {_RUN_COLUMNS} FROM grile_runs WHERE id = $1",
                run_id,
            )

    async def get_running_run(self, month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                SELECT {_RUN_COLUMNS} FROM grile_runs
                WHERE run_month = $1 AND status IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1
                """,
                month,
            )

    async def get_run_statuses(self, run_id: int) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"SELECT {_STORE_STATUS_COLUMNS} FROM grile_store_status WHERE run_id = $1",
                run_id,
            )
