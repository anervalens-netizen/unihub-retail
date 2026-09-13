"""Lot 46 F04 regression: P&L "Nealocat" scope must agree with sales reconciliation.

The pristine schema declares ``stores.regional TEXT NOT NULL``. To reproduce the
latent asymmetry on the base we relax the NOT NULL constraint in setup and
restore it in teardown; the divergence only manifests once a store is allowed
to carry a NULL ``regional`` value, which is exactly the population that the
P&L code normalises via ``COALESCE(s.regional, 'Nealocat')`` while
``sales_rows`` filters via the raw ``s.regional = $regional`` predicate.
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from db.connection import get_pool
from repositories.store_pnl import StorePnlRepository


NULL_REGIONAL_SITE = "PNL-L46-NULLREG"
NAMED_REGIONAL_SITE = "PNL-L46-NAMEDREG"
FIRMA = "Mobicell"
PERIOD = date(2097, 7, 1)
SALES_MONTH = "2097-07"

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _drop_regional_not_null(connection) -> None:
    await connection.execute("ALTER TABLE stores ALTER COLUMN regional DROP NOT NULL")


async def _restore_regional_not_null(connection) -> None:
    await connection.execute(
        "UPDATE stores SET regional = '' WHERE regional IS NULL"
    )
    await connection.execute("ALTER TABLE stores ALTER COLUMN regional SET NOT NULL")


async def _reset_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM historical_monthly_sales WHERE site_code = ANY($1::text[])",
            [NULL_REGIONAL_SITE, NAMED_REGIONAL_SITE],
        )
        await connection.execute(
            "DELETE FROM store_pnl_site_links WHERE site_code = ANY($1::text[])",
            [NULL_REGIONAL_SITE, NAMED_REGIONAL_SITE],
        )
        await connection.execute(
            "DELETE FROM store_pnl_monthly WHERE source_site_code = ANY($1::text[])",
            [NULL_REGIONAL_SITE, NAMED_REGIONAL_SITE],
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code = ANY($1::text[])",
            [NULL_REGIONAL_SITE, NAMED_REGIONAL_SITE],
        )


async def _seed_regional_test_data() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await _drop_regional_not_null(connection)
        await connection.executemany(
            """
            INSERT INTO stores (
                site_code, locatie, firma, regional, asm,
                first_seen_month, last_seen_month
            ) VALUES ($1, $2, $3, $4, 'L46 ASM', $5, $5)
            """,
            [
                (
                    NULL_REGIONAL_SITE,
                    "P&L L46 null regional",
                    FIRMA,
                    None,
                    SALES_MONTH,
                ),
                (
                    NAMED_REGIONAL_SITE,
                    "P&L L46 named regional",
                    FIRMA,
                    "Named Region",
                    SALES_MONTH,
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
                    FIRMA,
                    PERIOD,
                    NULL_REGIONAL_SITE,
                    "P&L L46 null regional",
                    Decimal("100.00"),
                    "l46-nullreg-pnl.xlsx",
                    "n" * 64,
                ),
                (
                    FIRMA,
                    PERIOD,
                    NAMED_REGIONAL_SITE,
                    "P&L L46 named regional",
                    Decimal("50.00"),
                    "l46-namedreg-pnl.xlsx",
                    "m" * 64,
                ),
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
                    NULL_REGIONAL_SITE,
                    SALES_MONTH,
                    "Mobicell SRL",
                    Decimal("300.00"),
                    "l46-nullreg-sales.xlsx",
                    "P&L L46 null regional",
                ),
                (
                    NAMED_REGIONAL_SITE,
                    SALES_MONTH,
                    "Mobicell SRL",
                    Decimal("75.00"),
                    "l46-namedreg-sales.xlsx",
                    "P&L L46 named regional",
                ),
            ],
        )


@pytest.mark.anyio
async def test_f04_baseline_nealocat_diverges_between_pnl_and_sales_rows() -> None:
    """Baseline repro: P&L COALESCE matches NULL, sales_rows raw predicate drops it.

    The baseline reproduces the pre-fix SQL by replaying the original raw
    ``s.regional = $regional`` predicate against the same dataset the fix
    unifies. This must always fail (and prove the divergence exists) because
    the production predicate cannot match NULL.
    """
    await _reset_fixture()
    await _seed_regional_test_data()
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            baseline_rows = await conn.fetch(
                """
                SELECT s.regional, h.site_code, h.total_value
                FROM historical_monthly_sales h
                JOIN stores s ON s.site_code = h.site_code
                WHERE h.import_month = $1
                  AND (s.regional = $2)
                """,
                SALES_MONTH,
                "Nealocat",
            )
            assert baseline_rows == [], (
                "Baseline repro precondition failed: NULL regionals should never "
                "match a raw text comparison. The schema constraint should keep "
                "this strictly empty when sales_rows uses s.regional = $regional."
            )
            coalesce_rows = await conn.fetch(
                """
                SELECT s.regional, h.site_code, h.total_value
                FROM historical_monthly_sales h
                JOIN stores s ON s.site_code = h.site_code
                WHERE h.import_month = $1
                  AND (COALESCE(s.regional, 'Nealocat') = $2)
                """,
                SALES_MONTH,
                "Nealocat",
            )
            coalesce_amounts = sorted(row["total_value"] for row in coalesce_rows)
            assert coalesce_amounts == [Decimal("300.00")], (
                "P&L COALESCE('Nealocat') matches the NULL-regional store, "
                "confirming the predicate asymmetry that the fix resolves."
            )
    finally:
        async with pool.acquire() as connection:
            await _reset_fixture()
            await _restore_regional_not_null(connection)


@pytest.mark.anyio
async def test_f04_fix_nealocat_agrees_between_pnl_and_sales_rows() -> None:
    """Regression: the fix unifies the two scopes on the same NULL-regional population."""
    await _reset_fixture()
    await _seed_regional_test_data()
    pool = await get_pool()
    repository = StorePnlRepository(pool)
    try:
        pnl_rows = await repository.rows(
            PERIOD, PERIOD, FIRMA, None, None, "Nealocat"
        )
        pnl_amounts = sorted(row["amount"] for row in pnl_rows)
        assert pnl_amounts == [Decimal("100.00")]

        sales = await repository.sales_rows(
            PERIOD, PERIOD, FIRMA, None, None, "Nealocat"
        )
        sales_amounts = sorted(row["gross_amount"] for row in sales)
        assert sales_amounts == [Decimal("300.00")], (
            "After the fix, sales_rows must include only the NULL-regional store when "
            "the requested regional is 'Nealocat'."
        )
    finally:
        async with pool.acquire() as connection:
            await _reset_fixture()
            await _restore_regional_not_null(connection)


@pytest.mark.anyio
async def test_f04_fix_named_regional_unaffected() -> None:
    """Regression: ordinary named regionals must keep the previous behavior."""
    await _reset_fixture()
    await _seed_regional_test_data()
    pool = await get_pool()
    repository = StorePnlRepository(pool)
    try:
        pnl_rows = await repository.rows(
            PERIOD, PERIOD, FIRMA, None, None, "Named Region"
        )
        pnl_amounts = sorted(row["amount"] for row in pnl_rows)
        assert pnl_amounts == [Decimal("50.00")]

        sales = await repository.sales_rows(
            PERIOD, PERIOD, FIRMA, None, None, "Named Region"
        )
        sales_amounts = sorted(row["gross_amount"] for row in sales)
        assert sales_amounts == [Decimal("75.00")]
    finally:
        async with pool.acquire() as connection:
            await _reset_fixture()
            await _restore_regional_not_null(connection)


@pytest.mark.anyio
async def test_f04_fix_unfiltered_returns_full_population() -> None:
    """Regression: regional=None must remain a no-op for both queries."""
    await _reset_fixture()
    await _seed_regional_test_data()
    pool = await get_pool()
    repository = StorePnlRepository(pool)
    try:
        pnl_rows = await repository.rows(PERIOD, PERIOD, FIRMA, None, None, None)
        pnl_amounts = sorted(row["amount"] for row in pnl_rows)
        assert pnl_amounts == [Decimal("50.00"), Decimal("100.00")]

        sales = await repository.sales_rows(PERIOD, PERIOD, FIRMA, None, None, None)
        sales_amounts = sorted(row["gross_amount"] for row in sales)
        assert sales_amounts == [Decimal("375.00")]
    finally:
        async with pool.acquire() as connection:
            await _reset_fixture()
            await _restore_regional_not_null(connection)


@pytest.mark.anyio
async def test_f04_fix_firma_filter_unaffected() -> None:
    """Regression: company filter remains the cross-population delimiter."""
    await _reset_fixture()
    await _seed_regional_test_data()
    pool = await get_pool()
    repository = StorePnlRepository(pool)
    try:
        pnl_rows = await repository.rows(
            PERIOD, PERIOD, "Mobiup", None, None, "Nealocat"
        )
        assert pnl_rows == []

        sales = await repository.sales_rows(
            PERIOD, PERIOD, "Mobiup", None, None, "Nealocat"
        )
        assert sales == []
    finally:
        async with pool.acquire() as connection:
            await _reset_fixture()
            await _restore_regional_not_null(connection)


@pytest.mark.anyio
async def test_f04_fix_explicit_site_code_filter_unaffected() -> None:
    """Regression: site_code selection still dominates the scope."""
    await _reset_fixture()
    await _seed_regional_test_data()
    pool = await get_pool()
    repository = StorePnlRepository(pool)
    try:
        pnl_null = await repository.rows(
            PERIOD, PERIOD, FIRMA, NULL_REGIONAL_SITE, None, None
        )
        pnl_amounts = sorted(row["amount"] for row in pnl_null)
        assert pnl_amounts == [Decimal("100.00")]

        sales_null = await repository.sales_rows(
            PERIOD, PERIOD, FIRMA, NULL_REGIONAL_SITE, None, None
        )
        sales_amounts = sorted(row["gross_amount"] for row in sales_null)
        assert sales_amounts == [Decimal("300.00")]

        pnl_named = await repository.rows(
            PERIOD, PERIOD, FIRMA, NAMED_REGIONAL_SITE, None, None
        )
        assert sorted(row["amount"] for row in pnl_named) == [Decimal("50.00")]
        sales_named = await repository.sales_rows(
            PERIOD, PERIOD, FIRMA, NAMED_REGIONAL_SITE, None, None
        )
        assert sorted(row["gross_amount"] for row in sales_named) == [Decimal("75.00")]
    finally:
        async with pool.acquire() as connection:
            await _reset_fixture()
            await _restore_regional_not_null(connection)
