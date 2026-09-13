from __future__ import annotations

import json
import zlib

import asyncpg


# Fixed CRM namespace id used as the first advisory-lock key.
# Together with a stable per-month hash of the calendar month this
# guarantees: same-month recalculations serialize against one another,
# different-month recalculations do not block each other, and no other
# subsystem falls into the same key pair.
_CRM_LOCK_NAMESPACE = 7377


class CrmRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_kpi_data_for_month(self, month: str, prev_month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
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
                """,
                month,
                prev_month,
            )

    async def replace_month_scores(
        self, month: str, scores: list[dict]
    ) -> None:
        """Atomically replace every ``store_scores`` row for ``month``.

        After a successful call, ``store_scores`` for the given month
        holds exactly the rows described by ``scores`` (no stale rows,
        no partial replacement, no touch on other months).

        - The DELETE + INSERT pair runs inside one transaction.
        - A transaction-scoped advisory lock keyed by the CRM namespace
          and a stable per-month hash serializes same-month calls and
          leaves different-month calls independent.
        - A ``scores`` of length zero is honoured as "this month has no
          current projection" — only the DELETE runs and the transaction
          commits an empty projection for the month.
        """
        # zlib.crc32 is portable and deterministic across processes; we
        # mask to a positive 31-bit integer so the lock call fits the
        # PostgreSQL int4 argument range.
        month_lock_key = zlib.crc32(month.encode("utf-8")) & 0x7FFFFFFF
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Serialize same-month recalculations only. The lock is
                # transaction-scoped: it is released on COMMIT/ROLLBACK.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, $2)",
                    _CRM_LOCK_NAMESPACE, month_lock_key,
                )
                await conn.execute(
                    "DELETE FROM store_scores WHERE score_month = $1",
                    month,
                )
                if scores:
                    await conn.executemany(
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
