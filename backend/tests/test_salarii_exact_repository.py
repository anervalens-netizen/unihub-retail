from __future__ import annotations

import os
from decimal import Decimal

import pytest

from db.connection import close_db_pool, get_pool
from repositories.salarii_exact import SalariiExactRepository


PERSON_ID = "sp1_" + "d" * 64
SITE_CODE = "SALARYEXACT"
YEAR = 2099
MONTH = 9


async def cleanup(conn) -> None:
    await conn.execute(
        "DELETE FROM salary_records WHERE person_id = $1 AND year = $2 AND month = $3",
        PERSON_ID,
        YEAR,
        MONTH,
    )
    await conn.execute(
        "DELETE FROM salary_private.people WHERE person_id = $1",
        PERSON_ID,
    )
    await conn.execute(
        "DELETE FROM stores WHERE site_code = $1",
        SITE_CODE,
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_identical_salary_components_are_not_deduplicated() -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await cleanup(conn)
            await conn.execute(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    first_seen_month, last_seen_month, is_active
                ) VALUES (
                    $1, 'Salary Exact Store', 'Mobiup', 'Test Regional',
                    'Test ASM', '2099-09', '2099-09', TRUE
                )
                """,
                SITE_CODE,
            )
            await conn.execute(
                """
                INSERT INTO salary_private.people (
                    person_id, cnp, normalized_name, identity_source
                ) VALUES ($1, NULL, 'agent exact', 'name')
                """,
                PERSON_ID,
            )
            await conn.executemany(
                """
                INSERT INTO salary_records (
                    year, month, full_name, cnp, person_id, total_salary,
                    company_name, site_code, locatie
                ) VALUES ($1, $2, 'Agent Exact', NULL, $3, $4, 'Mobiup', $5, 'Salary Exact Store')
                """,
                [
                    (YEAR, MONTH, PERSON_ID, Decimal("1500.00"), SITE_CODE),
                    (YEAR, MONTH, PERSON_ID, Decimal("1500.00"), SITE_CODE),
                ],
            )

            repo = SalariiExactRepository(pool)
            overview = await repo.fetch_overview(
                company_name="Mobiup",
                site_code=SITE_CODE,
                regional=None,
                asm=None,
            )
            assert overview["total"] == 3000.0
            assert overview["record_count"] == 2
            assert overview["agent_count"] == 1
            assert overview["avg_salary"] == 3000.0

            evolution = await repo.fetch_evolution_single_company(
                company_name="Mobiup",
                site_code=SITE_CODE,
                regional=None,
                asm=None,
            )
            assert len(evolution) == 1
            assert evolution[0]["total"] == Decimal("3000.00")

            history = await repo.fetch_agent_history_by_person_id(PERSON_ID)
            assert len(history) == 1
            assert history[0]["total_salary"] == Decimal("3000.00")

            summary = await repo.fetch_summary_by_site(
                company_name="Mobiup",
                site_code=SITE_CODE,
                regional=None,
                asm=None,
                year=YEAR,
                month=MONTH,
            )
            assert len(summary) == 1
            assert summary[0]["total_salary"] == Decimal("3000.00")
            assert summary[0]["agent_count"] == 1

            trend = await repo.fetch_trend(
                company_name="Mobiup",
                site_code=SITE_CODE,
                regional=None,
                asm=None,
            )
            row = next(item for item in trend if item["year"] == YEAR and item["month"] == MONTH)
            assert row["total_salary"] == Decimal("3000.00")
    finally:
        async with pool.acquire() as conn:
            await cleanup(conn)
        await close_db_pool()
