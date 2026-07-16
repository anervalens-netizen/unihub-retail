"""Sync visit aggregates into the Retail HR projection.

Sursa este selectata prin flagul de cutover. `visits_snapshot` ramane o
proiectie cacheata pentru queries async native in hr.py.

Apelat:
  - La boot în lifespan (main.py), după verificarea read-only a migrations
  - La POST /api/admin/sync-visits-snapshot pentru refresh manual
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

from config import (
    get_visits_db_path,
    get_visits_read_source,
    visits_shadow_compare_enabled,
)
from services.visits_shadow import compare_visit_result, record_visit_shadow_error

logger = logging.getLogger(__name__)


def _read_sqlite_aggregates(sqlite_path: Path) -> list[dict[str, Any]]:
    """Execuție sincronă — rulată din run_in_executor o singură dată la boot."""
    if not sqlite_path.exists():
        logger.warning("visits.db not found at %s — snapshot skipped", sqlite_path)
        return []

    con = sqlite3.connect(sqlite_path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(
            """
            SELECT
                asm,
                substr(data_raport, 1, 7)                                          AS month,
                COUNT(*)                                                            AS total_visits,
                ROUND(AVG(completion_pct), 1)                                      AS avg_completion,
                ROUND(AVG(durata_vizita_ore), 2)                                   AS avg_duration,
                COUNT(DISTINCT magazin)                                             AS distinct_stores,
                ROUND(AVG(
                    (COALESCE(curatenie, 0) + COALESCE(imagine, 0)
                     + COALESCE(uniforma, 0) + COALESCE(afise, 0)
                     + COALESCE(produse_promo, 0)) * 20.0
                ), 1)                                                               AS checklist_score,
                ROUND(
                    SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
                    1
                )                                                                   AS approved_pct
            FROM visits
            WHERE asm IS NOT NULL AND asm != ''
            GROUP BY asm, substr(data_raport, 1, 7)
            """
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


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


async def sync_visits_snapshot(
    conn: Any,
    sqlite_path: Path | None = None,
) -> int:
    """Replace `visits_snapshot` from the configured visit authority.

    Returns:
        Numărul de rânduri inserate/actualizate.
    """
    path = sqlite_path or get_visits_db_path()

    async def sqlite_reader() -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _read_sqlite_aggregates, path)

    async def postgres_reader() -> list[dict[str, Any]]:
        return await _read_postgres_aggregates(conn)

    source = get_visits_read_source()
    primary_reader = postgres_reader if source == "postgres" else sqlite_reader
    shadow_reader = sqlite_reader if source == "postgres" else postgres_reader
    rows = _sorted_aggregates(await primary_reader())
    if visits_shadow_compare_enabled():
        try:
            shadow_rows = _sorted_aggregates(await shadow_reader())
            compare_visit_result("snapshot", rows, shadow_rows)
        except Exception:
            record_visit_shadow_error("snapshot")

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
