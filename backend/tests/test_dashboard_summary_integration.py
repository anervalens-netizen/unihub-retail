"""Integration tests for DashboardRepository.fetch_summary cartela CTE and forecast math.

These tests seed a real isolated PostgreSQL database and assert that:
- Cartele rows do NOT contaminate Retail KPI totals (total_sales, total_quantity).
- cartele_qty is populated separately from raw sales_transactions (is_cartela = true).
- Cartela cohort respects site_code scope.
- Forecast math is correct for partial months.
- Manager-scope OR-expansion applies to the cartela CTE (current_scope + regional).

Guarded by UNIHUB_TEST_DATABASE=1 so they only run under run_tests_isolated.sh.
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import pytest

import asyncpg

from db.connection import close_db_pool, get_pool
from repositories.dashboard import DashboardRepository
from services.filters import build_scoped_params, scoped_clauses


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]

_TEST_MONTH = "2099-05"
_SITE_A = "TEST-A"
_SITE_B = "TEST-B"


async def _seed_stores(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO stores (site_code, locatie, firma, regional, asm, is_active, first_seen_month, last_seen_month)
        VALUES
            ($1, 'Test Park Lake', 'Mobiup', 'Andrei Stancu', 'Andrei Stancu', true, $3, $3),
            ($2, 'Test Mall Vitan', 'Mobicell', 'Andrei Stancu', 'Mihai Condorateanu', true, $3, $3)
        ON CONFLICT (site_code) DO NOTHING
        """,
        _SITE_A,
        _SITE_B,
        _TEST_MONTH,
    )


async def _seed_snapshot(conn: asyncpg.Connection, *, is_month_final: bool, period_end_day: int | None = None) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO import_snapshots (import_month, filename, is_month_final, status)
        VALUES ($1, 'test.xlsx', $2, 'completed')
        RETURNING id
        """,
        _TEST_MONTH,
        is_month_final,
    )
    snapshot_id = row["id"]
    if period_end_day is not None and not is_month_final:
        await conn.execute(
            "UPDATE import_snapshots SET heartbeat_at = now() WHERE id = $1",
            snapshot_id,
        )
    return snapshot_id


async def _seed_reporting_day(
    conn: asyncpg.Connection,
    *,
    site_code: str,
    day: int,
    total_sales: Decimal,
    total_quantity: int,
    agent: str = "Agent Test",
    locatie: str = "Test Loc",
    firma: str = "Mobiup",
    regional: str = "Andrei Stancu",
    asm: str = "Andrei Stancu",
) -> None:
    from datetime import date

    sale_date = date(2099, 5, day)
    await conn.execute(
        """
        INSERT INTO reporting_agent_day
            (import_month, sale_date, site_code, locatie, firma, regional, asm, agent,
             total_sales, total_quantity, focus_quantity, receipt_count, receipt_2plus_count,
             receipt_1_count, receipt_2_count, receipt_3_count, receipt_4plus_count)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8,
             $9, $10, 0, 1, 1, 0, 0, 0, 0)
        ON CONFLICT (import_month, sale_date, site_code, agent) DO NOTHING
        """,
        _TEST_MONTH,
        sale_date,
        site_code,
        locatie,
        firma,
        regional,
        asm,
        agent,
        total_sales,
        total_quantity,
    )


async def _seed_cartela_tx(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    site_code: str,
    quantity: int,
    day: int = 1,
) -> None:
    from datetime import date

    sale_date = date(2099, 5, day)
    await conn.execute(
        """
        INSERT INTO sales_transactions
            (import_month, sale_date, site_code, bon_nr, item_code, item_name,
             quantity, unit_price, total_value, agent, is_cartela, is_return, snapshot_id)
        VALUES
            ($1, $2, $3, 'BON-CARTELA-1', 'CARTELA', 'Cartela telefon',
             $4, 10.00, $5, 'Agent Test', true, false, $6)
        """,
        _TEST_MONTH,
        sale_date,
        site_code,
        quantity,
        Decimal(quantity) * Decimal("10.00"),
        snapshot_id,
    )


async def _seed_retail_tx(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    site_code: str,
    quantity: int,
    day: int = 1,
) -> None:
    from datetime import date

    sale_date = date(2099, 5, day)
    await conn.execute(
        """
        INSERT INTO sales_transactions
            (import_month, sale_date, site_code, bon_nr, item_code, item_name,
             quantity, unit_price, total_value, agent, is_cartela, is_return, snapshot_id)
        VALUES
            ($1, $2, $3, 'BON-RETAIL-1', 'HUSA', 'Husa telefon',
             $4, 20.00, $5, 'Agent Test', false, false, $6)
        """,
        _TEST_MONTH,
        sale_date,
        site_code,
        quantity,
        Decimal(quantity) * Decimal("20.00"),
        snapshot_id,
    )


async def _seed_target(conn: asyncpg.Connection, *, site_code: str, target_value: Decimal) -> None:
    await conn.execute(
        """
        INSERT INTO store_targets (import_month, site_code, target_value)
        VALUES ($1, $2, $3)
        ON CONFLICT (import_month, site_code) DO NOTHING
        """,
        _TEST_MONTH,
        site_code,
        target_value,
    )


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM sales_transactions WHERE import_month = $1", _TEST_MONTH)
    await conn.execute("DELETE FROM reporting_agent_day WHERE import_month = $1", _TEST_MONTH)
    await conn.execute("DELETE FROM store_targets WHERE import_month = $1", _TEST_MONTH)
    await conn.execute("DELETE FROM import_snapshots WHERE import_month = $1", _TEST_MONTH)
    await conn.execute("DELETE FROM stores WHERE site_code IN ($1, $2)", _SITE_A, _SITE_B)
    await conn.execute("DELETE FROM stores WHERE site_code = 'TR-DEPOT'")


def _build_clauses_no_scope(month: str) -> tuple[list[str], list[str], list[Any]]:
    params, positions = build_scoped_params([month], firma=None, regional=None, asm=None, site_code=None, agent=None)
    clauses = scoped_clauses(
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
    )
    cartela_clauses = scoped_clauses(
        positions,
        site_alias="c",
        store_alias="cs",
        agent_alias="c",
    )
    return clauses, cartela_clauses, params


async def test_cartela_does_not_contaminate_retail_totals() -> None:
    """Cartele rows in sales_transactions must NOT inflate total_sales / total_quantity."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        await _seed_stores(conn)
        snapshot_id = await _seed_snapshot(conn, is_month_final=True)

        await _seed_reporting_day(conn, site_code=_SITE_A, day=1, total_sales=Decimal("1000.00"), total_quantity=5)
        await _seed_cartela_tx(conn, snapshot_id=snapshot_id, site_code=_SITE_A, quantity=8)
        await _seed_target(conn, site_code=_SITE_A, target_value=Decimal("2000.00"))

        try:
            clauses, cartela_clauses, params = _build_clauses_no_scope(_TEST_MONTH)
            repo = DashboardRepository(pool)
            row = await repo.fetch_summary(clauses, params, cartela_clauses, current_scope=False)

            assert row is not None, "fetch_summary returned None"
            assert row["total_sales"] == Decimal("1000.00"), f"total_sales should be 1000 (Retail only), got {row['total_sales']}"
            assert row["total_quantity"] == 5, f"total_quantity should be 5 (Retail only), got {row['total_quantity']}"
            assert row["cartele_qty"] == 8, f"cartele_qty should be 8 (separate), got {row['cartele_qty']}"
        finally:
            await _cleanup(conn)


async def test_cartela_respects_site_code_scope() -> None:
    """When site_code is scoped, cartele_qty must only count that site's cartela."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        await _seed_stores(conn)
        snapshot_id = await _seed_snapshot(conn, is_month_final=True)

        await _seed_reporting_day(conn, site_code=_SITE_A, day=1, total_sales=Decimal("500.00"), total_quantity=3)
        await _seed_reporting_day(conn, site_code=_SITE_B, day=1, total_sales=Decimal("800.00"), total_quantity=4)
        await _seed_cartela_tx(conn, snapshot_id=snapshot_id, site_code=_SITE_A, quantity=8)
        await _seed_cartela_tx(conn, snapshot_id=snapshot_id, site_code=_SITE_B, quantity=12)
        await _seed_target(conn, site_code=_SITE_A, target_value=Decimal("1000.00"))
        await _seed_target(conn, site_code=_SITE_B, target_value=Decimal("1000.00"))

        try:
            params, positions = build_scoped_params(
                [_TEST_MONTH], firma=None, regional=None, asm=None, site_code=_SITE_A, agent=None
            )
            clauses = scoped_clauses(
                positions,
                site_alias="agg",
                store_alias="agg",
                agent_alias="agg",
                month_alias="agg.import_month",
                month_position=1,
            )
            cartela_clauses = scoped_clauses(
                positions,
                site_alias="c",
                store_alias="cs",
                agent_alias="c",
            )
            repo = DashboardRepository(pool)
            row = await repo.fetch_summary(clauses, params, cartela_clauses, current_scope=False)

            assert row is not None
            assert row["cartele_qty"] == 8, f"cartele_qty should be 8 (SITE_A only), got {row['cartele_qty']}"
            assert row["total_sales"] == Decimal("500.00"), f"total_sales should be 500 (SITE_A), got {row['total_sales']}"
        finally:
            await _cleanup(conn)


async def test_forecast_math_partial_month() -> None:
    """For a partial month (is_month_final=false, last sale day=6, days_in_month=31):
    forecast_sales == total_sales / 6 * 31.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        await _seed_stores(conn)
        await _seed_snapshot(conn, is_month_final=False)

        await _seed_reporting_day(conn, site_code=_SITE_A, day=1, total_sales=Decimal("600.00"), total_quantity=10)
        for day in range(2, 7):
            await _seed_reporting_day(conn, site_code=_SITE_A, day=day, total_sales=Decimal("100.00"), total_quantity=1)
        await _seed_target(conn, site_code=_SITE_A, target_value=Decimal("10000.00"))

        try:
            clauses, cartela_clauses, params = _build_clauses_no_scope(_TEST_MONTH)
            repo = DashboardRepository(pool)
            row = await repo.fetch_summary(clauses, params, cartela_clauses, current_scope=False)

            assert row is not None
            assert row["is_month_final"] is False
            assert row["imported_day_of_month"] == 6, f"imported_day_of_month should be 6, got {row['imported_day_of_month']}"
            assert row["days_in_month"] == 31, f"days_in_month should be 31 (May), got {row['days_in_month']}"
            total_sales = row["total_sales"]
            expected_forecast = (total_sales / Decimal("6") * Decimal("31")).quantize(Decimal("0.01"))
            assert row["forecast_sales"] == expected_forecast, (
                f"forecast_sales should be {expected_forecast} (={total_sales}/6*31), got {row['forecast_sales']}"
            )
        finally:
            await _cleanup(conn)


async def test_manager_scope_or_expansion_applies_to_cartela() -> None:
    """When current_scope=True + regional selected (no asm/site), the cartela CTE must
    OR-match stores where the manager owns via ASM, not just RM. This is the subtility
    that _expand_current_manager_scope + the .replace() chain currently preserve.
    """
    from services.dashboard.utils import _expand_current_manager_scope

    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        await _seed_stores(conn)
        snapshot_id = await _seed_snapshot(conn, is_month_final=True)

        await _seed_reporting_day(conn, site_code=_SITE_A, day=1, total_sales=Decimal("1000.00"), total_quantity=5)
        await _seed_reporting_day(conn, site_code=_SITE_B, day=1, total_sales=Decimal("2000.00"), total_quantity=10)
        await _seed_cartela_tx(conn, snapshot_id=snapshot_id, site_code=_SITE_A, quantity=4)
        await _seed_cartela_tx(conn, snapshot_id=snapshot_id, site_code=_SITE_B, quantity=6)
        await _seed_target(conn, site_code=_SITE_A, target_value=Decimal("1000.00"))
        await _seed_target(conn, site_code=_SITE_B, target_value=Decimal("1000.00"))

        try:
            params, positions = build_scoped_params(
                [_TEST_MONTH], firma=None, regional="Andrei Stancu", asm=None, site_code=None, agent=None
            )
            clauses = scoped_clauses(
                positions,
                site_alias="agg",
                store_alias="s",
                agent_alias="agg",
                month_alias="agg.import_month",
                month_position=1,
            )
            clauses = _expand_current_manager_scope(clauses, positions)
            clauses.append("s.is_active = true")

            cartela_clauses = scoped_clauses(
                positions,
                site_alias="c",
                store_alias="cs",
                agent_alias="c",
            )
            cartela_clauses = _expand_current_manager_scope(
                cartela_clauses, positions, store_alias="cs"
            )
            cartela_clauses.append("cs.is_active = true")

            repo = DashboardRepository(pool)
            row = await repo.fetch_summary(clauses, params, cartela_clauses, current_scope=True)

            assert row is not None
            assert row["cartele_qty"] == 10, (
                f"cartele_qty should be 10 (both sites: SITE_A via RM + SITE_B via ASM), got {row['cartele_qty']}"
            )
            assert row["total_sales"] == Decimal("3000.00"), (
                f"total_sales should be 3000 (both sites via OR-expansion), got {row['total_sales']}"
            )
        finally:
            await _cleanup(conn)


async def test_tr_percent_locations_excluded_from_retail() -> None:
    """Stores with locatie LIKE 'TR %' must be excluded from Retail KPIs."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        await _seed_stores(conn)
        await conn.execute(
            """
            INSERT INTO stores (site_code, locatie, firma, regional, asm, is_active, first_seen_month, last_seen_month)
            VALUES ('TR-DEPOT', 'TR Depot Bucuresti', 'Mobiup', 'Andrei Stancu', 'Andrei Stancu', true, $1, $1)
            ON CONFLICT (site_code) DO NOTHING
            """,
            _TEST_MONTH,
        )
        snapshot_id = await _seed_snapshot(conn, is_month_final=True)
        await _seed_reporting_day(conn, site_code=_SITE_A, day=1, total_sales=Decimal("1000.00"), total_quantity=5)
        await _seed_reporting_day(
            conn,
            site_code="TR-DEPOT",
            day=1,
            total_sales=Decimal("5000.00"),
            total_quantity=20,
            locatie="TR Depot Bucuresti",
        )
        await _seed_target(conn, site_code=_SITE_A, target_value=Decimal("1000.00"))
        await _seed_target(conn, site_code="TR-DEPOT", target_value=Decimal("1000.00"))

        try:
            clauses, cartela_clauses, params = _build_clauses_no_scope(_TEST_MONTH)
            repo = DashboardRepository(pool)
            row = await repo.fetch_summary(clauses, params, cartela_clauses, current_scope=False)

            assert row is not None
            assert row["total_sales"] == Decimal("1000.00"), (
                f"total_sales should be 1000 (TR-DEPOT excluded), got {row['total_sales']}"
            )
            assert row["total_quantity"] == 5, (
                f"total_quantity should be 5 (TR-DEPOT excluded), got {row['total_quantity']}"
            )
        finally:
            await _cleanup(conn)
