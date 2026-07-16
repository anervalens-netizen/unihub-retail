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

    async def get_manager_overview_rows(self, month: str) -> list[asyncpg.Record]:
        """Returnează sumarul de structură și flux al echipei pentru fiecare manager.

        Portofoliul pornește din magazinele active curente, nu din magazinele
        care au deja vânzări în luna cerută. Agenții sunt deduplicați la nivel
        de manager, iar intrările/ieșirile compară aceeași structură curentă cu
        luna precedentă.
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH active_stores AS (
                    SELECT DISTINCT
                        site_code,
                        locatie,
                        firma,
                        regional,
                        asm
                    FROM stores
                    WHERE is_active = TRUE
                      AND locatie NOT ILIKE 'TR %'
                      AND NULLIF(BTRIM(asm), '') IS NOT NULL
                ),
                current_agents AS (
                    SELECT DISTINCT s.asm, ram.agent
                    FROM active_stores s
                    JOIN reporting_agent_month ram ON ram.site_code = s.site_code
                    WHERE ram.import_month = $1
                      AND ram.agent IS NOT NULL
                      AND ram.agent <> '-'
                ),
                previous_agents AS (
                    SELECT DISTINCT s.asm, ram.agent
                    FROM active_stores s
                    JOIN reporting_agent_month ram ON ram.site_code = s.site_code
                    WHERE ram.import_month = to_char(($1 || '-01')::date - INTERVAL '1 month', 'YYYY-MM')
                      AND ram.agent IS NOT NULL
                      AND ram.agent <> '-'
                ),
                current_store_agents AS (
                    SELECT s.site_code, COUNT(DISTINCT ram.agent)::INT AS agent_count
                    FROM active_stores s
                    LEFT JOIN reporting_agent_month ram
                      ON ram.site_code = s.site_code
                     AND ram.import_month = $1
                     AND ram.agent IS NOT NULL
                     AND ram.agent <> '-'
                    GROUP BY s.site_code
                )
                SELECT
                    s.asm,
                    MIN(s.regional) AS regional,
                    EXISTS (
                        SELECT 1 FROM reporting_agent_month ram
                        WHERE ram.import_month = $1
                    ) AS reporting_available,
                    COUNT(DISTINCT s.site_code)::INT AS active_stores,
                    (SELECT COUNT(*)::INT FROM current_agents ca WHERE ca.asm = s.asm) AS active_agents,
                    (SELECT COUNT(*)::INT FROM previous_agents pa WHERE pa.asm = s.asm) AS previous_active_agents,
                    (
                        SELECT COUNT(*)::INT
                        FROM current_agents ca
                        WHERE ca.asm = s.asm
                          AND NOT EXISTS (
                              SELECT 1 FROM previous_agents pa
                              WHERE pa.asm = ca.asm AND pa.agent = ca.agent
                          )
                    ) AS agents_added,
                    (
                        SELECT COUNT(*)::INT
                        FROM previous_agents pa
                        WHERE pa.asm = s.asm
                          AND NOT EXISTS (
                              SELECT 1 FROM current_agents ca
                              WHERE ca.asm = pa.asm AND ca.agent = pa.agent
                          )
                    ) AS agents_left,
                    COUNT(*) FILTER (WHERE COALESCE(csa.agent_count, 0) = 0)::INT AS stores_without_agents
                FROM active_stores s
                LEFT JOIN current_store_agents csa ON csa.site_code = s.site_code
                GROUP BY s.asm
                ORDER BY s.asm
                """,
                month,
            )

    async def get_manager_store_overview_rows(self, month: str) -> list[asyncpg.Record]:
        """Returnează acoperirea cu agenți per magazin pentru overview-ul Manageri."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH active_stores AS (
                    SELECT DISTINCT
                        site_code,
                        locatie,
                        firma,
                        regional,
                        asm
                    FROM stores
                    WHERE is_active = TRUE
                      AND locatie NOT ILIKE 'TR %'
                      AND NULLIF(BTRIM(asm), '') IS NOT NULL
                ),
                current_agents AS (
                    SELECT
                        s.site_code,
                        COUNT(DISTINCT ram.agent)::INT AS agent_count
                    FROM active_stores s
                    LEFT JOIN reporting_agent_month ram
                      ON ram.site_code = s.site_code
                     AND ram.import_month = $1
                     AND ram.agent IS NOT NULL
                     AND ram.agent <> '-'
                    GROUP BY s.site_code
                ),
                previous_agents AS (
                    SELECT
                        s.site_code,
                        COUNT(DISTINCT ram.agent)::INT AS agent_count
                    FROM active_stores s
                    LEFT JOIN reporting_agent_month ram
                      ON ram.site_code = s.site_code
                     AND ram.import_month = to_char(($1 || '-01')::date - INTERVAL '1 month', 'YYYY-MM')
                     AND ram.agent IS NOT NULL
                     AND ram.agent <> '-'
                    GROUP BY s.site_code
                )
                SELECT
                    s.asm,
                    s.site_code,
                    s.locatie,
                    s.firma,
                    COALESCE(ca.agent_count, 0)::INT AS active_agents,
                    COALESCE(pa.agent_count, 0)::INT AS previous_active_agents
                FROM active_stores s
                LEFT JOIN current_agents ca ON ca.site_code = s.site_code
                LEFT JOIN previous_agents pa ON pa.site_code = s.site_code
                ORDER BY
                    s.asm,
                    (COALESCE(ca.agent_count, 0) = 0) DESC,
                    (COALESCE(ca.agent_count, 0) - COALESCE(pa.agent_count, 0)) ASC,
                    s.locatie,
                    s.firma
                """,
                month,
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

    async def get_asm_store_breakdown(self, asm_name: str, month: str) -> list[asyncpg.Record]:
        """Date pe magazin (insulă) pentru un ASM și o lună, pentru grila salarială.

        Agregă `reporting_agent_month` per site_code (un magazin poate avea
        mai mulți agenți). Include magazinele din zona ASM-ului care au target
        sau vânzări în luna cerută; magazinele fără target și fără vânzări
        (ex. închise) sunt excluse. `stores.asm` reflectă apartenența curentă,
        consistent cu `get_asm_performance_rows` și istoricul ASM.
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH store_sales AS (
                    SELECT
                        ram.site_code,
                        COALESCE(SUM(ram.total_sales), 0)    AS total_sales,
                        COALESCE(SUM(ram.focus_quantity), 0) AS focus_quantity,
                        COALESCE(SUM(ram.total_quantity), 0) AS total_quantity
                    FROM reporting_agent_month ram
                    WHERE ram.import_month = $1
                    GROUP BY ram.site_code
                )
                SELECT
                    s.site_code,
                    s.locatie,
                    s.firma,
                    COALESCE(st.target_value, 0)   AS target_value,
                    COALESCE(ss.total_sales, 0)    AS total_sales,
                    COALESCE(ss.focus_quantity, 0) AS focus_quantity,
                    COALESCE(ss.total_quantity, 0) AS total_quantity
                FROM stores s
                LEFT JOIN store_targets st
                  ON st.site_code = s.site_code AND st.import_month = $1
                LEFT JOIN store_sales ss
                  ON ss.site_code = s.site_code
                WHERE s.asm = $2
                  AND (st.site_code IS NOT NULL OR ss.site_code IS NOT NULL)
                ORDER BY s.locatie, s.firma
                """,
                month,
                asm_name,
            )
