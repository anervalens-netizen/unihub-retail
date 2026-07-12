"""Isolated PostgreSQL coverage for the H-01A opaque salary identity queries."""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from db.connection import get_pool
from repositories.salarii import SalariiRepository
from salary_identity import make_salary_person_id
from services.salarii import SalariiService


TEST_SITE = "H01PERS"
TEST_REGION = "H01 Test Region"
PERSON_ID_KEY = "synthetic-hmac-key-for-tests-abcdefghijklmnopqrstuvwxyz"
PRIVATE_ID = "synthetic-private-id-a"
FALLBACK_NAME = "Fallback Salary Agent"
PRIVATE_PERSON_ID = make_salary_person_id(PRIVATE_ID, "Private Salary Agent", PERSON_ID_KEY)
FALLBACK_PERSON_ID = make_salary_person_id(None, FALLBACK_NAME, PERSON_ID_KEY)

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _reset_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM agent_salary_links WHERE site_code = $1", TEST_SITE)
        await conn.execute("DELETE FROM salary_records WHERE site_code = $1", TEST_SITE)
        await conn.execute("DELETE FROM stores WHERE site_code = $1", TEST_SITE)


async def _seed_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO stores (site_code, locatie, firma, regional, asm, first_seen_month, last_seen_month)
            VALUES ($1, 'H01 Privacy Test Store', 'Mobicell', $2, 'H01 Test ASM', '2097-01', '2097-02')
            """,
            TEST_SITE,
            TEST_REGION,
        )
        await conn.executemany(
            """
            INSERT INTO salary_records (
                year, month, full_name, cnp, total_salary, company_name, site_code, locatie
            ) VALUES ($1, $2, $3, $4, $5, 'Mobicell', $6, 'H01 Privacy Test Store')
            """,
            [
                (2097, 1, "Private Salary Agent", PRIVATE_ID, Decimal("3000"), TEST_SITE),
                (2097, 2, "Private Salary Agent", PRIVATE_ID, Decimal("3200"), TEST_SITE),
                (2097, 1, FALLBACK_NAME, None, Decimal("2800"), TEST_SITE),
            ],
        )
        await conn.executemany(
            """
            INSERT INTO agent_salary_links (
                agent_code, site_code, salary_full_name, salary_cnp, match_status,
                match_source, confidence, effective_from_month, note
            ) VALUES ($1, $2, $3, $4, $5, 'manual', $6, '2097-01', NULL)
            """,
            [
                ("H01CONF", TEST_SITE, "", PRIVATE_ID, "confirmed", "high"),
                ("H01UNKNOWN", TEST_SITE, None, None, "unknown", "unknown"),
            ],
        )


@pytest.mark.anyio
async def test_h01_repository_queries_return_opaque_ids_without_private_columns() -> None:
    await _reset_fixture()
    await _seed_fixture()
    try:
        repo = SalariiRepository(await get_pool())

        summary = await repo.fetch_agents_summary(
            q=None, company_name=None, site_code=TEST_SITE, regional=None, asm=None,
            year=None, month=None, limit=10, offset=0, person_id_key=PERSON_ID_KEY,
        )
        assert summary["total"] == 2
        assert {row["person_id"] for row in summary["items"]} == {PRIVATE_PERSON_ID, FALLBACK_PERSON_ID}
        assert all(set(row) == {
            "person_id", "full_name", "company_name", "locatie", "month_count",
            "avg_month_count", "total_salary", "avg_salary",
        } for row in summary["items"])
        assert all(not ({"cnp", "salary_cnp", "agent_key"} & set(row)) for row in summary["items"])
        assert sorted(row["month_count"] for row in summary["items"]) == [1, 2]
        assert sorted(float(row["total_salary"]) for row in summary["items"]) == [2800.0, 6200.0]

        paged = await repo.fetch_agents_summary(
            q=None, company_name=None, site_code=TEST_SITE, regional=None, asm=None,
            year=None, month=None, limit=1, offset=1, person_id_key=PERSON_ID_KEY,
        )
        assert paged["total"] == 2
        assert len(paged["items"]) == 1

        summary_private_id = next(
            row["person_id"] for row in summary["items"] if row["person_id"] == PRIVATE_PERSON_ID
        )
        history = await repo.fetch_agent_history_by_person_id(summary_private_id, PERSON_ID_KEY)
        assert {(row["year"], row["month"]) for row in history} == {(2097, 1), (2097, 2)}
        assert all(set(row.keys()) == {"year", "month", "company_name", "total_salary", "site_code", "locatie"} for row in history)
        assert {float(row["total_salary"]) for row in history} == {3000.0, 3200.0}
        assert await repo.fetch_agent_history_by_person_id(
            make_salary_person_id("unknown-private-id", "Unknown", PERSON_ID_KEY), PERSON_ID_KEY,
        ) == []

        records = await repo.fetch_records(
            company_name=None, year=2097, month=None, site_code=TEST_SITE,
            limit=10, offset=0, person_id_key=PERSON_ID_KEY,
        )
        assert {row["person_id"] for row in records} == {PRIVATE_PERSON_ID, FALLBACK_PERSON_ID}
        assert all("cnp" not in row.keys() for row in records)
    finally:
        await _reset_fixture()


@pytest.mark.anyio
async def test_h01_repository_links_round_trip_by_person_id_and_unknown_stays_private() -> None:
    await _reset_fixture()
    await _seed_fixture()
    try:
        repo = SalariiRepository(await get_pool())
        service = SalariiService(repo, PERSON_ID_KEY)

        confirmed = await repo.fetch_agent_salary_link(
            agent_code="H01CONF", site_code=TEST_SITE, person_id_key=PERSON_ID_KEY,
        )
        assert confirmed is not None
        assert confirmed["person_id"] == PRIVATE_PERSON_ID
        assert "salary_cnp" in confirmed

        round_trip = await service.get_agent_history_by_retail_code(
            agent_code="H01CONF", site_code=TEST_SITE,
        )
        assert round_trip["link"]["person_id"] == PRIVATE_PERSON_ID
        assert len(round_trip["records"]) == 2
        assert "salary_cnp" not in str(round_trip)

        unknown = await service.get_agent_history_by_retail_code(
            agent_code="H01UNKNOWN", site_code=TEST_SITE,
        )
        unknown_repository_link = await repo.fetch_agent_salary_link(
            agent_code="H01UNKNOWN", site_code=TEST_SITE, person_id_key=PERSON_ID_KEY,
        )
        assert unknown_repository_link is not None
        assert unknown_repository_link["person_id"] is None
        assert unknown["link"]["person_id"] is None
        assert unknown["records"] == []
    finally:
        await _reset_fixture()
