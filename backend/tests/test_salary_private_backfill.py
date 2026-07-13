"""Integration coverage for the retained salary identity boundary."""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from db.connection import get_pool
from salary_identity import make_salary_person_id
from scripts.backfill_salary_private_identities import backfill


TEST_SITE = "H01BACK"
TEST_KEY = "synthetic-hmac-key-for-tests-abcdefghijklmnopqrstuvwxyz"
TEST_PRIVATE_ID = "synthetic-private-backfill-id"
TEST_PERSON_ID = make_salary_person_id(TEST_PRIVATE_ID, "Backfill Agent", TEST_KEY)

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


class _BackfillConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, sql: str, *_args: object) -> str:
        self.statements.append(sql)
        return "OK"

    async def fetchrow(self, _sql: str) -> dict[str, int]:
        return {
            "people": 1,
            "records": 0,
            "records_missing": 0,
            "confirmed_links": 1,
            "links_missing": 0,
            "blank_confirmed_links": 0,
            "collisions": 0,
        }


@pytest.mark.anyio
async def test_backfill_materializes_link_only_private_identities() -> None:
    connection = _BackfillConnection()
    await backfill(connection, TEST_KEY)  # type: ignore[arg-type]
    private_inserts = [
        statement
        for statement in connection.statements
        if "INSERT INTO salary_private.people" in statement
    ]
    assert len(private_inserts) == 2
    assert "FROM salary_records" in private_inserts[0]
    assert "FROM agent_salary_links" in private_inserts[1]
    assert "match_status = 'confirmed'" in private_inserts[1]
    assert "person_id AS stored_person_id" in private_inserts[1]
    assert "COALESCE(identity.stored_person_id" in private_inserts[1]
    assert "NULLIF(BTRIM(salary_full_name), '') IS NOT NULL" in private_inserts[1]
    link_updates = [
        statement
        for statement in connection.statements
        if "UPDATE agent_salary_links links" in statement
    ]
    assert len(link_updates) == 1
    assert "person_id IS NULL" in link_updates[0]
    assert "NULLIF(BTRIM(salary_full_name), '') IS NOT NULL" in link_updates[0]


@pytest.mark.anyio
async def test_backfill_rejects_blank_confirmed_link_identity_explicitly() -> None:
    connection = _BackfillConnection()

    async def blank_stats(_sql: str) -> dict[str, int]:
        return {
            "people": 0,
            "records": 0,
            "records_missing": 0,
            "confirmed_links": 1,
            "links_missing": 1,
            "blank_confirmed_links": 1,
            "collisions": 0,
        }

    connection.fetchrow = blank_stats  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="blank confirmed identities"):
        await backfill(connection, TEST_KEY)  # type: ignore[arg-type]


async def _cleanup() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute("DELETE FROM agent_salary_links WHERE site_code = $1", TEST_SITE)
        await connection.execute("DELETE FROM salary_records WHERE site_code = $1", TEST_SITE)
        await connection.execute("DELETE FROM stores WHERE site_code = $1", TEST_SITE)
        await connection.execute(
            "DELETE FROM salary_private.people WHERE person_id = $1", TEST_PERSON_ID
        )


@pytest.mark.anyio
async def test_backfill_is_idempotent_and_persists_private_mapping() -> None:
    await _cleanup()
    pool = await get_pool()
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    first_seen_month, last_seen_month
                ) VALUES (
                    $1, 'H01 Backfill Store', 'Mobiup', 'H01 Region', 'H01 ASM',
                    '2096-01', '2096-02'
                )
                """,
                TEST_SITE,
            )
            await connection.executemany(
                """
                INSERT INTO salary_private.people (
                    person_id, cnp, normalized_name, identity_source
                ) VALUES ($1, $2, $3, 'cnp')
                """,
                [(TEST_PERSON_ID, TEST_PRIVATE_ID, "backfill agent")],
            )
            await connection.executemany(
                """
                INSERT INTO salary_records (
                    year, month, full_name, cnp, total_salary,
                    company_name, site_code, locatie, person_id
                ) VALUES ($1, $2, $3, $4, $5, 'Mobiup', $6, 'H01 Backfill Store', $7)
                """,
                [
                    (2096, 1, "Backfill Agent", TEST_PRIVATE_ID, Decimal("3000"), TEST_SITE, TEST_PERSON_ID),
                    (2096, 2, "Backfill Agent Renamed", TEST_PRIVATE_ID, Decimal("3200"), TEST_SITE, TEST_PERSON_ID),
                ],
            )
            await connection.execute(
                """
                INSERT INTO agent_salary_links (
                    agent_code, site_code, salary_full_name, salary_cnp,
                    match_status, match_source, confidence
                    , person_id
                ) VALUES ('H01BACK', $1, 'Backfill Agent', NULL, 'confirmed', 'manual', 'high', $2)
                """,
                TEST_SITE,
                TEST_PERSON_ID,
            )
            async with connection.transaction():
                first = await backfill(connection, TEST_KEY)
            async with connection.transaction():
                second = await backfill(connection, TEST_KEY)

            records = await connection.fetch(
                "SELECT DISTINCT person_id FROM salary_records WHERE site_code = $1",
                TEST_SITE,
            )
            link_id = await connection.fetchval(
                "SELECT person_id FROM agent_salary_links WHERE site_code = $1",
                TEST_SITE,
            )
            private_row = await connection.fetchrow(
                """
                SELECT person_id, cnp, identity_source
                FROM salary_private.people
                WHERE person_id = $1
                """,
                TEST_PERSON_ID,
            )

        assert first["records_missing"] == 0
        assert second["records_missing"] == 0
        assert [row["person_id"] for row in records] == [TEST_PERSON_ID]
        assert link_id == TEST_PERSON_ID
        assert dict(private_row) == {
            "person_id": TEST_PERSON_ID,
            "cnp": TEST_PRIVATE_ID,
            "identity_source": "cnp",
        }
    finally:
        await _cleanup()
