"""
Import script: reads salarii_simplu.db (SQLite) and populates PostgreSQL.

Usage:
    python -m scripts.import_salarii

Idempotent — uses ON CONFLICT DO UPDATE so re-runs are safe.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from db.connection import get_pool

SALARII_DB = Path(r"C:\Users\andre\Desktop\Workspace\unihub\salarii_simplu.db")


async def run_import() -> None:
    print(f"Starting import from {SALARII_DB}")
    if not SALARII_DB.exists():
        print(f"ERROR: salarii_simplu.db not found at {SALARII_DB}")
        return

    con = sqlite3.connect(SALARII_DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute("SELECT * FROM salary_records").fetchall()
    con.close()

    pool = await get_pool()
    async with pool.acquire() as conn:
        inserted = 0
        updated = 0
        errors = 0
        for row in rows:
            try:
                was_insert = await conn.fetchval(
                    """
                    INSERT INTO salary_records (
                        year, month, full_name, cnp, total_salary,
                        company_name, site_code, locatie
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (year, month, cnp, full_name, company_name)
                    DO UPDATE SET
                        total_salary = EXCLUDED.total_salary,
                        site_code = EXCLUDED.site_code,
                        locatie = EXCLUDED.locatie
                    RETURNING (xmax = 0)
                    """,
                    row["year"], row["month"], row["full_name"],
                    row["cnp"], row["total_salary"],
                    row["company_name"], row["site_code"], row["locatie"],
                )
                if was_insert:
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  Warning: failed to import row id={row['id']}: {e}")

    print(f"Import complete: {inserted} inserted, {updated} updated, {errors} errors.")


if __name__ == "__main__":
    asyncio.run(run_import())
