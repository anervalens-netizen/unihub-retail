#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from salary_identity import get_salary_person_id_key, salary_person_id_sql


BACKFILL_LOCK_ID = 7_221_901_202_607_13


async def backfill(connection: asyncpg.Connection, key: str) -> dict[str, int]:
    salary_person_id = salary_person_id_sql("sr", "$1")
    link_person_id = salary_person_id_sql("identity", "$1")
    await connection.execute("SELECT pg_advisory_xact_lock($1)", BACKFILL_LOCK_ID)
    await connection.execute(
        f"""
        INSERT INTO salary_private.people (
            person_id, cnp, normalized_name, identity_source
        )
        SELECT DISTINCT ON (person_id)
            person_id,
            cnp,
            normalized_name,
            identity_source
        FROM (
            SELECT
                {salary_person_id} AS person_id,
                NULLIF(BTRIM(sr.cnp), '') AS cnp,
                LOWER(BTRIM(sr.full_name)) AS normalized_name,
                CASE WHEN NULLIF(BTRIM(sr.cnp), '') IS NOT NULL THEN 'cnp' ELSE 'name' END AS identity_source
            FROM salary_records sr
            WHERE NULLIF(BTRIM(sr.cnp), '') IS NOT NULL
               OR NULLIF(BTRIM(sr.full_name), '') IS NOT NULL
        ) identities
        ORDER BY person_id, normalized_name
        ON CONFLICT (person_id) DO NOTHING
        """,
        key,
    )
    await connection.execute(
        f"""
        WITH link_identities AS (
            SELECT
                agent_code,
                site_code,
                salary_cnp AS cnp,
                salary_full_name AS full_name
            FROM agent_salary_links
            WHERE match_status = 'confirmed'
              AND (
                  NULLIF(BTRIM(salary_cnp), '') IS NOT NULL
                  OR NULLIF(BTRIM(salary_full_name), '') IS NOT NULL
              )
        )
        INSERT INTO salary_private.people (
            person_id, cnp, normalized_name, identity_source
        )
        SELECT DISTINCT ON (person_id)
            person_id,
            cnp,
            normalized_name,
            identity_source
        FROM (
            SELECT
                {link_person_id} AS person_id,
                NULLIF(BTRIM(identity.cnp), '') AS cnp,
                LOWER(BTRIM(identity.full_name)) AS normalized_name,
                CASE WHEN NULLIF(BTRIM(identity.cnp), '') IS NOT NULL THEN 'cnp' ELSE 'name' END AS identity_source
            FROM link_identities identity
        ) identities
        ORDER BY person_id, normalized_name
        ON CONFLICT (person_id) DO NOTHING
        """,
        key,
    )
    await connection.execute(
        f"""
        UPDATE salary_records sr
        SET person_id = {salary_person_id}
        WHERE sr.person_id IS DISTINCT FROM {salary_person_id}
        """,
        key,
    )
    await connection.execute(
        f"""
        WITH link_identity AS (
            SELECT
                agent_code,
                site_code,
                salary_cnp AS cnp,
                salary_full_name AS full_name
            FROM agent_salary_links
            WHERE match_status = 'confirmed'
              AND (
                  NULLIF(BTRIM(salary_cnp), '') IS NOT NULL
                  OR NULLIF(BTRIM(salary_full_name), '') IS NOT NULL
              )
        )
        UPDATE agent_salary_links links
        SET person_id = {link_person_id}
        FROM link_identity identity
        WHERE links.agent_code = identity.agent_code
          AND links.site_code = identity.site_code
          AND links.person_id IS DISTINCT FROM {link_person_id}
        """,
        key,
    )
    stats = await connection.fetchrow(
        """
        SELECT
            (SELECT COUNT(*) FROM salary_private.people) AS people,
            (SELECT COUNT(*) FROM salary_records) AS records,
            (SELECT COUNT(*) FROM salary_records WHERE person_id IS NULL) AS records_missing,
            (SELECT COUNT(*) FROM agent_salary_links WHERE match_status = 'confirmed') AS confirmed_links,
            (SELECT COUNT(*) FROM agent_salary_links WHERE match_status = 'confirmed' AND person_id IS NULL) AS links_missing,
            (
                SELECT COUNT(*)
                FROM agent_salary_links
                WHERE match_status = 'confirmed'
                  AND NULLIF(BTRIM(COALESCE(salary_cnp, '')), '') IS NULL
                  AND NULLIF(BTRIM(COALESCE(salary_full_name, '')), '') IS NULL
            ) AS blank_confirmed_links,
            (
                SELECT COUNT(*) FROM (
                    SELECT person_id
                    FROM salary_records
                    GROUP BY person_id
                    HAVING COUNT(DISTINCT COALESCE(NULLIF(BTRIM(cnp), ''), 'name:' || LOWER(BTRIM(full_name)))) > 1
                ) collisions
            ) AS collisions
        """
    )
    result = {name: int(stats[name]) for name in stats.keys()}
    if result["blank_confirmed_links"]:
        raise RuntimeError("Salary identity backfill found blank confirmed identities")
    if result["records_missing"] or result["links_missing"] or result["collisions"]:
        raise RuntimeError("Salary identity backfill validation failed")
    return result


async def main() -> None:
    database_url = os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Migration database URL is not configured")
    key = get_salary_person_id_key()
    connection = await asyncpg.connect(
        database_url,
        command_timeout=120,
        server_settings={"application_name": "unihub-retail-salary-identity-backfill"},
    )
    try:
        async with connection.transaction():
            result = await backfill(connection, key)
    finally:
        await connection.close()
    print(
        "Salary identity backfill verified: "
        f"people={result['people']} records={result['records']} "
        f"confirmed_links={result['confirmed_links']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
