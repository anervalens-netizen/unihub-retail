"""Repository-level tests for salary reporting invariants."""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from db.connection import get_pool
from repositories.salarii import SalariiRepository


TEST_SITE = "TSTSAL"
TEST_REGION = "Salary Test Region"
TEST_ASM = "Salary Test ASM"
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
            INSERT INTO salary_records (
                year, month, full_name, cnp, total_salary, company_name, site_code, locatie
            )
            VALUES ($1, $2, $3, $4, $5, 'Mobicell', $6, 'Salary Test Store')
            """,
            [
                (2098, 1, "Low Salary Agent", "synthetic-private-id-a", Decimal("1500"), TEST_SITE),
                (2098, 1, "High Salary Agent", "synthetic-private-id-b", Decimal("3000"), TEST_SITE),
                (2098, 2, "High Salary Agent", "synthetic-private-id-b", Decimal("4000"), TEST_SITE),
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
