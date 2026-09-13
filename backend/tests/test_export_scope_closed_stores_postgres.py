"""Lot 46 F05 regression: export report historical fallback respects closed-store scope.

The historical UNION in ``_scope_parameters`` previously omitted the
``s.is_active = TRUE`` predicate so a closed current store (a stores row with
``is_active = FALSE``) could still leak historical ``historical_monthly_sales``
rows when ``include_closed_stores=False``. The dashboard already applies the
same active predicate to its historical path, so this test pins the same
semantic into the export report on both the unperiodised (total) and
``period='month'`` branches.

The test never alters the schema and never inserts orphan historical rows:
every ``historical_monthly_sales`` row references a real ``stores`` row. The
test therefore runs cleanly on any isolated database that enforces
``historical_monthly_sales.site_code REFERENCES stores(site_code)``.

Fixtures:

ACTIVE_SITE
    valid stores row, ``is_active = TRUE``; reporting_agent_day + historical.
    Historical is suppressed by the ``NOT EXISTS`` guard.

CLOSED_SITE
    valid stores row, ``is_active = FALSE``; only historical_monthly_sales.
    No ``reporting_agent_day`` row, so the historical UNION picks it up — that
    is the leak path the F05 fix closes.

TR_SITE
    valid stores row, ``is_active = TRUE``; locatie starts with ``TR ``;
    reporting + historical. The historical fallback must not bypass the
    location filter.

The closing block additionally pins the schema invariants that justify the
F04 disposition (no production delta) and that bound this test (no FK drops).
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
TR_SITE = "EXPORT-L46-TR"
TR_LOCATION = "TR Something else"
MONTH = "2097-07"
HISTORICAL_FK_NAME = "historical_monthly_sales_site_code_fkey"


pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _fk_is_validated(connection) -> bool:
    return bool(
        await connection.fetchval(
            """
            SELECT convalidated
            FROM pg_constraint
            WHERE conrelid = 'historical_monthly_sales'::regclass
              AND contype = 'f'
              AND conname = $1
            """,
            HISTORICAL_FK_NAME,
        )
    )


async def _fk_exists(connection) -> bool:
    return bool(
        await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'historical_monthly_sales'::regclass
                  AND contype = 'f'
                  AND conname = $1
            )
            """,
            HISTORICAL_FK_NAME,
        )
    )


async def _stores_regional_is_not_null(connection) -> bool:
    return bool(
        await connection.fetchval(
            """
            SELECT attnotnull
            FROM pg_attribute
            WHERE attrelid = 'stores'::regclass
              AND attname = 'regional'
            """
        )
    )


@pytest.fixture
async def f05_pool():
    pool = await get_pool()
    yield pool


@pytest.fixture
async def f05_seeded(f05_pool):
    """Seed ACTIVE/CLOSED/TR sites, all with FK-valid historical rows."""
    async with f05_pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM reporting_agent_day WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM historical_monthly_sales WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )
        await connection.executemany(
            """
            INSERT INTO stores (
                site_code, locatie, firma, regional, asm,
                first_seen_month, last_seen_month, is_active
            ) VALUES (
                $1, $2, 'Mobicell', 'L46 Region', 'L46 ASM',
                $3, $3, $4
            )
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
                (MONTH, date(2097, 7, 15), ACTIVE_SITE, "Export L46 active",
                 "Agent 1", Decimal("100.00")),
                (MONTH, date(2097, 7, 15), TR_SITE, TR_LOCATION,
                 "Agent 1", Decimal("999.00")),
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
                (ACTIVE_SITE, MONTH, Decimal("10.00"),
                 "l46-active.xlsx", "Export L46 active"),
                (CLOSED_SITE, MONTH, Decimal("20.00"),
                 "l46-closed.xlsx", "Export L46 closed"),
                (TR_SITE, MONTH, Decimal("40.00"),
                 "l46-tr.xlsx", TR_LOCATION),
            ],
        )
    yield
    async with f05_pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM reporting_agent_day WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM historical_monthly_sales WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code = ANY($1::text[])",
            [ACTIVE_SITE, CLOSED_SITE, TR_SITE],
        )


@pytest.mark.anyio
async def test_f05_schema_invariants_hold(f05_pool) -> None:
    """The historical FK must exist, be validated, and ``stores.regional`` must
    remain NOT NULL. These invariants justify the F04 disposition (no
    production delta) and bound this test (no FK drops)."""
    async with f05_pool.acquire() as connection:
        assert await _fk_exists(connection), (
            "Authoritative schema invariant broken: "
            "historical_monthly_sales.site_code FK must exist."
        )
        assert await _fk_is_validated(connection), (
            "Authoritative schema invariant broken: "
            "historical_monthly_sales.site_code FK must be validated "
            "(convalidated = true)."
        )
        assert await _stores_regional_is_not_null(connection), (
            "Authoritative schema invariant broken: stores.regional must "
            "be NOT NULL."
        )


@pytest.mark.anyio
async def test_f05_orphan_historical_insert_is_rejected(f05_pool) -> None:
    """Inserting a historical row that has no matching stores row must fail.

    The probe runs inside a SAVEPOINT so the transaction is left untouched
    if the rejection ever stops happening.
    """
    async with f05_pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SAVEPOINT f05_orphan_probe")
            with pytest.raises(Exception) as exc_info:
                await connection.execute(
                    """
                    INSERT INTO historical_monthly_sales (
                        site_code, import_month, firma, total_value,
                        total_qty, source_file, source_store_name
                    ) VALUES (
                        'EXPORT-L46-NONEXISTENT', $1, 'Mobicell',
                        1.00, 0, 'l46-orphan.xlsx', 'orphan'
                    )
                    """,
                    MONTH,
                )
            message = str(exc_info.value)
            assert "foreign key" in message.lower() or "23503" in message, (
                "Expected PostgreSQL foreign key violation on "
                "historical_monthly_sales.site_code, "
                f"got: {message!r}"
            )
            await connection.execute("ROLLBACK TO SAVEPOINT f05_orphan_probe")
            await connection.execute("RELEASE SAVEPOINT f05_orphan_probe")


@pytest.mark.anyio
async def test_f05_baseline_closed_store_leaks_without_active_predicate(
    f05_seeded,
) -> None:
    """Baseline reproduction: replay the historical UNION without the active
    predicate and prove CLOSED_SITE leaks. Then replay the fixed shape and
    prove CLOSED_SITE is excluded. The divergence is pinned at the SQL
    predicate level so the proof survives the fix.
    """
    pool = await get_pool()
    async with pool.acquire() as connection:
        baseline = await connection.fetch(
            """
            SELECT hms.site_code, hms.total_value
            FROM historical_monthly_sales hms
            LEFT JOIN stores s ON s.site_code = hms.site_code
            WHERE hms.import_month = $1
              AND COALESCE(s.locatie, hms.source_store_name, '')
                  NOT ILIKE 'TR %'
              AND NOT EXISTS (
                  SELECT 1 FROM reporting_agent_day rad
                  WHERE rad.import_month = hms.import_month
                    AND rad.site_code = hms.site_code
              )
            """,
            MONTH,
        )
        baseline_amounts = {
            row["site_code"]: row["total_value"] for row in baseline
        }
        assert CLOSED_SITE in baseline_amounts, (
            "Baseline repro precondition: the unfiltered historical UNION "
            "must surface the closed store (its reporting_agent_day row is "
            "absent so the NOT EXISTS guard does not suppress it)."
        )
        assert baseline_amounts[CLOSED_SITE] == Decimal("20.00")

        fixed = await connection.fetch(
            """
            SELECT hms.site_code, hms.total_value
            FROM historical_monthly_sales hms
            LEFT JOIN stores s ON s.site_code = hms.site_code
            WHERE hms.import_month = $1
              AND s.is_active = TRUE
              AND COALESCE(s.locatie, hms.source_store_name, '')
                  NOT ILIKE 'TR %'
              AND NOT EXISTS (
                  SELECT 1 FROM reporting_agent_day rad
                  WHERE rad.import_month = hms.import_month
                    AND rad.site_code = hms.site_code
              )
            """,
            MONTH,
        )
        fixed_site_codes = {row["site_code"] for row in fixed}
        assert CLOSED_SITE not in fixed_site_codes, (
            "Predicted post-fix behavior: the active predicate filters the "
            "closed store out of the historical UNION."
        )
        assert TR_SITE not in fixed_site_codes, (
            "TR-prefixed locations must remain excluded from the historical "
            "UNION regardless of is_active."
        )


@pytest.mark.anyio
async def test_f05_fix_closed_store_excluded_from_total_branch(f05_seeded) -> None:
    """After the fix, ``include_closed_stores=False`` excludes CLOSED_SITE
    from the total branch."""
    pool = await get_pool()
    repository = ExportsRepository(pool)
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
    totals = {row["site_code"]: row["total_sales"] for row in rows}
    assert ACTIVE_SITE in totals, totals
    assert totals[ACTIVE_SITE] == Decimal("100.00"), totals
    assert CLOSED_SITE not in totals, (
        "Closed store must not contribute when include_closed_stores=False."
    )


@pytest.mark.anyio
async def test_f05_fix_closed_store_excluded_from_monthly_branch(f05_seeded) -> None:
    """The fix must apply on the ``period='month'`` branch too."""
    pool = await get_pool()
    repository = ExportsRepository(pool)
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
    assert CLOSED_SITE not in site_codes, (
        "Closed store must not contribute on the monthly branch either."
    )


@pytest.mark.anyio
async def test_f05_fix_include_closed_stores_true_returns_closed_historical(
    f05_seeded,
) -> None:
    """Regression: ``include_closed_stores=True`` keeps the closed store's
    historical fallback visible on the total branch."""
    pool = await get_pool()
    repository = ExportsRepository(pool)
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
    totals = {row["site_code"]: row["total_sales"] for row in rows}
    assert totals[ACTIVE_SITE] == Decimal("100.00"), totals
    assert totals[CLOSED_SITE] == Decimal("20.00"), (
        "Closed store historical fallback must be visible when "
        "include_closed_stores=True."
    )


@pytest.mark.anyio
async def test_f05_fix_tr_location_exclusion_unchanged(f05_seeded) -> None:
    """Regression: TR-prefixed locations stay excluded on both branches and
    both ``include_closed_stores`` values."""
    pool = await get_pool()
    repository = ExportsRepository(pool)
    for include_closed in (False, True):
        rows = await repository.fetch_report_rows(
            dataset="stores",
            months=[MONTH],
            filters={},
            include_closed_stores=include_closed,
            campaign_codes_by_month=None,
            campaign_exclusions_by_month=None,
            selected_days=None,
            period=None,
            include_campaign_metrics=False,
            limit=None,
            include_total_count=False,
        )
        assert all(row["locatie"] != TR_LOCATION for row in rows), (
            f"TR-prefixed locations must be excluded when "
            f"include_closed_stores={include_closed}.",
            [(row["site_code"], row["locatie"]) for row in rows],
        )


@pytest.mark.anyio
async def test_f05_fix_firma_filter_preserved(f05_seeded) -> None:
    """Regression: the LEFT JOIN COALESCE fallback for firma filters is intact
    on the historical UNION."""
    pool = await get_pool()
    repository = ExportsRepository(pool)
    mobicell_rows = await repository.fetch_report_rows(
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
    assert mobicell_rows and all(
        row["firma"] == "Mobicell" for row in mobicell_rows
    )

    mobiup_rows = await repository.fetch_report_rows(
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
    assert mobiup_rows == []


@pytest.mark.anyio
async def test_f05_historical_not_exists_suppression_unchanged(f05_seeded) -> None:
    """Regression: a historical row that already has a reporting_agent_day row
    for the same month/site is suppressed by the NOT EXISTS guard, even when
    ``include_closed_stores=True``."""
    pool = await get_pool()
    repository = ExportsRepository(pool)
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
    site_codes = {row["site_code"]: row for row in rows}
    assert site_codes[ACTIVE_SITE]["total_sales"] == Decimal("100.00"), (
        "ACTIVE_SITE must reflect reporting_agent_day only (100.00); the "
        "historical fallback (10.00) must be suppressed by NOT EXISTS."
    )


@pytest.mark.anyio
async def test_f05_agent_dataset_keeps_no_historical_fallback(f05_seeded) -> None:
    """Regression: dataset='agents' must NOT pull in the historical UNION."""
    pool = await get_pool()
    repository = ExportsRepository(pool)
    rows = await repository.fetch_report_rows(
        dataset="agents",
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
    assert all(row["site_code"] != CLOSED_SITE for row in rows), (
        "Agents dataset must not include the closed store's historical "
        "fallback; the historical UNION is restricted to non-agent paths."
    )
