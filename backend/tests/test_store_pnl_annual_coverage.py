"""Regression coverage for annual P&L store/month union counts."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from db.connection import get_pool
from repositories.store_pnl import StorePnlRepository
from services.store_pnl import StorePnlService


SITE_A = "PNLANN-A"
SITE_B = "PNLANN-B"
PERIOD_A = date(2095, 1, 1)
PERIOD_B = date(2095, 2, 1)

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _reset_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM store_pnl_monthly WHERE source_site_code = ANY($1::text[])",
            [SITE_A, SITE_B],
        )
        await connection.execute(
            "DELETE FROM store_pnl_site_links WHERE source_site_code = ANY($1::text[])",
            [SITE_A, SITE_B],
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code = ANY($1::text[])",
            [SITE_A, SITE_B],
        )


@pytest.mark.anyio
async def test_annual_counts_cover_union_across_disjoint_categories() -> None:
    await _reset_fixture()
    pool = await get_pool()
    try:
        async with pool.acquire() as connection:
            await connection.executemany(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    first_seen_month, last_seen_month
                ) VALUES ($1, $2, 'Mobicell', 'P&L Annual Region',
                          'P&L Annual ASM', $3, $3)
                """,
                [
                    (SITE_A, "P&L Annual A", "2095-01"),
                    (SITE_B, "P&L Annual B", "2095-02"),
                ],
            )
            await connection.executemany(
                """
                INSERT INTO store_pnl_monthly (
                    company_name, period, source_site_code,
                    source_location_name, category_code, category_name,
                    amount, data_kind, source_file, source_sha256
                ) VALUES ('Mobicell', $1, $2, $3, $4, $5, $6,
                          'actual', $7, $8)
                """,
                [
                    (
                        PERIOD_A,
                        SITE_A,
                        "P&L Annual A",
                        "v1",
                        "Revenue",
                        Decimal("100.00"),
                        "annual-a.xlsx",
                        "a" * 64,
                    ),
                    (
                        PERIOD_B,
                        SITE_B,
                        "P&L Annual B",
                        "c1",
                        "COGS",
                        Decimal("40.00"),
                        "annual-b.xlsx",
                        "b" * 64,
                    ),
                ],
            )

        repository = StorePnlRepository(pool)
        rows = await repository.annual_rows("Mobicell", None)
        year_rows = [row for row in rows if row["year"] == 2095]

        assert {row["category_code"] for row in year_rows} == {"v1", "c1"}
        assert {(row["store_count"], row["month_count"]) for row in year_rows} == {(2, 2)}

        annual = await StorePnlService(repository).annual("Mobicell", None)
        assert annual == [
            {
                "year": "2095",
                "store_count": 2,
                "month_count": 2,
                "revenue": Decimal("100.00"),
                "cogs": Decimal("40.00"),
                "gross_margin": Decimal("60.00"),
                "operating_costs": Decimal("0.00"),
                "ebitda": Decimal("60.00"),
                "depreciation": Decimal("0.00"),
                "ebit": Decimal("60.00"),
                "is_estimated": False,
            }
        ]
    finally:
        await _reset_fixture()
