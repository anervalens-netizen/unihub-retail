"""Lot 23 PostgreSQL proof for the materialized return-receipt read model.

The Dashboard used to rescan raw ``sales_transactions`` for every return
summary.  Lot 23 materializes the canonical return-receipt count at the
reporting grain instead.  This module proves, against the disposable database
created by ``run_tests_isolated.sh``:

* migration 074 backfill equals a fresh ``rebuild_reporting_month()``;
* the day model carries the canonical receipt count and the month model is its
  day-model sum;
* duplicate item rows on one receipt contribute one, while the same receipt
  number on different canonical dimensions stays additive;
* cartela and ``TR `` rows contribute zero;
* History, Store, Agent and Regional return outputs still match the pre-change
  raw-transaction semantics.
"""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path

import asyncpg
import pytest

from db.connection import get_pool
from repositories.dashboard import DashboardRepository
from services.dashboard.history import load_monthly_history
from services.dashboard.queries import (
    _fetch_agent_stats_rows,
    _fetch_regional_stats,
    _fetch_store_stats_rows,
)
from services.dashboard_service import DashboardService
from services.receipt_identity import canonical_receipt_identity_sql
from services.reporting_refresh_month import rebuild_reporting_month

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]

_MONTH = "2099-10"
_SITE_A = "L23-A"
_SITE_B = "L23-B"
_SITE_TR = "L23-TR"
_REGIONAL = "L23 Regional"
_ASM = "L23 ASM"
_AGENT_A = "L23 Agent A"
_AGENT_B = "L23 Agent B"

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "074_v3_reporting_return_receipt_count.sql"
)

# Canonical day-grain expectation for the fixture below.
_EXPECTED_DAY_RETURNS: dict[tuple[date, str, str], int] = {
    (date(2099, 10, 1), _SITE_A, _AGENT_A): 1,  # two item rows, one receipt
    (date(2099, 10, 2), _SITE_A, _AGENT_A): 1,  # same bon_nr, other day
    (date(2099, 10, 3), _SITE_A, _AGENT_A): 1,  # distinct receipt
    (date(2099, 10, 1), _SITE_A, _AGENT_B): 1,  # same bon_nr, other agent
    (date(2099, 10, 1), _SITE_B, _AGENT_A): 1,  # same bon_nr, other site
}
_EXPECTED_MONTH_RETURNS: dict[tuple[str, str], int] = {
    (_SITE_A, _AGENT_A): 3,
    (_SITE_A, _AGENT_B): 1,
    (_SITE_B, _AGENT_A): 1,
}


class _HistoryServiceShim(DashboardService):
    """History-only double: the real service surface bound to the test pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        super().__init__(DashboardRepository(pool), pool)


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM sales_transactions WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_day WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_month WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM import_snapshots WHERE import_month = $1", _MONTH)
    await conn.execute(
        "DELETE FROM stores WHERE site_code = ANY($1::TEXT[])",
        [_SITE_A, _SITE_B, _SITE_TR],
    )


async def _sale(
    conn: asyncpg.Connection,
    snapshot_id: int,
    *,
    day: int,
    site: str,
    agent: str,
    bon: str,
    item: str,
    quantity: int = -1,
    cartela: bool = False,
) -> None:
    await conn.execute(
        """
        INSERT INTO sales_transactions
            (import_month, sale_date, site_code, bon_nr, item_code, item_name,
             quantity, unit_price, total_value, agent, is_cartela, is_return,
             snapshot_id)
        VALUES
            ($1, $2, $3, $4, $5, 'Lot23 item', $6, 10, $6 * 10,
             $7, $8, $6 < 0, $9)
        """,
        _MONTH,
        date(2099, 10, day),
        site,
        bon,
        item,
        quantity,
        agent,
        cartela,
        snapshot_id,
    )


async def _seed(conn: asyncpg.Connection) -> int:
    await conn.execute(
        """
        INSERT INTO stores
            (site_code, locatie, firma, regional, asm, is_active,
             first_seen_month, last_seen_month)
        VALUES
            ($1, 'Lot23 Retail A', 'Mobiup', $4, $5, true,  $6, $6),
            ($2, 'Lot23 Retail B', 'Mobiup', $4, $5, true,  $6, $6),
            ($3, 'TR Lot23 Distribution', 'Mobiup', $4, $5, true, $6, $6)
        """,
        _SITE_A,
        _SITE_B,
        _SITE_TR,
        _REGIONAL,
        _ASM,
        _MONTH,
    )
    snapshot = await conn.fetchrow(
        """
        INSERT INTO import_snapshots
            (import_month, filename, is_month_final, status)
        VALUES ($1, 'v3-lot23-fixture.xlsx', true, 'completed')
        RETURNING id
        """,
        _MONTH,
    )
    assert snapshot is not None
    snapshot_id = int(snapshot["id"])

    # One receipt with two negative item rows: must contribute exactly one.
    await _sale(conn, snapshot_id, day=1, site=_SITE_A, agent=_AGENT_A, bon="BON-DUP", item="D1")
    await _sale(conn, snapshot_id, day=1, site=_SITE_A, agent=_AGENT_A, bon="BON-DUP", item="D2")

    # The same bon_nr on a different canonical dimension stays additive.
    await _sale(conn, snapshot_id, day=2, site=_SITE_A, agent=_AGENT_A, bon="BON-DUP", item="D3")
    await _sale(conn, snapshot_id, day=1, site=_SITE_B, agent=_AGENT_A, bon="BON-DUP", item="D4")
    await _sale(conn, snapshot_id, day=1, site=_SITE_A, agent=_AGENT_B, bon="BON-DUP", item="D5")

    # Plain control receipt.
    await _sale(conn, snapshot_id, day=3, site=_SITE_A, agent=_AGENT_A, bon="BON-CTRL", item="C1")

    # Non-contributing rows: cartela, distribution location, positive quantity.
    await _sale(
        conn, snapshot_id, day=4, site=_SITE_A, agent=_AGENT_A, bon="BON-CART", item="K1", cartela=True
    )
    await _sale(conn, snapshot_id, day=1, site=_SITE_TR, agent=_AGENT_A, bon="BON-TR", item="T1")
    await _sale(
        conn, snapshot_id, day=5, site=_SITE_A, agent=_AGENT_A, bon="BON-POS", item="P1", quantity=1
    )
    return snapshot_id


async def _materialized_day_returns(
    conn: asyncpg.Connection,
) -> dict[tuple[date, str, str], int]:
    rows = await conn.fetch(
        """
        SELECT sale_date, site_code, agent, return_receipt_count
        FROM reporting_agent_day
        WHERE import_month = $1
        """,
        _MONTH,
    )
    return {
        (row["sale_date"], row["site_code"], row["agent"]): int(row["return_receipt_count"])
        for row in rows
        if int(row["return_receipt_count"]) > 0
    }


async def _materialized_month_returns(
    conn: asyncpg.Connection,
) -> dict[tuple[str, str], int]:
    rows = await conn.fetch(
        """
        SELECT site_code, agent, return_receipt_count
        FROM reporting_agent_month
        WHERE import_month = $1
        """,
        _MONTH,
    )
    return {
        (row["site_code"], row["agent"]): int(row["return_receipt_count"])
        for row in rows
        if int(row["return_receipt_count"]) > 0
    }


async def _raw_day_returns(conn: asyncpg.Connection) -> dict[tuple[date, str, str], int]:
    """Independent raw-transaction computation at the reporting day grain."""

    rows = await conn.fetch(
        """
        SELECT
            st.sale_date,
            st.site_code,
            st.agent,
            COUNT(DISTINCT st.bon_nr)::INT AS return_receipt_count
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        WHERE st.import_month = $1
          AND s.locatie NOT ILIKE 'TR %'
          AND NOT st.is_cartela
          AND st.quantity < 0
          AND st.bon_nr IS NOT NULL
        GROUP BY st.sale_date, st.site_code, st.agent
        """,
        _MONTH,
    )
    return {
        (row["sale_date"], row["site_code"], row["agent"]): int(row["return_receipt_count"])
        for row in rows
    }


_PRE_CHANGE_GROUP_SQL: dict[str, tuple[str, tuple[str, ...]]] = {
    "history": ("st.import_month", ("import_month",)),
    "store": ("st.site_code", ("site_code",)),
    "agent": ("st.site_code, st.agent", ("site_code", "agent")),
    "regional": ("s.regional", ("regional",)),
}


async def _pre_change_dashboard_returns(
    conn: asyncpg.Connection, level: str
) -> dict[tuple[object, ...], int]:
    """Reproduce the pre-Lot-23 return summary from raw transactions.

    These four shapes are exactly the raw ``return_summary`` CTEs the Dashboard
    used before the counts were materialized.
    """

    identity = canonical_receipt_identity_sql("st")
    group_sql, key_columns = _PRE_CHANGE_GROUP_SQL[level]
    rows = await conn.fetch(
        f"""
        SELECT
            {group_sql},
            COUNT(DISTINCT {identity})
                FILTER (
                    WHERE st.quantity < 0
                      AND st.bon_nr IS NOT NULL
                )::INT AS return_receipt_count
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        WHERE st.import_month = $1
          AND NOT st.is_cartela
          AND st.quantity < 0
          AND st.bon_nr IS NOT NULL
          AND s.locatie NOT ILIKE 'TR %'
        GROUP BY {group_sql}
        """,
        _MONTH,
    )
    return {
        tuple(row[column] for column in key_columns): int(row["return_receipt_count"])
        for row in rows
    }


async def _run_migration_074(conn: asyncpg.Connection) -> None:
    await conn.execute(_MIGRATION_PATH.read_text(encoding="utf-8"))


async def test_lot23_refresh_materializes_canonical_day_and_month_counts() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        try:
            await _seed(conn)

            await rebuild_reporting_month(conn, _MONTH)

            # 1 + 2: duplicate item rows count once, the same bon_nr on a
            # different day/site/agent stays additive.
            # 3 + 4: cartela and TR rows contribute nothing.
            day_returns = await _materialized_day_returns(conn)
            assert day_returns == _EXPECTED_DAY_RETURNS
            assert day_returns == await _raw_day_returns(conn)

            # 5: the day model carries the correct count and keeps zero rows.
            zero_rows = await conn.fetchval(
                """
                SELECT COUNT(*)::INT
                FROM reporting_agent_day
                WHERE import_month = $1
                  AND site_code = $2
                  AND agent = $3
                  AND sale_date = DATE '2099-10-05'
                  AND return_receipt_count = 0
                """,
                _MONTH,
                _SITE_A,
                _AGENT_A,
            )
            assert zero_rows == 1
            assert await conn.fetchval(
                """
                SELECT COUNT(*)::INT
                FROM reporting_agent_day
                WHERE import_month = $1
                  AND site_code = ANY($2::TEXT[])
                  AND return_receipt_count <> 0
                """,
                _MONTH,
                [_SITE_TR],
            ) == 0

            # 6: the month model is exactly the day-model sum.
            month_returns = await _materialized_month_returns(conn)
            assert month_returns == _EXPECTED_MONTH_RETURNS
            day_sums: dict[tuple[str, str], int] = {}
            for (_day, site, agent), count in day_returns.items():
                day_sums[(site, agent)] = day_sums.get((site, agent), 0) + count
            assert day_sums == month_returns
            assert await conn.fetchval(
                """
                SELECT COALESCE(SUM(return_receipt_count), 0)::INT
                FROM reporting_agent_month
                WHERE import_month = $1
                """,
                _MONTH,
            ) == sum(_EXPECTED_MONTH_RETURNS.values())
        finally:
            await _cleanup(conn)


async def test_lot23_migration_backfill_matches_fresh_rebuild() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        try:
            await _seed(conn)
            await rebuild_reporting_month(conn, _MONTH)
            expected_day = await _materialized_day_returns(conn)
            expected_month = await _materialized_month_returns(conn)
            assert expected_day == _EXPECTED_DAY_RETURNS
            assert expected_month == _EXPECTED_MONTH_RETURNS

            # Simulate a database that already has reporting rows but predates
            # migration 074: both columns exist and are still zero.
            await conn.execute(
                "UPDATE reporting_agent_day SET return_receipt_count = 0 WHERE import_month = $1",
                _MONTH,
            )
            await conn.execute(
                "UPDATE reporting_agent_month SET return_receipt_count = 0 WHERE import_month = $1",
                _MONTH,
            )
            assert await _materialized_day_returns(conn) == {}
            assert await _materialized_month_returns(conn) == {}

            await _run_migration_074(conn)

            assert await _materialized_day_returns(conn) == expected_day
            assert await _materialized_month_returns(conn) == expected_month

            # The backfill is idempotent.
            await _run_migration_074(conn)
            assert await _materialized_day_returns(conn) == expected_day
            assert await _materialized_month_returns(conn) == expected_month

            # A fresh rebuild after the backfill produces exactly the same rows.
            await rebuild_reporting_month(conn, _MONTH)
            assert await _materialized_day_returns(conn) == expected_day
            assert await _materialized_month_returns(conn) == expected_month
        finally:
            await _cleanup(conn)


async def test_lot23_dashboard_return_outputs_match_pre_change_semantics() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        try:
            await _seed(conn)
            await rebuild_reporting_month(conn, _MONTH)

            expected_history = await _pre_change_dashboard_returns(conn, "history")
            expected_store = await _pre_change_dashboard_returns(conn, "store")
            expected_agent = await _pre_change_dashboard_returns(conn, "agent")
            expected_regional = await _pre_change_dashboard_returns(conn, "regional")
            assert expected_history == {(_MONTH,): 5}
            assert expected_store == {(_SITE_A,): 4, (_SITE_B,): 1}
            assert expected_agent == {
                (site, agent): count for (site, agent), count in _EXPECTED_MONTH_RETURNS.items()
            }
            assert expected_regional == {(_REGIONAL,): 5}

            service = _HistoryServiceShim(pool)
            history = await load_monthly_history(
                service, _MONTH, 1, None, None, None, None, None,
                current_scope=False,
            )
            assert {
                row.month: row.return_receipt_count for row in history.history
            } == {_MONTH: 5}

            stores = await _fetch_store_stats_rows(
                conn, _MONTH, None, None, None, None, None
            )
            assert {
                (row["site_code"],): row["return_receipt_count"] for row in stores
            } == expected_store

            agents = await _fetch_agent_stats_rows(
                conn, _MONTH, None, None, None, None, None
            )
            assert {
                (row["site_code"], row["agent"]): row["return_receipt_count"]
                for row in agents
            } == expected_agent

            regional = await _fetch_regional_stats(
                conn, _MONTH, None, None, None, None, None
            )
            assert {
                (row["regional"],): row["return_receipt_count"] for row in regional
            } == expected_regional

            # Filtered slices keep the same pre-change semantics.
            filtered = await _fetch_agent_stats_rows(
                conn, _MONTH, None, None, None, _SITE_B, _AGENT_A
            )
            assert [
                (row["site_code"], row["agent"], row["return_receipt_count"])
                for row in filtered
            ] == [(_SITE_B, _AGENT_A, 1)]
        finally:
            await _cleanup(conn)
