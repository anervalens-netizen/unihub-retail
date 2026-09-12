"""Regression for P&L reconciliation scope on unlinked site codes."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from db.connection import get_pool
from repositories.store_pnl import StorePnlRepository


SITE = "PNL-UNLINKED-FALLBACK"
MONTH = "2094-03"
PERIOD = date(2094, 3, 1)

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _reset_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM historical_monthly_sales WHERE site_code = $1 AND import_month = $2",
            SITE,
            MONTH,
        )
        await connection.execute(
            "DELETE FROM store_pnl_site_links WHERE source_site_code = $1 OR site_code = $1",
            SITE,
        )
        await connection.execute("DELETE FROM stores WHERE site_code = $1", SITE)


@pytest.mark.anyio
async def test_unlinked_site_uses_company_when_site_company_is_omitted() -> None:
    await _reset_fixture()
    pool = await get_pool()
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    first_seen_month, last_seen_month
                ) VALUES ($1, 'P&L unlinked fallback', 'Mobicell',
                          'P&L Fallback Region', 'P&L Fallback ASM', $2, $2)
                """,
                SITE,
                MONTH,
            )
            await connection.executemany(
                """
                INSERT INTO historical_monthly_sales (
                    site_code, import_month, firma, total_value,
                    source_file, source_store_name
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                [
                    (SITE, MONTH, "Mobicell", Decimal("10.00"), "fallback-mobicell.xlsx", "Fallback"),
                    (SITE, MONTH, "Mobiup", Decimal("20.00"), "fallback-mobiup.xlsx", "Fallback"),
                ],
            )

        repository = StorePnlRepository(pool)

        fallback = await repository.sales_rows(
            PERIOD,
            PERIOD,
            "Mobicell",
            SITE,
            None,
            None,
        )
        assert [row["gross_amount"] for row in fallback] == [Decimal("10.00")]

        explicit = await repository.sales_rows(
            PERIOD,
            PERIOD,
            None,
            SITE,
            "Mobiup",
            None,
        )
        assert [row["gross_amount"] for row in explicit] == [Decimal("20.00")]

        ambiguous = await repository.sales_rows(
            PERIOD,
            PERIOD,
            None,
            SITE,
            None,
            None,
        )
        assert ambiguous == []
    finally:
        await _reset_fixture()
