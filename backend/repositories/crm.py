from __future__ import annotations

import json

import asyncpg


class CrmRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_kpi_data_for_month(
        self,
        month: str,
        prev_month: str,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> list[asyncpg.Record]:
        """Read the CRM KPI source rows for ``month``.

        When ``connection`` is supplied, the read uses that connection
        (this is the lock-aware path used by ``CrmService.recalculate_scores``
        so the per-month advisory lock covers the entire
        calculate-then-replace cycle). Otherwise a fresh pool connection
        is acquired for the read.
        """
        sql = """
            WITH current AS (
                SELECT
                    ram.site_code,
                    SUM(ram.total_sales) AS total_value,
                    ROUND(SUM(ram.receipt_2plus_count) * 100.0 / NULLIF(SUM(ram.receipt_count), 0), 2) AS pct_bon2acc,
                    ROUND(SUM(ram.focus_quantity) * 100.0 / NULLIF(SUM(ram.total_quantity), 0), 2) AS pct_focus,
                    COALESCE(
                        (SELECT SUM(st.target_value)
                         FROM store_targets st
                         WHERE st.site_code = ram.site_code
                           AND st.import_month = $1),
                        0
                    ) AS target_value
                FROM reporting_agent_month ram
                WHERE ram.import_month = $1
                GROUP BY ram.site_code
            ),
            prev AS (
                SELECT
                    site_code,
                    SUM(total_sales) AS total_value
                FROM reporting_agent_month
                WHERE import_month = $2
                GROUP BY site_code
            ),
            kpi_avgs AS (
                SELECT
                    ROUND(SUM(receipt_2plus_count) * 100.0 / NULLIF(SUM(receipt_count), 0), 2) AS avg_bon2acc,
                    ROUND(SUM(focus_quantity) * 100.0 / NULLIF(SUM(total_quantity), 0), 2) AS avg_focus
                FROM reporting_agent_month
                WHERE import_month = $1
            )
            SELECT
                c.site_code,
                c.total_value,
                c.pct_bon2acc,
                c.pct_focus,
                c.target_value,
                COALESCE(p.total_value, 0) AS prev_value,
                k.avg_bon2acc,
                k.avg_focus
            FROM current c
            LEFT JOIN prev p ON p.site_code = c.site_code
            CROSS JOIN kpi_avgs k
        """
        if connection is not None:
            return await connection.fetch(sql, month, prev_month)
        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, month, prev_month)

    async def replace_month_scores(
        self,
        month: str,
        scores: list[dict],
        *,
        connection: asyncpg.Connection,
    ) -> None:
        """Atomically replace every ``store_scores`` row for ``month``.

        This is the destructive primitive. It MUST be called inside a
        transaction that already holds the per-month advisory lock
        acquired by ``CrmService.recalculate_scores`` (or an equivalent
        locked-cycle owner). The lock guarantees that no concurrent
        calculation is in flight for the same month.

        The ``scores`` argument MUST be a non-empty validated projection.
        An empty list is a programming error and raises ``ValueError``
        before any DELETE runs. This fail-closed behaviour prevents a
        future caller from bypassing the service-level
        ``CrmSourceDataUnavailable`` check and silently wiping the
        month — which is exactly the AGENTS invariant the previous
        candidate violated.

        After a successful call, ``store_scores`` for the given month
        holds exactly the rows described by ``scores`` (no stale rows,
        no partial replacement, no touch on other months). The DELETE
        and INSERT run as one transactional unit on the supplied
        connection.
        """
        if not scores:
            raise ValueError(
                "CrmRepository.replace_month_scores requires a non-empty "
                "score list; the service must reject empty-source "
                "recalculation via CrmSourceDataUnavailable before "
                "invoking this primitive."
            )
        if connection is None:
            raise TypeError(
                "CrmRepository.replace_month_scores requires an explicit "
                "transactional connection so the per-month advisory lock "
                "covers the calculate-then-replace cycle."
            )
        await connection.execute(
            "DELETE FROM store_scores WHERE score_month = $1",
            month,
        )
        await connection.executemany(
            """
            INSERT INTO store_scores (
                site_code, score_month, score, breakdown
            ) VALUES ($1, $2, $3, $4::jsonb)
            """,
            [
                (
                    s["site_code"],
                    month,
                    s["score"],
                    json.dumps(s["breakdown"]),
                )
                for s in scores
            ],
        )

    async def get_alerts_data(self, month: str, prev_month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH current AS (
                    SELECT site_code, SUM(total_sales) AS val
                    FROM reporting_agent_month WHERE import_month = $1
                    GROUP BY site_code
                ),
                prev AS (
                    SELECT site_code, SUM(total_sales) AS val
                    FROM reporting_agent_month
                    WHERE import_month = $2
                    GROUP BY site_code
                ),
                scores AS (
                    SELECT site_code, score
                    FROM store_scores
                    WHERE score_month = $1
                )
                SELECT
                    c.site_code,
                    COALESCE(s.score, -1) AS score,
                    c.val AS current_val,
                    COALESCE(p.val, 0) AS prev_val,
                    COALESCE(st.regional, 'Necunoscut') AS regional,
                    COALESCE(st.asm, 'Necunoscut') AS asm,
                    COALESCE(st.locatie, c.site_code) AS locatie
                FROM current c
                LEFT JOIN prev p ON p.site_code = c.site_code
                LEFT JOIN scores s ON s.site_code = c.site_code
                LEFT JOIN stores st ON st.site_code = c.site_code
                """,
                month,
                prev_month,
            )

    async def get_scores(self, month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT ss.site_code, ss.score, ss.breakdown, ss.calculated_at::text,
                       COALESCE(s.regional, 'Necunoscut') AS regional,
                       COALESCE(s.asm, 'Necunoscut') AS asm,
                       COALESCE(s.locatie, ss.site_code) AS locatie
                FROM store_scores ss
                LEFT JOIN stores s ON s.site_code = ss.site_code
                WHERE ss.score_month = $1
                ORDER BY s.regional NULLS LAST, s.asm NULLS LAST, ss.score ASC
                """,
                month,
            )
