"""Sync visits aggregates from SQLite into the visits_snapshot PG table.

Sursa de adevăr rămâne SQLite. PG-ul e o proiecție cacheată pentru queries
async native în hr.py, fără run_in_executor per request.

Apelat:
  - La boot în lifespan (main.py), după apply_pending_migrations
  - La POST /api/admin/sync-visits-snapshot pentru refresh manual
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_VISITS_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "visits" / "visits.db"


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


async def sync_visits_snapshot(
    conn: Any,
    sqlite_path: Path | None = None,
) -> int:
    """Upsert vizite agregate din SQLite în visits_snapshot PG.

    Returns:
        Numărul de rânduri inserate/actualizate.
    """
    path = sqlite_path or _VISITS_DB_PATH
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(None, _read_sqlite_aggregates, path)

    if not rows:
        return 0

    await conn.executemany(
        """
        INSERT INTO visits_snapshot
            (asm, month, total_visits, avg_completion, avg_duration,
             distinct_stores, checklist_score, approved_pct, synced_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
        ON CONFLICT (asm, month) DO UPDATE SET
            total_visits    = EXCLUDED.total_visits,
            avg_completion  = EXCLUDED.avg_completion,
            avg_duration    = EXCLUDED.avg_duration,
            distinct_stores = EXCLUDED.distinct_stores,
            checklist_score = EXCLUDED.checklist_score,
            approved_pct    = EXCLUDED.approved_pct,
            synced_at       = now()
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
