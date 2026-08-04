"""Repository-level tests for salary reporting invariants."""
from __future__ import annotations

import os
from decimal import Decimal
from uuid import UUID

import pytest

from db.connection import get_pool
from repositories.salarii import SalariiRepository
from salary_identity import make_salary_person_id
from services.salarii import SalariiService


TEST_SITE = "TSTSAL"
TEST_REGION = "Salary Test Region"
TEST_ASM = "Salary Test ASM"
PERSON_ID_KEY = "synthetic-hmac-key-for-tests-abcdefghijklmnopqrstuvwxyz"
LOW_PERSON_ID = make_salary_person_id("synthetic-private-id-a", "Low Salary Agent", PERSON_ID_KEY)
HIGH_PERSON_ID = make_salary_person_id("synthetic-private-id-b", "High Salary Agent", PERSON_ID_KEY)
PROVENANCE_PERSON_ID = "sp1_" + "d" * 64
PROVENANCE_SITE = "SALARYMULTI"
PROVENANCE_REGION = "Salary Components Region"
PROVENANCE_ASM = "Salary Components ASM"
PROVENANCE_YEAR = 2099
PROVENANCE_MONTH = 9
PROVENANCE_BATCH_ID = UUID("00000000-0000-0000-0000-000000000209")
PROVENANCE_SOURCE_SHA = "f" * 64
pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _reset_salary_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM reporting_agent_month WHERE site_code = $1", TEST_SITE)
        await conn.execute("DELETE FROM salary_records WHERE site_code = $1", TEST_SITE)
        await conn.execute("DELETE FROM stores WHERE site_code = $1", TEST_SITE)
        await conn.execute(
            "DELETE FROM salary_private.people WHERE person_id = ANY($1::text[])",
            [LOW_PERSON_ID, HIGH_PERSON_ID],
        )


async def _seed_salary_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO stores (site_code, locatie, firma, regional, asm, first_seen_month, last_seen_month)
            VALUES ($1, 'Salary Test Store', 'Mobicell', $2, $3, '2098-01', '2098-02')
            ON CONFLICT (site_code) DO UPDATE
            SET locatie = EXCLUDED.locatie,
                firma = EXCLUDED.firma,
                regional = EXCLUDED.regional,
                asm = EXCLUDED.asm,
                last_seen_month = EXCLUDED.last_seen_month
            """,
            TEST_SITE,
            TEST_REGION,
            TEST_ASM,
        )
        await conn.executemany(
            """
            INSERT INTO salary_private.people (
                person_id, cnp, normalized_name, identity_source
            ) VALUES ($1, $2, $3, 'cnp')
            """,
            [
                (LOW_PERSON_ID, "synthetic-private-id-a", "low salary agent"),
                (HIGH_PERSON_ID, "synthetic-private-id-b", "high salary agent"),
            ],
        )
        await conn.executemany(
            """
            INSERT INTO salary_records (
                year, month, full_name, cnp, total_salary, company_name, site_code, locatie,
                person_id
            )
            VALUES ($1, $2, $3, $4, $5, 'Mobicell', $6, 'Salary Test Store', $7)
            """,
            [
                (2098, 1, "Low Salary Agent", "synthetic-private-id-a", Decimal("1500"), TEST_SITE, LOW_PERSON_ID),
                (2098, 1, "High Salary Agent", "synthetic-private-id-b", Decimal("3000"), TEST_SITE, HIGH_PERSON_ID),
                (2098, 2, "High Salary Agent", "synthetic-private-id-b", Decimal("4000"), TEST_SITE, HIGH_PERSON_ID),
            ],
        )


@pytest.mark.anyio
async def test_overview_total_includes_low_salary_but_average_excludes_it() -> None:
    await _reset_salary_fixture()
    await _seed_salary_fixture()
    try:
        repo = SalariiRepository(await get_pool())
        data = await repo.fetch_overview(
            company_name=None,
            site_code=None,
            regional=TEST_REGION,
            asm=None,
        )

        assert data["total"] == 8500.0
        assert data["agent_month_count"] == 3
        assert data["avg_agent_month_count"] == 2
        assert data["avg_salary"] == 3500.0
    finally:
        await _reset_salary_fixture()


@pytest.mark.anyio
async def test_summary_total_includes_low_salary_but_average_excludes_it() -> None:
    await _reset_salary_fixture()
    await _seed_salary_fixture()
    try:
        repo = SalariiRepository(await get_pool())
        rows = await repo.fetch_summary_by_site(
            company_name=None,
            site_code=TEST_SITE,
            regional=None,
            asm=None,
            year=2098,
            month=1,
        )

        assert len(rows) == 1
        row = rows[0]
        assert float(row["total_salary"]) == 4500.0
        assert row["agent_count"] == 2
        assert row["avg_agent_count"] == 1
        assert float(row["avg_salary"]) == 3000.0
    finally:
        await _reset_salary_fixture()


async def _reset_provenance_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM agent_salary_links WHERE site_code = $1", PROVENANCE_SITE)
        await conn.execute("DELETE FROM reporting_agent_month WHERE site_code = $1", PROVENANCE_SITE)
        await conn.execute("DELETE FROM salary_records WHERE import_batch_id = $1", PROVENANCE_BATCH_ID)
        await conn.execute("DELETE FROM salary_import_batches WHERE batch_id = $1", PROVENANCE_BATCH_ID)
        await conn.execute("DELETE FROM salary_private.people WHERE person_id = $1", PROVENANCE_PERSON_ID)
        await conn.execute("DELETE FROM stores WHERE site_code = $1", PROVENANCE_SITE)


async def _seed_provenance_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO stores (
                site_code, locatie, firma, regional, asm, first_seen_month, last_seen_month
            ) VALUES ($1, 'Salary Components Store', 'Mobiup', $2, $3, '2099-09', '2099-09')
            """,
            PROVENANCE_SITE,
            PROVENANCE_REGION,
            PROVENANCE_ASM,
        )
        await conn.execute(
            """
            INSERT INTO salary_private.people (person_id, cnp, normalized_name, identity_source)
            VALUES ($1, NULL, 'salary components agent', 'name')
            """,
            PROVENANCE_PERSON_ID,
        )
        await conn.execute(
            """
            INSERT INTO salary_import_batches (
                batch_id, year, month, status, manifest, manifest_sha256, applied_by
            ) VALUES ($1, $2, $3, 'applied', '{}'::jsonb, $4, 'salary-component-test')
            """,
            PROVENANCE_BATCH_ID,
            PROVENANCE_YEAR,
            PROVENANCE_MONTH,
            PROVENANCE_SOURCE_SHA,
        )
        await conn.executemany(
            """
            INSERT INTO salary_records (
                year, month, full_name, cnp, person_id, total_salary, company_name,
                site_code, locatie, import_batch_id, source_file, source_sheet,
                source_row, source_sha256
            ) VALUES (
                $1, $2, 'Salary Components Agent', NULL, $3, $4, 'Mobiup',
                $5, 'Salary Components Store', $6, 'salary-components.xlsx', 'Salarii', $7, $8
            )
            """,
            [
                (
                    PROVENANCE_YEAR,
                    PROVENANCE_MONTH,
                    PROVENANCE_PERSON_ID,
                    Decimal("1500.00"),
                    PROVENANCE_SITE,
                    PROVENANCE_BATCH_ID,
                    10,
                    PROVENANCE_SOURCE_SHA,
                ),
                (
                    PROVENANCE_YEAR,
                    PROVENANCE_MONTH,
                    PROVENANCE_PERSON_ID,
                    Decimal("1500.00"),
                    PROVENANCE_SITE,
                    PROVENANCE_BATCH_ID,
                    11,
                    PROVENANCE_SOURCE_SHA,
                ),
            ],
        )
        await conn.execute(
            """
            INSERT INTO agent_salary_links (
                agent_code, site_code, salary_full_name, match_status, match_source,
                confidence, effective_from_month, person_id
            ) VALUES ($1, $2, 'Salary Components Agent', 'confirmed', 'manual', 'high', '2099-09', $3)
            """,
            "SALCOMP",
            PROVENANCE_SITE,
            PROVENANCE_PERSON_ID,
        )
        await conn.execute(
            """
            INSERT INTO reporting_agent_month (
                import_month, site_code, locatie, firma, regional, asm, agent, total_sales
            ) VALUES ('2099-09', $1, 'Salary Components Store', 'Mobiup', $2, $3, 'SALCOMP', 10000)
            """,
            PROVENANCE_SITE,
            PROVENANCE_REGION,
            PROVENANCE_ASM,
        )


@pytest.mark.anyio
async def test_salary_components_with_distinct_provenance_keep_all_read_surfaces_consistent() -> None:
    await _reset_provenance_fixture()
    await _seed_provenance_fixture()
    try:
        repo = SalariiRepository(await get_pool())
        scope = {
            "company_name": "Mobiup",
            "site_code": PROVENANCE_SITE,
            "regional": PROVENANCE_REGION,
            "asm": PROVENANCE_ASM,
        }

        overview = await repo.fetch_overview(**scope)
        assert overview["total"] == 3000.0
        assert overview["record_count"] == 2
        assert overview["agent_count"] == overview["agent_month_count"] == 1
        assert overview["avg_agent_month_count"] == 1
        assert overview["avg_salary"] == 3000.0

        evolution = await repo.fetch_evolution_main(**scope)
        assert len(evolution) == 1
        assert evolution[0]["total"] == Decimal("3000.00")
        assert evolution[0]["mobiup"] == Decimal("3000.00")
        single_company_evolution = await repo.fetch_evolution_single_company(**scope)
        assert single_company_evolution[0]["total"] == Decimal("3000.00")

        agents = await repo.fetch_agents_summary(
            q=None,
            year=PROVENANCE_YEAR,
            month=PROVENANCE_MONTH,
            limit=10,
            offset=0,
            **scope,
        )
        assert agents["total"] == 1
        assert agents["items"][0]["person_id"] == PROVENANCE_PERSON_ID
        assert agents["items"][0]["month_count"] == agents["items"][0]["avg_month_count"] == 1
        assert agents["items"][0]["total_salary"] == agents["items"][0]["avg_salary"] == Decimal("3000.00")

        person_history = await repo.fetch_agent_history_by_person_id(PROVENANCE_PERSON_ID)
        retail_code_history = await repo.fetch_agent_history_by_salary_link(person_id=PROVENANCE_PERSON_ID)
        assert [dict(row) for row in retail_code_history] == [dict(row) for row in person_history]
        assert len(person_history) == 1
        assert person_history[0]["total_salary"] == Decimal("3000.00")

        service = SalariiService(repo, PERSON_ID_KEY)
        person_response = await service.get_agent_history(PROVENANCE_PERSON_ID)
        retail_code_response = await service.get_agent_history_by_retail_code(
            agent_code="SALCOMP",
            site_code=PROVENANCE_SITE,
        )
        assert retail_code_response["link"]["person_id"] == PROVENANCE_PERSON_ID
        for key in ("records", "total", "avg", "month_count", "avg_month_count"):
            assert retail_code_response[key] == person_response[key]

        summary = await repo.fetch_summary_by_site(
            year=PROVENANCE_YEAR,
            month=PROVENANCE_MONTH,
            **scope,
        )
        assert len(summary) == 1
        assert summary[0]["total_salary"] == summary[0]["avg_salary"] == Decimal("3000.00")
        assert summary[0]["agent_count"] == summary[0]["avg_agent_count"] == 1
        assert summary[0]["total_sales"] == Decimal("10000.00")

        trend = await repo.fetch_trend(**scope)
        assert len(trend) == 1
        assert trend[0]["total_salary"] == trend[0]["avg_salary"] == Decimal("3000.00")
        assert trend[0]["agent_count"] == trend[0]["avg_agent_count"] == 1
        assert trend[0]["total_sales"] == Decimal("10000.00")

        records = await repo.fetch_records(
            company_name="Mobiup",
            year=PROVENANCE_YEAR,
            month=PROVENANCE_MONTH,
            site_code=PROVENANCE_SITE,
            limit=10,
            offset=0,
        )
        assert len(records) == 2
        assert len({record["id"] for record in records}) == 2
        assert sum(record["total_salary"] for record in records) == Decimal("3000.00")
    finally:
        await _reset_provenance_fixture()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "scope",
    [
        {"company_name": "Mobiup", "site_code": None, "regional": None, "asm": None},
        {"company_name": None, "site_code": PROVENANCE_SITE, "regional": None, "asm": None},
        {"company_name": None, "site_code": None, "regional": PROVENANCE_REGION, "asm": None},
        {"company_name": None, "site_code": None, "regional": None, "asm": PROVENANCE_ASM},
    ],
)
async def test_salary_component_scope_filters_do_not_multiply_rows(scope: dict[str, str | None]) -> None:
    await _reset_provenance_fixture()
    await _seed_provenance_fixture()
    try:
        overview = await SalariiRepository(await get_pool()).fetch_overview(**scope)
        assert overview["total"] == 3000.0
        assert overview["record_count"] == 2
        assert overview["agent_count"] == 1
    finally:
        await _reset_provenance_fixture()
