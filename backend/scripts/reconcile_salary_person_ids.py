"""Read-only aggregate reconciliation for the H-01A salary identity boundary."""
from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

async def reconcile() -> dict[str, int]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    temporary_key = secrets.token_urlsafe(48)
    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            row = await conn.fetchrow(
                """
                WITH identities AS (
                    SELECT
                        COALESCE(NULLIF(BTRIM(cnp), ''), 'name:' || LOWER(BTRIM(COALESCE(full_name, '')))) AS canonical,
                        'sp1_' || encode(hmac((COALESCE(NULLIF(BTRIM(cnp), ''), 'name:' || LOWER(BTRIM(COALESCE(full_name, ''))))::text), $1::text, 'sha256'), 'hex') AS person_id,
                        NULLIF(BTRIM(cnp), '') IS NULL AS name_fallback
                    FROM salary_records
                ),
                distinct_identities AS (
                    SELECT DISTINCT canonical, person_id, name_fallback
                    FROM identities
                ),
                sampled AS (
                    SELECT canonical, person_id
                    FROM distinct_identities
                    ORDER BY md5(canonical)
                    LIMIT 100
                ),
                history_check AS (
                    SELECT
                        sampled.canonical,
                        (SELECT COUNT(*) FROM salary_records sr
                         WHERE COALESCE(NULLIF(BTRIM(sr.cnp), ''), 'name:' || LOWER(BTRIM(COALESCE(sr.full_name, '')))) = sampled.canonical
                        ) AS legacy_count,
                        (SELECT COUNT(*) FROM salary_records sr2
                         WHERE 'sp1_' || encode(hmac((COALESCE(NULLIF(BTRIM(sr2.cnp), ''), 'name:' || LOWER(BTRIM(COALESCE(sr2.full_name, ''))))::text), $1::text, 'sha256'), 'hex') = sampled.person_id
                        ) AS opaque_count
                    FROM sampled
                )
                SELECT
                    (SELECT COUNT(*) FROM distinct_identities) AS canonical_identity_count,
                    (SELECT COUNT(DISTINCT person_id) FROM distinct_identities) AS generated_person_id_count,
                    (SELECT COUNT(*) FROM (
                        SELECT canonical
                        FROM distinct_identities
                        GROUP BY canonical
                        HAVING COUNT(DISTINCT person_id) > 1
                    ) collisions) AS collision_count,
                    (SELECT COUNT(*) FROM distinct_identities WHERE name_fallback) AS name_fallback_identity_count,
                    (SELECT COUNT(*) FROM (
                        SELECT BTRIM(cnp)
                        FROM salary_records
                        WHERE NULLIF(BTRIM(cnp), '') IS NOT NULL
                        GROUP BY BTRIM(cnp)
                        HAVING COUNT(*) > 1
                    ) duplicate_private) AS duplicate_nonempty_private_id_group_count,
                    (SELECT COUNT(*) FROM (
                        SELECT LOWER(BTRIM(full_name))
                        FROM salary_records
                        WHERE NULLIF(BTRIM(cnp), '') IS NULL
                        GROUP BY LOWER(BTRIM(full_name))
                        HAVING COUNT(*) > 1
                    ) duplicate_fallback) AS duplicate_normalized_name_fallback_group_count,
                    (SELECT COUNT(*) FROM sampled) AS sampled_history_identity_count,
                    (SELECT COUNT(*) FROM history_check WHERE legacy_count <> opaque_count) AS sampled_history_mismatch_count
                """,
                temporary_key,
            )
            return {key: int(row[key]) for key in row.keys()}
    finally:
        await conn.close()


def main() -> int:
    result = asyncio.run(reconcile())
    for key, value in result.items():
        print(f"{key}={value}")
    if result["generated_person_id_count"] != result["canonical_identity_count"]:
        return 1
    if result["collision_count"] != 0 or result["sampled_history_mismatch_count"] != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
