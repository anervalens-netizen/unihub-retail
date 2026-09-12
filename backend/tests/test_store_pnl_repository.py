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
TEST_OLD_SOURCE = "PNLPREF-OLD"
TEST_OLD_COMPANY_SOURCE = "PNLPREF-MOBIUP"
TEST_UNMAPPED_SOURCE = "PNL-UNMAPPED"
TEST_ESTIMATED_SITE = "PNLPREF-ESTIMATED"
UNALLOCATED_SOURCE = "__FINANCE_UNALLOCATED__"
TEST_OLD_COMPANY_PERIOD = date(2096, 7, 1)
TEST_PERIOD = date(2097, 7, 1)
TEST_SALES_MONTH = "2097-07"

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _reset_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM store_pnl_monthly WHERE source_site_code = ANY($1::text[]) OR (period = $2 AND source_site_code = $3)",
            [
                TEST_SITE,
                TEST_OLD_SOURCE,
                TEST_OLD_COMPANY_SOURCE,
                TEST_UNMAPPED_SOURCE,
                TEST_ESTIMATED_SITE,
            ],
            TEST_PERIOD,
            UNALLOCATED_SOURCE,
        )
        await connection.execute(
            "DELETE FROM store_pnl_site_links WHERE source_site_code = ANY($1::text[])",
            [TEST_SITE, TEST_OLD_SOURCE, TEST_OLD_COMPANY_SOURCE, TEST_ESTIMATED_SITE],
        )
        await connection.execute(
            "DELETE FROM historical_monthly_sales WHERE site_code = ANY($1::text[]) AND import_month = $2",
            [TEST_SITE, TEST_UNMAPPED_SOURCE],
            TEST_SALES_MONTH,
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code = ANY($1::text[])",
            [TEST_SITE, TEST_ESTIMATED_SITE, TEST_UNMAPPED_SOURCE],
        )


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
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    first_seen_month, last_seen_month
                ) VALUES ($1, 'P&L estimated test', 'Mobicell',
                          'P&L Test Region', 'P&L Test ASM', '2097-07', '2097-07')
                """,
                TEST_ESTIMATED_SITE,
            )
            await connection.executemany(
                """
                INSERT INTO store_pnl_site_links (
                    company_name, source_site_code, source_location_name,
                    site_code, match_method, confidence, reviewed
                ) VALUES ($1, $2, $3, $4, $5, 1, true)
                """,
                [
                    ("Mobicell", TEST_SITE, "P&L precedence test", TEST_SITE, "exact_code"),
                    (
                        "Mobicell",
                        TEST_OLD_SOURCE,
                        "P&L old-code estimate",
                        TEST_SITE,
                        "manual_alias",
                    ),
                    (
                        "Mobiup",
                        TEST_OLD_COMPANY_SOURCE,
                        "P&L previous-company history",
                        TEST_SITE,
                        "manual_alias",
                    ),
                    (
                        "Mobicell",
                        TEST_ESTIMATED_SITE,
                        "P&L estimated test",
                        TEST_ESTIMATED_SITE,
                        "exact_code",
                    ),
                ],
            )
            await connection.executemany(
                """
                INSERT INTO store_pnl_monthly (
                    company_name, period, source_site_code,
                    source_location_name, category_code, category_name,
                    amount, data_kind, source_file, source_sha256
                ) VALUES ($1, $2, $3, $4, 'v2', 'Topups', $5,
                          'actual', $6, $7)
                """,
                [
                    (
                        "Mobicell",
                        TEST_PERIOD,
                        TEST_UNMAPPED_SOURCE,
                        "Mobicell unmapped collision",
                        Decimal("10.00"),
                        "mobicell-unmapped.xlsx",
                        "c" * 64,
                    ),
                    (
                        "Mobiup",
                        TEST_PERIOD,
                        TEST_UNMAPPED_SOURCE,
                        "Mobiup unmapped collision",
                        Decimal("20.00"),
                        "mobiup-unmapped.xlsx",
                        "u" * 64,
                    ),
                ],
            )
            await connection.executemany(
                """
                INSERT INTO store_pnl_monthly (
                    company_name, period, source_site_code,
                    source_location_name, category_code, category_name,
                    amount, data_kind, source_file, source_sha256
                ) VALUES ('Mobicell', $1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                [
                    (
                        TEST_PERIOD,
                        TEST_ESTIMATED_SITE,
                        "P&L estimated test",
                        "v1",
                        "Revenue",
                        Decimal("200.00"),
                        "estimated",
                        "estimated-store.xlsx",
                        "s" * 64,
                    ),
                    (
                        TEST_PERIOD,
                        UNALLOCATED_SOURCE,
                        "Finance unallocated",
                        "v3",
                        "Other revenue",
                        Decimal("25.00"),
                        "actual",
                        "finance-unallocated.xlsx",
                        "f" * 64,
                    ),
                ],
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
                    (
                        TEST_PERIOD,
                        TEST_OLD_SOURCE,
                        Decimal("999.00"),
                        "estimated",
                        "old-code-estimate.xlsx",
                        "o" * 64,
                    ),
                ],
            )
            await connection.executemany(
                """
                INSERT INTO store_pnl_monthly (
                    company_name, period, source_site_code,
                    source_location_name, category_code, category_name,
                    amount, data_kind, source_file, source_sha256
                ) VALUES ('Mobiup', $1, $2, 'P&L previous-company history',
                          'v1', 'Revenue', $3, $4, $5, $6)
                """,
                [
                    (
                        TEST_OLD_COMPANY_PERIOD,
                        TEST_OLD_COMPANY_SOURCE,
                        Decimal("80.00"),
                        "actual",
                        "previous-company.xlsx",
                        "m" * 64,
                    ),
                    (
                        TEST_PERIOD,
                        TEST_OLD_COMPANY_SOURCE,
                        Decimal("777.00"),
                        "estimated",
                        "moved-store-estimate.xlsx",
                        "x" * 64,
                    ),
                ],
            )

        rows = await StorePnlRepository(pool).rows(TEST_PERIOD, TEST_PERIOD, "Mobicell")

        matching = [row for row in rows if row["source_site_code"] == TEST_SITE]
        assert len(matching) == 1
        assert matching[0]["data_kind"] == "actual"
        assert matching[0]["amount"] == Decimal("125.00")
        assert matching[0]["site_code"] == TEST_SITE

        estimated = [row for row in rows if row["site_code"] == TEST_ESTIMATED_SITE]
        assert len(estimated) == 1
        assert estimated[0]["data_kind"] == "estimated"
        assert estimated[0]["amount"] == Decimal("200.00")

        unallocated = [
            row for row in rows if row["source_site_code"] == UNALLOCATED_SOURCE
        ]
        assert len(unallocated) == 1
        assert unallocated[0]["data_kind"] == "actual"
        assert unallocated[0]["site_code"] == UNALLOCATED_SOURCE

        filtered_out = await StorePnlRepository(pool).rows(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
            "OTHER-SITE",
        )
        assert all(row["source_site_code"] != TEST_SITE for row in filtered_out)

        regional_rows = await StorePnlRepository(pool).rows(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
            regional="P&L Test Region",
        )
        assert {(row["site_code"], row["data_kind"]) for row in regional_rows} == {
            (TEST_SITE, "actual"),
            (TEST_ESTIMATED_SITE, "estimated"),
        }

        stores = await StorePnlRepository(pool).stores("Mobicell")
        store = next(row for row in stores if row["site_code"] == TEST_SITE)
        assert store["company_name"] == "Mobicell"
        assert store["location"] == "P&L precedence test"
        assert all(row["site_code"] != UNALLOCATED_SOURCE for row in stores)

        all_stores = await StorePnlRepository(pool).stores(None)
        unmapped = [
            row for row in all_stores if row["site_code"] == TEST_UNMAPPED_SOURCE
        ]
        assert {row["scope_company"] for row in unmapped} == {"Mobicell", "Mobiup"}

        mobicell_unmapped = await StorePnlRepository(pool).rows(
            TEST_PERIOD,
            TEST_PERIOD,
            None,
            TEST_UNMAPPED_SOURCE,
            "Mobicell",
        )
        assert [(row["company_name"], row["amount"]) for row in mobicell_unmapped] == [
            ("Mobicell", Decimal("10.00"))
        ]
        assert await StorePnlRepository(pool).rows(
            TEST_PERIOD,
            TEST_PERIOD,
            None,
            TEST_UNMAPPED_SOURCE,
        ) == []

        mobiup_unmapped = await StorePnlRepository(pool).annual_rows(
            None,
            TEST_UNMAPPED_SOURCE,
            "Mobiup",
        )
        assert [(row["category_code"], row["amount"]) for row in mobiup_unmapped] == [
            ("v2", Decimal("20.00"))
        ]

        annual_rows = await StorePnlRepository(pool).annual_rows("Mobicell", TEST_SITE)
        revenues = {
            row["year"]: row
            for row in annual_rows
            if row["category_code"] == "v1"
        }
        assert revenues[2096]["amount"] == Decimal("80.00")
        assert revenues[2097]["amount"] == Decimal("902.00")
        assert revenues[2096]["is_estimated"] is False
        assert revenues[2097]["is_estimated"] is True

        annual_company_rows = await StorePnlRepository(pool).annual_rows("Mobicell", None)
        company_revenue = next(
            row for row in annual_company_rows if row["year"] == 2097 and row["category_code"] == "v1"
        )
        assert company_revenue["amount"] == Decimal("325.00")
        assert company_revenue["store_count"] == 2
        assert company_revenue["is_estimated"] is True
        unallocated_annual = next(
            row for row in annual_company_rows if row["year"] == 2097 and row["category_code"] == "v3"
        )
        assert unallocated_annual["amount"] == Decimal("25.00")
        assert unallocated_annual["store_count"] == 0

        annual_regional_rows = await StorePnlRepository(pool).annual_rows(
            "Mobicell",
            None,
            regional="P&L Test Region",
        )
        regional_revenue = next(
            row for row in annual_regional_rows if row["category_code"] == "v1"
        )
        assert regional_revenue["amount"] == Decimal("325.00")
        assert regional_revenue["store_count"] == 2

        service = StorePnlService(StorePnlRepository(pool))
        overview = await service.overview(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
            TEST_SITE,
        )
        assert overview["site_code"] == TEST_SITE
        assert overview["summary"]["revenue"] == 902.0
        assert len(overview["stores"]) == 2

        company_overview = await service.overview(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
        )
        assert company_overview["summary"]["revenue"] == 360.0
        assert all(store["source_site_code"] != UNALLOCATED_SOURCE for store in company_overview["stores"])

        annual = await service.annual("Mobicell", TEST_SITE)
        assert annual == [
            {
                "year": "2096",
                "revenue": 80.0,
                "cogs": 0.0,
                "gross_margin": 80.0,
                "operating_costs": 0.0,
                "ebitda": 80.0,
                "depreciation": 0.0,
                "ebit": 80.0,
                "store_count": 1,
                "month_count": 1,
                "is_estimated": False,
            },
            {
                "year": "2097",
                "revenue": 902.0,
                "cogs": 0.0,
                "gross_margin": 902.0,
                "operating_costs": 0.0,
                "ebitda": 902.0,
                "depreciation": 0.0,
                "ebit": 902.0,
                "store_count": 1,
                "month_count": 1,
                "is_estimated": True,
            }
        ]
    finally:
        await _reset_fixture()


@pytest.mark.anyio
async def test_sales_rows_align_with_pnl_reconciliation_population() -> None:
    """Retail sales must use the same population rules as the P&L rows."""
    await _reset_fixture()
    pool = await get_pool()
    repository = StorePnlRepository(pool)
    try:
        async with pool.acquire() as connection:
            await connection.executemany(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    first_seen_month, last_seen_month
                ) VALUES ($1, $2, 'Mobicell', $3, 'P&L Test ASM', '2097-07', '2097-07')
                """,
                [
                    (TEST_SITE, "P&L precedence test", "P&L Test Region"),
                    (TEST_UNMAPPED_SOURCE, "P&L unmapped sales test", "P&L Unmapped Region"),
                ],
            )
            await connection.executemany(
                """
                INSERT INTO historical_monthly_sales (
                    site_code, import_month, firma, total_value,
                    source_file, source_store_name
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                [
                    (
                        TEST_SITE,
                        TEST_SALES_MONTH,
                        "Mobicell SRL",
                        Decimal("300.00"),
                        "sales-mobicell.xlsx",
                        "P&L precedence test",
                    ),
                    (
                        TEST_SITE,
                        TEST_SALES_MONTH,
                        "Mobiup SRL",
                        Decimal("50.00"),
                        "sales-mobiup.xlsx",
                        "P&L previous-company history",
                    ),
                    (
                        TEST_UNMAPPED_SOURCE,
                        TEST_SALES_MONTH,
                        "Mobicell SRL",
                        Decimal("10.00"),
                        "sales-unmapped-mobicell.xlsx",
                        "P&L unmapped sales test",
                    ),
                    (
                        TEST_UNMAPPED_SOURCE,
                        TEST_SALES_MONTH,
                        "Mobiup SRL",
                        Decimal("20.00"),
                        "sales-unmapped-mobiup.xlsx",
                        "P&L unmapped sales test",
                    ),
                ],
            )
            # The canonical site links both companies, so P&L revenue already
            # consolidates them; retail sales must report the same population.
            await connection.executemany(
                """
                INSERT INTO store_pnl_site_links (
                    company_name, source_site_code, source_location_name,
                    site_code, match_method, confidence, reviewed
                ) VALUES ($1, $2, $3, $4, $5, 1, true)
                """,
                [
                    ("Mobicell", TEST_SITE, "P&L precedence test", TEST_SITE, "exact_code"),
                    (
                        "Mobiup",
                        TEST_OLD_COMPANY_SOURCE,
                        "P&L previous-company history",
                        TEST_SITE,
                        "manual_alias",
                    ),
                ],
            )
            await connection.executemany(
                """
                INSERT INTO store_pnl_monthly (
                    company_name, period, source_site_code,
                    source_location_name, category_code, category_name,
                    amount, data_kind, source_file, source_sha256
                ) VALUES ($1, $2, $3, $4, 'v1', 'Revenue', $5, 'actual', $6, $7)
                """,
                [
                    (
                        "Mobicell",
                        TEST_PERIOD,
                        TEST_SITE,
                        "P&L precedence test",
                        Decimal("125.00"),
                        "pnl-mobicell.xlsx",
                        "p" * 64,
                    ),
                    (
                        "Mobiup",
                        TEST_PERIOD,
                        TEST_OLD_COMPANY_SOURCE,
                        "P&L previous-company history",
                        Decimal("77.00"),
                        "pnl-mobiup.xlsx",
                        "q" * 64,
                    ),
                ],
            )

        # A. A canonical mapped site consolidates both companies, exactly like rows().
        consolidated = await repository.sales_rows(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
            TEST_SITE,
            None,
            None,
        )
        assert [row["gross_amount"] for row in consolidated] == [Decimal("350.00")]

        # B. Without site_code the company filter still applies (no cross-company leak).
        company_only = await repository.sales_rows(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
            None,
            None,
            None,
        )
        assert [row["gross_amount"] for row in company_only] == [Decimal("310.00")]

        # C. Unlinked collision: site_company remains the explicit disambiguator.
        unlinked_mobicell = await repository.sales_rows(
            TEST_PERIOD,
            TEST_PERIOD,
            None,
            TEST_UNMAPPED_SOURCE,
            "Mobicell",
            None,
        )
        assert [row["gross_amount"] for row in unlinked_mobicell] == [Decimal("10.00")]

        unlinked_mobiup = await repository.sales_rows(
            TEST_PERIOD,
            TEST_PERIOD,
            None,
            TEST_UNMAPPED_SOURCE,
            "Mobiup",
            None,
        )
        assert [row["gross_amount"] for row in unlinked_mobiup] == [Decimal("20.00")]

        # D. Regional scoping is unchanged.
        assert await repository.sales_rows(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
            TEST_SITE,
            None,
            "P&L Unmapped Region",
        ) == []

        # E. The reconciliation block reports the same retail population as P&L.
        overview = await StorePnlService(repository).overview(
            TEST_PERIOD,
            TEST_PERIOD,
            "Mobicell",
            TEST_SITE,
        )
        assert len(overview["reconciliation"]) == 1
        reconciliation = overview["reconciliation"][0]
        assert reconciliation["month"] == "2097-07"
        assert reconciliation["pnl_revenue"] == Decimal("202.00")
        assert reconciliation["retail_sales_gross"] == Decimal("350.00")
        assert reconciliation["retail_sales_gross"] == consolidated[0]["gross_amount"]
    finally:
        await _reset_fixture()
