"""PostgreSQL regression coverage for audit finding H-03.

This test uses the disposable database created by run_tests_isolated.sh. It
proves that receipt numbers alone collide across business dimensions and that
the real Dashboard history, store, agent and regional queries expose the
canonical return-receipt count.
"""
from __future__ import annotations

from datetime import date
import os

import asyncpg
import pytest

from db.connection import get_pool
from repositories.dashboard import DashboardRepository
from services.dashboard.queries import (
    _fetch_agent_stats_rows,
    _fetch_regional_stats,
    _fetch_store_stats_rows,
)
from services.receipt_identity import canonical_receipt_identity_sql


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]

_MONTH = "2099-11"
_SITE_A = "H03-A"
_SITE_B = "H03-B"
_REGIONAL = "H03 Regional"
_AGENT_A = "H03 Agent A"
_AGENT_B = "H03 Agent B"


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM sales_transactions WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_day WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_month WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM import_snapshots WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM stores WHERE site_code IN ($1, $2)", _SITE_A, _SITE_B)


async def _seed_dashboard_rows(conn: asyncpg.Connection) -> int:
    await conn.execute(
        """
        INSERT INTO stores (site_code, locatie, firma, regional, asm, is_active, first_seen_month, last_seen_month)
        VALUES
            ($1, 'H03 Store A', 'Mobiup', $3, $3, true, $4, $4),
            ($2, 'H03 Store B', 'Mobiup', $3, $3, true, $4, $4)
        """,
        _SITE_A,
        _SITE_B,
        _REGIONAL,
        _MONTH,
    )
    snapshot = await conn.fetchrow(
        """
        INSERT INTO import_snapshots (import_month, filename, is_month_final, status)
        VALUES ($1, 'h03-fixture.xlsx', true, 'completed')
        RETURNING id
        """,
        _MONTH,
    )
    assert snapshot is not None

    await conn.execute(
        """
        INSERT INTO reporting_agent_day
            (import_month, sale_date, site_code, locatie, firma, regional, asm, agent,
             total_sales, total_quantity, focus_quantity, receipt_count, receipt_2plus_count,
             receipt_1_count, receipt_2_count, receipt_3_count, receipt_4plus_count)
        VALUES
            ($1, DATE '2099-11-01', $2, 'H03 Store A', 'Mobiup', $4, $4, $5, 100, 1, 0, 1, 0, 1, 0, 0, 0),
            ($1, DATE '2099-11-01', $2, 'H03 Store A', 'Mobiup', $4, $4, $6, 100, 1, 0, 1, 0, 1, 0, 0, 0),
            ($1, DATE '2099-11-01', $3, 'H03 Store B', 'Mobiup', $4, $4, $5, 100, 1, 0, 1, 0, 1, 0, 0, 0)
        """,
        _MONTH,
        _SITE_A,
        _SITE_B,
        _REGIONAL,
        _AGENT_A,
        _AGENT_B,
    )
    await conn.execute(
        """
        INSERT INTO reporting_agent_month
            (import_month, site_code, locatie, firma, regional, asm, agent,
             total_sales, total_quantity, focus_quantity, receipt_count, receipt_2plus_count,
             receipt_1_count, receipt_2_count, receipt_3_count, receipt_4plus_count, working_days)
        VALUES
            ($1, $2, 'H03 Store A', 'Mobiup', $4, $4, $5, 100, 1, 0, 1, 0, 1, 0, 0, 0, 1),
            ($1, $2, 'H03 Store A', 'Mobiup', $4, $4, $6, 100, 1, 0, 1, 0, 1, 0, 0, 0, 1),
            ($1, $3, 'H03 Store B', 'Mobiup', $4, $4, $5, 100, 1, 0, 1, 0, 1, 0, 0, 0, 1)
        """,
        _MONTH,
        _SITE_A,
        _SITE_B,
        _REGIONAL,
        _AGENT_A,
        _AGENT_B,
    )
    return int(snapshot["id"])


async def _insert_return(
    conn: asyncpg.Connection,
    snapshot_id: int,
    *,
    sale_date: date,
    site_code: str,
    agent: str,
    bon_nr: str,
    item_code: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO sales_transactions
            (import_month, sale_date, site_code, bon_nr, item_code, item_name,
             quantity, unit_price, total_value, agent, is_cartela, is_return, snapshot_id)
        VALUES ($1, $2, $3, $4, $5, 'H03 return item', -1, 10, -10, $6, false, true, $7)
        """,
        _MONTH,
        sale_date,
        site_code,
        bon_nr,
        item_code,
        agent,
        snapshot_id,
    )


async def _assert_null_receipt_number_is_ignored(conn: asyncpg.Connection) -> None:
    """Exercise the NULL edge case without weakening the production schema."""

    identity = canonical_receipt_identity_sql("st")
    count = await conn.fetchval(
        f"""
        WITH st(sale_date, site_code, agent, bon_nr, quantity) AS (
            VALUES ($1::DATE, $2::TEXT, $3::TEXT, NULL::TEXT, -1::INTEGER)
        )
        SELECT COUNT(DISTINCT {identity})
            FILTER (WHERE st.quantity < 0 AND st.bon_nr IS NOT NULL)
        FROM st
        """,
        date(2099, 11, 3),
        _SITE_A,
        _AGENT_A,
    )
    assert count == 0


async def test_h03_canonical_identity_is_used_by_all_return_receipt_queries() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        try:
            snapshot_id = await _seed_dashboard_rows(conn)

            # Same number and same dimensions on two item rows: one receipt.
            await _insert_return(
                conn,
                snapshot_id,
                sale_date=date(2099, 11, 1),
                site_code=_SITE_A,
                agent=_AGENT_A,
                bon_nr="H03-SHARED",
                item_code="A1",
            )
            await _insert_return(
                conn,
                snapshot_id,
                sale_date=date(2099, 11, 1),
                site_code=_SITE_A,
                agent=_AGENT_A,
                bon_nr="H03-SHARED",
                item_code="A2",
            )

            # Same number but changed date, store and agent: three more receipts.
            await _insert_return(
                conn,
                snapshot_id,
                sale_date=date(2099, 11, 2),
                site_code=_SITE_A,
                agent=_AGENT_A,
                bon_nr="H03-SHARED",
                item_code="A3",
            )
            await _insert_return(
                conn,
                snapshot_id,
                sale_date=date(2099, 11, 1),
                site_code=_SITE_B,
                agent=_AGENT_A,
                bon_nr="H03-SHARED",
                item_code="B1",
            )
            await _insert_return(
                conn,
                snapshot_id,
                sale_date=date(2099, 11, 1),
                site_code=_SITE_A,
                agent=_AGENT_B,
                bon_nr="H03-SHARED",
                item_code="A4",
            )
            await _insert_return(
                conn,
                snapshot_id,
                sale_date=date(2099, 11, 3),
                site_code=_SITE_A,
                agent=_AGENT_A,
                bon_nr="H03-CONTROL",
                item_code="A5",
            )
            await _assert_null_receipt_number_is_ignored(conn)

            identity = canonical_receipt_identity_sql("st")
            counts = await conn.fetchrow(
                f"""
                SELECT
                    COUNT(DISTINCT st.bon_nr) FILTER (WHERE st.quantity < 0) AS legacy_count,
                    COUNT(DISTINCT {identity})
                        FILTER (WHERE st.quantity < 0 AND st.bon_nr IS NOT NULL) AS canonical_count
                FROM sales_transactions st
                WHERE st.import_month = $1
                """,
                _MONTH,
            )
            assert counts is not None
            assert counts["legacy_count"] == 2
            assert counts["canonical_count"] == 5

            history = await DashboardRepository(pool).fetch_monthly_history([], [_MONTH, 1])
            assert history
            assert history[0]["return_receipt_count"] == 5

            stores = await _fetch_store_stats_rows(
                conn, _MONTH, None, None, None, None, None
            )
            assert {
                row["site_code"]: row["return_receipt_count"] for row in stores
            } == {_SITE_A: 4, _SITE_B: 1}

            agents = await _fetch_agent_stats_rows(
                conn, _MONTH, None, None, None, None, None
            )
            assert {
                (row["site_code"], row["agent"]): row["return_receipt_count"]
                for row in agents
            } == {
                (_SITE_A, _AGENT_A): 3,
                (_SITE_A, _AGENT_B): 1,
                (_SITE_B, _AGENT_A): 1,
            }

            regional = await _fetch_regional_stats(
                conn, _MONTH, None, None, None, None, None
            )
            assert [
                (row["regional"], row["return_receipt_count"])
                for row in regional
            ] == [(_REGIONAL, 5)]
        finally:
            await _cleanup(conn)
