"""Lot 46 F05 regression: export report historical fallback respects closed-store scope.

The historical UNION in ``_scope_parameters`` historically skipped the
``s.is_active = TRUE`` predicate so a closed current store could still leak
historical rows when ``include_closed_stores=False``. The dashboard already
applied the same active predicate to its historical path, so this test pins
the same semantic into the export report on both the unperiodised (total)
and ``period='month'`` branches.

Case C (historical-only / unmapped) has no current ``stores`` row at all;
the historical source uses ``LEFT JOIN stores`` so the SQL can express it.
The isolated test database does not enforce the ``historical_monthly_sales``
FK because the bootstrap replays the immutable manifest which omits the
constraint name in this path; the test fixtures rely on that permissive
state to plant an orphan historical row directly.
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from db.connection import get_pool
from repositories.exports import ExportsRepository


ACTIVE_SITE = "EXPORT-L46-ACTIVE"
CLOSED_SITE = "EXPORT-L46-CLOSED"
UNMAPPED_SITE = "EXPORT-L46-UNMAPPED"
TR_LOCATION = "TR Something else"
TR_SITE = "EXPORT-L46-TR"
MONTH = "2097-07"

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _drop_site_code_fk(connection) -> None:
    await connection.execute(
        "ALTER TABLE historical_monthly_sales "
        "DROP CONSTRAINT IF EXISTS historical_monthly_sales_site_code_fkey"
    )


async def _restore_site_code_fk(connection) -> None:
    """Re-add the FK with NOT VALID so existing orphan historical rows are tolerated."""
    await connection.execute(
        "ALTER TABLE historical_monthly_sales "
        "ADD CONSTRAINT historical_monthly_sales_site_code_fkey "
        "FOREIGN KEY (site_code) REFERENCES stores(site_code) NOT VALID"
    )


async def _reset_fixture() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM reporting_agent_day WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, UNMAPPED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM historical_monthly_sales WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, UNMAPPED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )


async def _seed_three_cases() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM reporting_agent_day WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, UNMAPPED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM historical_monthly_sales WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, UNMAPPED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )
        await _drop_site_code_fk(connection)
        await connection.executemany(
            """
            INSERT INTO stores (
                site_code, locatie, firma, regional, asm,
                first_seen_month, last_seen_month, is_active
            ) VALUES ($1, $2, 'Mobicell', 'L46 Region', 'L46 ASM', $3, $3, $4)
            """,
            [
                (ACTIVE_SITE, "Export L46 active", MONTH, True),
                (CLOSED_SITE, "Export L46 closed", MONTH, False),
                (TR_SITE, TR_LOCATION, MONTH, True),
            ],
        )
        await connection.executemany(
            """
            INSERT INTO reporting_agent_day (
                import_month, sale_date, site_code, locatie, firma,
                regional, asm, agent, total_sales, total_quantity,
                focus_quantity, receipt_count, receipt_2plus_count
            ) VALUES (
                $1, $2, $3, $4, 'Mobicell', 'L46 Region', 'L46 ASM',
                $5, $6, 0, 0, 0, 0
            )
            """,
            [
                (MONTH, date(2097, 7, 15), ACTIVE_SITE, "Export L46 active", "Agent 1", Decimal("100.00")),
                (MONTH, date(2097, 7, 15), TR_SITE, TR_LOCATION, "Agent 1", Decimal("999.00")),
            ],
        )
        await connection.executemany(
            """
            INSERT INTO historical_monthly_sales (
                site_code, import_month, firma, total_value,
                total_qty, source_file, source_store_name
            ) VALUES ($1, $2, 'Mobicell', $3, 0, $4, $5)
            """,
            [
                (ACTIVE_SITE, MONTH, Decimal("10.00"), "l46-active.xlsx", "Export L46 active"),
                (CLOSED_SITE, MONTH, Decimal("20.00"), "l46-closed.xlsx", "Export L46 closed"),
                (UNMAPPED_SITE, MONTH, Decimal("30.00"), "l46-unmapped.xlsx", "Export L46 unmapped"),
                (TR_SITE, MONTH, Decimal("40.00"), "l46-tr.xlsx", TR_LOCATION),
            ],
        )


async def _teardown(connection) -> None:
    await connection.execute(
        "DELETE FROM reporting_agent_day WHERE site_code = ANY($1::text[])",
        [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
    )
    await connection.execute(
        "DELETE FROM reporting_agent_month WHERE site_code = ANY($1::text[])",
        [ACTIVE_SITE, CLOSED_SITE, UNMAPPED_SITE, TR_SITE],
    )
    await connection.execute(
        "DELETE FROM historical_monthly_sales WHERE site_code = ANY($1::text[])",
        [ACTIVE_SITE, CLOSED_SITE, UNMAPPED_SITE, TR_SITE],
    )
    await connection.execute(
        "DELETE FROM stores WHERE site_code = ANY($1::text[])",
        [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
    )
    await _restore_site_code_fk(connection)


@pytest.mark.anyio
async def test_f05_baseline_closed_store_leaks_into_historical_branch() -> None:
    """Baseline repro: historical UNION has no active predicate.

    The historical UNION in ``_scope_parameters`` does not apply
    ``s.is_active = TRUE`` so a closed current store with historical sales
    still leaks. We replay both the unfiltered historical UNION and the
    fixed shape (the same SQL with ``s.is_active = TRUE`` appended) so the
    divergence is pinned at the SQL predicate level even after the fix.
    """
    await _reset_fixture()
    await _seed_three_cases()
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            baseline_rows = await conn.fetch(
                """
                SELECT hms.site_code, hms.total_value
                FROM historical_monthly_sales hms
                LEFT JOIN stores s ON s.site_code = hms.site_code
                WHERE hms.import_month = $1
                  AND NOT EXISTS (
                      SELECT 1 FROM reporting_agent_day rad
                      WHERE rad.import_month = hms.import_month
                        AND rad.site_code = hms.site_code
                  )
                """,
                MONTH,
            )
            baseline_amounts = {
                row["site_code"]: row["total_value"] for row in baseline_rows
            }
            assert baseline_amounts[CLOSED_SITE] == Decimal("20.00"), (
                "Baseline repro precondition: the unfiltered historical UNION "
                "must surface the closed store (its reporting_agent_day row "
                "is absent so the NOT EXISTS guard does not suppress it)."
            )
            assert baseline_amounts[UNMAPPED_SITE] == Decimal("30.00"), (
                "Baseline repro precondition: the unfiltered historical UNION "
                "must surface the historical-only/unmapped site because the "
                "LEFT JOIN produces NULL store metadata."
            )

            fixed_rows = await conn.fetch(
                """
                SELECT hms.site_code, hms.total_value
                FROM historical_monthly_sales hms
                LEFT JOIN stores s ON s.site_code = hms.site_code
                WHERE hms.import_month = $1
                  AND s.is_active = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM reporting_agent_day rad
                      WHERE rad.import_month = hms.import_month
                        AND rad.site_code = hms.site_code
                  )
                """,
                MONTH,
            )
            fixed_site_codes = {row["site_code"] for row in fixed_rows}
            assert CLOSED_SITE not in fixed_site_codes, (
                "Predicted post-fix behavior: the active predicate filters the "
                "closed store out of the historical UNION."
            )
            assert UNMAPPED_SITE not in fixed_site_codes, (
                "Predicted post-fix behavior: the active predicate also filters "
                "historical-only/unmapped sites because the LEFT JOIN produces "
                "NULL store metadata which fails s.is_active = TRUE."
            )
            assert ACTIVE_SITE not in fixed_site_codes, (
                "Active store is filtered out here because its reporting_agent_day "
                "row already satisfies the NOT EXISTS guard."
            )
    finally:
        async with pool.acquire() as conn:
            await _teardown(conn)


@pytest.mark.anyio
async def test_f05_fix_closed_store_excluded_from_total_branch() -> None:
    """After the fix, include_closed_stores=False excludes closed + historical-only sites."""
    await _reset_fixture()
    await _seed_three_cases()
    pool = await get_pool()
    repository = ExportsRepository(pool)
    try:
        rows = await repository.fetch_report_rows(
            dataset="stores",
            months=[MONTH],
            filters={},
            include_closed_stores=False,
            campaign_codes_by_month=None,
            campaign_exclusions_by_month=None,
            selected_days=None,
            period=None,
            include_campaign_metrics=False,
            limit=None,
            include_total_count=False,
        )
        totals = {
            row["site_code"]: row["total_sales"]
            for row in rows
        }
        assert ACTIVE_SITE in totals
        assert totals[ACTIVE_SITE] == Decimal("100.00")
        assert CLOSED_SITE not in totals, (
            "Closed store must not contribute when include_closed_stores=False."
        )
        assert UNMAPPED_SITE not in totals, (
            "Historical-only sites must be treated like closed stores when "
            "include_closed_stores=False, matching the established dashboard "
            "semantic."
        )
    finally:
        async with pool.acquire() as conn:
            await _teardown(conn)


@pytest.mark.anyio
async def test_f05_fix_closed_store_excluded_from_monthly_branch() -> None:
    """The fix must apply on the period='month' branch too."""
    await _reset_fixture()
    await _seed_three_cases()
    pool = await get_pool()
    repository = ExportsRepository(pool)
    try:
        rows = await repository.fetch_report_rows(
            dataset="stores",
            months=[MONTH],
            filters={},
            include_closed_stores=False,
            campaign_codes_by_month=None,
            campaign_exclusions_by_month=None,
            selected_days=None,
            period="month",
            include_campaign_metrics=False,
            limit=None,
            include_total_count=False,
        )
        site_codes = {row["site_code"] for row in rows}
        assert ACTIVE_SITE in site_codes
        assert CLOSED_SITE not in site_codes
        assert UNMAPPED_SITE not in site_codes
    finally:
        async with pool.acquire() as conn:
            await _teardown(conn)


@pytest.mark.anyio
async def test_f05_fix_include_closed_stores_true_returns_all() -> None:
    """Regression: include_closed_stores=True keeps every historical contribution."""
    await _reset_fixture()
    await _seed_three_cases()
    pool = await get_pool()
    repository = ExportsRepository(pool)
    try:
        rows = await repository.fetch_report_rows(
            dataset="stores",
            months=[MONTH],
            filters={},
            include_closed_stores=True,
            campaign_codes_by_month=None,
            campaign_exclusions_by_month=None,
            selected_days=None,
            period=None,
            include_campaign_metrics=False,
            limit=None,
            include_total_count=False,
        )
        totals = {
            row["site_code"]: row["total_sales"]
            for row in rows
        }
        assert totals[ACTIVE_SITE] == Decimal("100.00")
        assert totals[CLOSED_SITE] == Decimal("20.00"), (
            "Closed store historical fallback must be visible when "
            "include_closed_stores=True."
        )
        assert totals[UNMAPPED_SITE] == Decimal("30.00"), (
            "Historical-only sites must remain visible when "
            "include_closed_stores=True."
        )
    finally:
        async with pool.acquire() as conn:
            await _teardown(conn)


@pytest.mark.anyio
async def test_f05_fix_tr_location_exclusion_unchanged() -> None:
    """Regression: TR % locations stay excluded across both source branches."""
    await _reset_fixture()
    await _seed_three_cases()
    pool = await get_pool()
    repository = ExportsRepository(pool)
    try:
        rows = await repository.fetch_report_rows(
            dataset="stores",
            months=[MONTH],
            filters={},
            include_closed_stores=False,
            campaign_codes_by_month=None,
            campaign_exclusions_by_month=None,
            selected_days=None,
            period=None,
            include_campaign_metrics=False,
            limit=None,
            include_total_count=False,
        )
        assert all(row["locatie"] != TR_LOCATION for row in rows), (
            "TR-prefixed locations must remain excluded even when they have "
            "both reporting and historical data."
        )
        rows_true = await repository.fetch_report_rows(
            dataset="stores",
            months=[MONTH],
            filters={},
            include_closed_stores=True,
            campaign_codes_by_month=None,
            campaign_exclusions_by_month=None,
            selected_days=None,
            period=None,
            include_campaign_metrics=False,
            limit=None,
            include_total_count=False,
        )
        assert all(row["locatie"] != TR_LOCATION for row in rows_true)
    finally:
        async with pool.acquire() as conn:
            await _teardown(conn)


@pytest.mark.anyio
async def test_f05_fix_firma_filter_uses_existing_fallback() -> None:
    """Regression: firma/regional/asm filters preserve the LEFT JOIN COALESCE fallback."""
    await _reset_fixture()
    await _seed_three_cases()
    pool = await get_pool()
    repository = ExportsRepository(pool)
    try:
        rows = await repository.fetch_report_rows(
            dataset="stores",
            months=[MONTH],
            filters={"firma": ["Mobicell"]},
            include_closed_stores=False,
            campaign_codes_by_month=None,
            campaign_exclusions_by_month=None,
            selected_days=None,
            period=None,
            include_campaign_metrics=False,
            limit=None,
            include_total_count=False,
        )
        assert all(row["firma"] == "Mobicell" for row in rows)
        rows_other = await repository.fetch_report_rows(
            dataset="stores",
            months=[MONTH],
            filters={"firma": ["Mobiup"]},
            include_closed_stores=False,
            campaign_codes_by_month=None,
            campaign_exclusions_by_month=None,
            selected_days=None,
            period=None,
            include_campaign_metrics=False,
            limit=None,
            include_total_count=False,
        )
        assert rows_other == []
    finally:
        async with pool.acquire() as conn:
            await _teardown(conn)
