"""Sync FieldOps PostgreSQL aggregates into the Retail HR projection."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def _read_postgres_aggregates(conn: Any) -> list[dict[str, Any]]:
    records = await conn.fetch(
        """
        SELECT
            asm,
            to_char(data_raport, 'YYYY-MM') AS month,
            COUNT(*)::INT AS total_visits,
            ROUND(AVG(completion_pct)::NUMERIC, 1)::FLOAT AS avg_completion,
            ROUND(AVG(durata_vizita_ore)::NUMERIC, 2)::FLOAT AS avg_duration,
            COUNT(DISTINCT magazin)::INT AS distinct_stores,
            ROUND(AVG(
                (curatenie::INT + imagine::INT + uniforma::INT
                 + afise::INT + produse_promo::INT) * 20.0
            )::NUMERIC, 1)::FLOAT AS checklist_score,
            ROUND(
                COUNT(*) FILTER (WHERE status = 'approved') * 100.0 / COUNT(*),
                1
            )::FLOAT AS approved_pct
        FROM fieldops_visits
        WHERE asm IS NOT NULL AND asm <> ''
        GROUP BY asm, to_char(data_raport, 'YYYY-MM')
        ORDER BY asm, month
        """
    )
    return [dict(record) for record in records]


def _sorted_aggregates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (row.get("asm") or "", row.get("month") or ""))


async def sync_visits_snapshot(conn: Any) -> int:
    """Replace `visits_snapshot` from the PostgreSQL visit authority.

    Returns:
        Numărul de rânduri inserate/actualizate.
    """
    rows = _sorted_aggregates(await _read_postgres_aggregates(conn))

    async with conn.transaction():
        await conn.execute("DELETE FROM visits_snapshot")
        if rows:
            await conn.executemany(
                """
                INSERT INTO visits_snapshot
                    (asm, month, total_visits, avg_completion, avg_duration,
                     distinct_stores, checklist_score, approved_pct, synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
                """,
                [
                    (
                        r["asm"],
                        r["month"],
                        int(r["total_visits"] or 0),
                        r["avg_completion"],
                        r["avg_duration"],
                        int(r["distinct_stores"] or 0),
                        r["checklist_score"],
                        r["approved_pct"],
                    )
                    for r in rows
                ],
            )
    logger.info("visits_snapshot synced: %d rows", len(rows))
    return len(rows)
