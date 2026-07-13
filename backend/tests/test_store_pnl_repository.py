"""Isolated PostgreSQL coverage for P&L actual-versus-estimate precedence."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from db.connection import get_pool
from repositories.store_pnl import StorePnlRepository
from services.store_pnl import StorePnlService


TEST_SITE = "PNLPREF"
TEST_PERIOD = date(2097, 7, 1)

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _reset_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM store_pnl_monthly WHERE source_site_code = $1",
            TEST_SITE,
        )
        await connection.execute(
            "DELETE FROM store_pnl_site_links WHERE source_site_code = $1",
            TEST_SITE,
        )
        await connection.execute("DELETE FROM stores WHERE site_code = $1", TEST_SITE)


@pytest.mark.anyio
async def test_rows_prefer_actual_over_estimate_for_same_business_key() -> None:
    await _reset_fixture()
    pool = await get_pool()
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    first_seen_month, last_seen_month
                ) VALUES ($1, 'P&L precedence test', 'Mobicell',
                          'P&L Test Region', 'P&L Test ASM', '2097-07', '2097-07')
                """,
                TEST_SITE,
            )
            await connection.execute(
                """
                INSERT INTO store_pnl_site_links (
                    company_name, source_site_code, source_location_name,
                    site_code, match_method, confidence, reviewed
                ) VALUES ('Mobicell', $1, 'P&L precedence test', $1,
                          'exact_code', 1, true)
                """,
                TEST_SITE,
            )
            await connection.executemany(
                """
                INSERT INTO store_pnl_monthly (
                    company_name, period, source_site_code,
                    source_location_name, category_code, category_name,
                    amount, data_kind, source_file, source_sha256
                ) VALUES ('Mobicell', $1, $2, 'P&L precedence test',
                          'v1', 'Revenue', $3, $4, $5, $6)
                """,
                [
                    (TEST_PERIOD, TEST_SITE, Decimal("100.00"), "estimated", "estimate.xlsx", "e" * 64),
                    (TEST_PERIOD, TEST_SITE, Decimal("125.00"), "actual", "actual.xlsx", "a" * 64),
                ],
            )

        rows = await StorePnlRepository(pool).rows(TEST_PERIOD, TEST_PERIOD, "Mobicell")

        matching = [row for row in rows if row["source_site_code"] == TEST_SITE]
        assert len(matching) == 1
        assert matching[0]["data_kind"] == "actual"
        assert matching[0]["amount"] == Decimal("125.00")
        assert matching[0]["site_code"] == TEST_SITE

        filtered_out = await StorePnlRepository(pool).rows(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
            "OTHER-SITE",
        )
        assert all(row["source_site_code"] != TEST_SITE for row in filtered_out)

        stores = await StorePnlRepository(pool).stores("Mobicell")
        store = next(row for row in stores if row["site_code"] == TEST_SITE)
        assert store["company_name"] == "Mobicell"
        assert store["location"] == "P&L precedence test"

        annual_rows = await StorePnlRepository(pool).annual_rows("Mobicell", TEST_SITE)
        revenue = next(row for row in annual_rows if row["category_code"] == "v1")
        assert revenue["year"] == 2097
        assert revenue["amount"] == Decimal("125.00")
        assert revenue["is_estimated"] is False

        service = StorePnlService(StorePnlRepository(pool))
        overview = await service.overview(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
            TEST_SITE,
        )
        assert overview["site_code"] == TEST_SITE
        assert overview["summary"]["revenue"] == 125.0
        assert len(overview["stores"]) == 1

        annual = await service.annual("Mobicell", TEST_SITE)
        assert annual == [
            {
                "year": "2097",
                "revenue": 125.0,
                "cogs": 0.0,
                "gross_margin": 125.0,
                "operating_costs": 0.0,
                "ebitda": 125.0,
                "depreciation": 0.0,
                "ebit": 125.0,
                "is_estimated": False,
            }
        ]
    finally:
        await _reset_fixture()
