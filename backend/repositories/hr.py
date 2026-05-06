from __future__ import annotations

from typing import Any
import asyncpg


class HrRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create_leave_request(self, data: dict) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                INSERT INTO leave_requests (agent_name, start_date, end_date, leave_type, notes)
                VALUES ($1, $2::text::date, $3::text::date, $4, $5)
                RETURNING id, agent_name, start_date::text, end_date::text, leave_type, notes,
                          status, created_at::text, updated_at::text
                """,
                data["agent_name"],
                data["start_date"],
                data["end_date"],
                data["leave_type"],
                data.get("notes"),
            )

    async def update_leave_status(self, request_id: int, status: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                UPDATE leave_requests
                SET status = $1, updated_at = now()
                WHERE id = $2
                RETURNING id, agent_name, start_date::text, end_date::text, leave_type, notes,
                          status, created_at::text, updated_at::text
                """,
                status,
                request_id,
            )

    async def list_leave_requests(self, status: str | None, agent_name: str | None) -> list[asyncpg.Record]:
        clauses = []
        params: list[Any] = []
        idx = 1
        if status:
            clauses.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if agent_name:
            clauses.append(f"agent_name ILIKE ${idx}")
            params.append(f"%{agent_name}%")
            idx += 1
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT id, agent_name, start_date::text, end_date::text, leave_type, notes,
                       status, created_at::text, updated_at::text
                FROM leave_requests
                {where}
                ORDER BY created_at DESC
                """,
                *params,
            )

    async def get_agent_performance(self, agent_name: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT
                    ram.import_month,
                    SUM(ram.total_sales) AS total_value,
                    SUM(ram.receipt_count) AS transaction_count,
                    SUM(ram.working_days) AS active_days,
                    COALESCE(
                        ROUND(
                            SUM(ram.total_sales)::numeric /
                            NULLIF(
                                (SELECT SUM(st.target_value)
                                 FROM store_targets st
                                 WHERE st.import_month = ram.import_month
                                   AND st.site_code = ram.site_code),
                                0
                            ) * 100,
                            1
                        ),
                        0
                    ) AS target_pct
                FROM reporting_agent_month ram
                WHERE ram.agent = $1
                  AND ram.import_month >= to_char(now() - interval '12 months', 'YYYY-MM')
                GROUP BY ram.import_month, ram.site_code
                ORDER BY ram.import_month
                """,
                agent_name,
            )

    async def get_asm_performance_rows(self, month: str, regional: str | None) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH asm_targets AS (
                    SELECT s.asm, SUM(st.target_value) AS total_target
                    FROM store_targets st
                    JOIN stores s ON s.site_code = st.site_code
                    WHERE st.import_month = $1
                    GROUP BY s.asm
                )
                SELECT
                    s.asm,
                    s.regional,
                    SUM(ram.total_sales)                                         AS total_sales,
                    COALESCE(at.total_target, 0)                                 AS total_target,
                    COUNT(DISTINCT ram.site_code)                                AS active_stores,
                    COUNT(DISTINCT ram.agent)                                    AS active_agents,
                    ROUND(
                        SUM(ram.receipt_2plus_count) * 100.0
                        / NULLIF(SUM(ram.receipt_count), 0),
                        1
                    )                                                            AS pct_bon2acc,
                    ROUND(
                        SUM(ram.focus_quantity) * 100.0
                        / NULLIF(SUM(ram.total_quantity), 0),
                        1
                    )                                                            AS pct_focus
                FROM reporting_agent_month ram
                JOIN stores s ON s.site_code = ram.site_code
                LEFT JOIN asm_targets at ON at.asm = s.asm
                WHERE ram.import_month = $1
                  AND ($2::text IS NULL OR s.regional = $2)
                GROUP BY s.asm, s.regional, at.total_target
                ORDER BY total_sales DESC
                """,
                month,
                regional,
            )

    async def get_visits_snapshot(self, month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM visits_snapshot WHERE month = $1", month
            )

    async def get_asm_history_rows(self, asm_name: str, months: int) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH asm_month_targets AS (
                    SELECT st.import_month, SUM(st.target_value) AS total_target
                    FROM store_targets st
                    JOIN stores s ON s.site_code = st.site_code
                    WHERE s.asm = $1
                      AND st.import_month >= to_char(now() - ($2 || ' months')::interval, 'YYYY-MM')
                    GROUP BY st.import_month
                )
                SELECT
                    ram.import_month,
                    SUM(ram.total_sales)               AS total_sales,
                    COALESCE(amt.total_target, 0)      AS total_target,
                    COUNT(DISTINCT ram.site_code)       AS active_stores
                FROM reporting_agent_month ram
                JOIN stores s ON s.site_code = ram.site_code
                LEFT JOIN asm_month_targets amt ON amt.import_month = ram.import_month
                WHERE s.asm = $1
                  AND ram.import_month >= to_char(now() - ($2 || ' months')::interval, 'YYYY-MM')
                GROUP BY ram.import_month, amt.total_target
                ORDER BY ram.import_month
                """,
                asm_name,
                str(months),
            )

    async def get_visits_snapshot_history(self, asm_name: str, months: int) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT * FROM visits_snapshot
                WHERE asm = $1
                  AND month >= to_char(now() - ($2 || ' months')::interval, 'YYYY-MM')
                ORDER BY month
                """,
                asm_name,
                str(months),
            )

    async def get_current_month_meta(self) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT
                    COALESCE(BOOL_OR(snap.is_month_final), true) AS is_final,
                    EXTRACT(DAY FROM MAX(rid.sale_date))::INT AS last_sale_day,
                    EXTRACT(DAY FROM (
                        date_trunc('month', now()) + INTERVAL '1 month - 1 day'
                    ))::INT AS days_in_month
                FROM import_snapshots snap
                LEFT JOIN (
                    SELECT MAX(sale_date) AS sale_date
                    FROM reporting_item_day
                    WHERE import_month = to_char(now(), 'YYYY-MM')
                ) rid ON true
                WHERE snap.import_month = to_char(now(), 'YYYY-MM')
                """,
            )
