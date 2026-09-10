"""Characterize return-receipt parity at the existing reporting grain.

Lot 22 is characterization-only.  The important distinction is between raw
transaction population and the real Dashboard scope policy.  Dashboard scope
always excludes distribution locations (``TR ``) and cartele; current scope may
also exclude inactive stores.  This test proves whether canonical return receipt
identity remains additive at the reporting-agent-day grain under those exact
row-selection semantics.

No production query or schema is changed by this test.
"""
from __future__ import annotations

from datetime import date
import os

import asyncpg
import pytest

from db.connection import get_pool
from repositories.dashboard import DashboardRepository
from retail_filters import retail_exclusion_clauses
from services.dashboard.history import load_monthly_history
from services.dashboard.queries import (
    _fetch_agent_stats_rows,
    _fetch_regional_stats,
    _fetch_store_stats_rows,
)
from services.dashboard.utils import _expand_current_manager_scope
from services.filters import build_scoped_params, scoped_clauses
from services.receipt_identity import canonical_receipt_identity_sql
from services.reporting_refresh_month import _REPORTING_MONTH_SQL_5


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]

_MONTH = "2099-12"
_RETAIL_SITE = "V3-L22-RETAIL"
_CLOSED_SITE = "V3-L22-CLOSED"
_TR_SITE = "V3-L22-TR"
_REGIONAL = "V3 Lot22 Regional"
_ASM = "V3 Lot22 ASM"
_AGENT_A = "V3 Lot22 Agent A"
_AGENT_B = "V3 Lot22 Agent B"
_AGENT_KEY_SQL = "COALESCE(NULLIF(BTRIM(st.agent), ''), '<unknown>')"


class _HistoryServiceShim:
    """Minimal service boundary needed to exercise load_monthly_history()."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.repo = DashboardRepository(pool)
        self._pool = pool

    def _pool_for(self, _deadline: object | None) -> asyncpg.Pool:
        return self._pool


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM sales_transactions WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_day WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_month WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM import_snapshots WHERE import_month = $1", _MONTH)
    await conn.execute(
        "DELETE FROM stores WHERE site_code = ANY($1::TEXT[])",
        [_RETAIL_SITE, _CLOSED_SITE, _TR_SITE],
    )


async def _seed_authority(conn: asyncpg.Connection) -> int:
    await conn.execute(
        """
        INSERT INTO stores
            (site_code, locatie, firma, regional, asm, is_active,
             first_seen_month, last_seen_month)
        VALUES
            ($1, 'Lot22 Retail', 'Mobiup', $4, $5, true,  $6, $6),
            ($2, 'Lot22 Closed', 'Mobiup', $4, $5, false, $6, $6),
            ($3, 'TR Lot22 Distribution', 'Mobiup', $4, $5, true, $6, $6)
        """,
        _RETAIL_SITE,
        _CLOSED_SITE,
        _TR_SITE,
        _REGIONAL,
        _ASM,
        _MONTH,
    )
    snapshot = await conn.fetchrow(
        """
        INSERT INTO import_snapshots
            (import_month, filename, is_month_final, status)
        VALUES ($1, 'v3-lot22-fixture.xlsx', true, 'completed')
        RETURNING id
        """,
        _MONTH,
    )
    assert snapshot is not None

    # reporting_agent_day/month intentionally contain ordinary retail rows and
    # one inactive historical retail store, but no TR row.  This mirrors the
    # reporting refresh filter policy while still allowing current-scope checks.
    await conn.execute(
        """
        INSERT INTO reporting_agent_day
            (import_month, sale_date, site_code, locatie, firma, regional, asm,
             agent, total_sales, total_quantity, focus_quantity, receipt_count,
             receipt_2plus_count, receipt_1_count, receipt_2_count,
             receipt_3_count, receipt_4plus_count)
        VALUES
            ($1, DATE '2099-12-01', $2, 'Lot22 Retail', 'Mobiup', $5, $6,
             $7, 100, 1, 0, 1, 0, 1, 0, 0, 0),
            ($1, DATE '2099-12-01', $2, 'Lot22 Retail', 'Mobiup', $5, $6,
             $8, 100, 1, 0, 1, 0, 1, 0, 0, 0),
            ($1, DATE '2099-12-01', $3, 'Lot22 Closed', 'Mobiup', $5, $6,
             $7, 100, 1, 0, 1, 0, 1, 0, 0, 0)
        """,
        _MONTH,
        _RETAIL_SITE,
        _CLOSED_SITE,
        _REGIONAL,
        _ASM,
        _AGENT_A,
        _AGENT_B,
    )
    await conn.execute(
        """
        INSERT INTO reporting_agent_month
            (import_month, site_code, locatie, firma, regional, asm, agent,
             total_sales, total_quantity, focus_quantity, receipt_count,
             receipt_2plus_count, receipt_1_count, receipt_2_count,
             receipt_3_count, receipt_4plus_count, working_days)
        VALUES
            ($1, $2, 'Lot22 Retail', 'Mobiup', $5, $6, $7,
             100, 1, 0, 1, 0, 1, 0, 0, 0, 1),
            ($1, $2, 'Lot22 Retail', 'Mobiup', $5, $6, $8,
             100, 1, 0, 1, 0, 1, 0, 0, 0, 1),
            ($1, $3, 'Lot22 Closed', 'Mobiup', $5, $6, $7,
             100, 1, 0, 1, 0, 1, 0, 0, 0, 1)
        """,
        _MONTH,
        _RETAIL_SITE,
        _CLOSED_SITE,
        _REGIONAL,
        _ASM,
        _AGENT_A,
        _AGENT_B,
    )
    return int(snapshot["id"])


async def _insert_sale(
    conn: asyncpg.Connection,
    snapshot_id: int,
    *,
    sale_date: date,
    site_code: str,
    agent: str,
    bon_nr: str,
    item_code: str,
    quantity: int = -1,
    is_cartela: bool = False,
) -> None:
    await conn.execute(
        """
        INSERT INTO sales_transactions
            (import_month, sale_date, site_code, bon_nr, item_code, item_name,
             quantity, unit_price, total_value, agent, is_cartela, is_return,
             snapshot_id)
        VALUES
            ($1, $2, $3, $4, $5, 'Lot22 item',
             $6, 10, $6 * 10, $7, $8, $6 < 0, $9)
        """,
        _MONTH,
        sale_date,
        site_code,
        bon_nr,
        item_code,
        quantity,
        agent,
        is_cartela,
        snapshot_id,
    )


async def _raw_population_count(conn: asyncpg.Connection) -> int:
    """Count non-cartela returns before Dashboard distribution/current scope."""

    identity = canonical_receipt_identity_sql("st")
    value = await conn.fetchval(
        f"""
        SELECT COUNT(DISTINCT {identity})::INT
        FROM sales_transactions st
        WHERE st.import_month = $1
          AND NOT st.is_cartela
          AND st.quantity < 0
          AND st.bon_nr IS NOT NULL
        """,
        _MONTH,
    )
    return int(value or 0)


def _scope_parts(
    *,
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> tuple[list[str], list[object]]:
    params, positions = build_scoped_params(
        [_MONTH],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses = scoped_clauses(
        positions,
        site_alias="st",
        store_alias="s",
        agent_alias="st",
        month_alias="st.import_month",
        month_position=1,
        include_cartela_filter=True,
    )
    if current_scope:
        clauses = _expand_current_manager_scope(clauses, positions)
    if current_scope and not include_closed_stores:
        clauses.append("s.is_active = true")
    clauses.extend(["st.quantity < 0", "st.bon_nr IS NOT NULL"])
    return clauses, params


async def _dashboard_scoped_count(
    conn: asyncpg.Connection,
    **scope: object,
) -> int:
    identity = canonical_receipt_identity_sql("st")
    clauses, params = _scope_parts(**scope)
    value = await conn.fetchval(
        f"""
        SELECT COUNT(DISTINCT {identity})::INT
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        WHERE {' AND '.join(clauses)}
        """,
        *params,
    )
    return int(value or 0)


async def _bucket_sum(
    conn: asyncpg.Connection,
    **scope: object,
) -> int:
    clauses, params = _scope_parts(**scope)
    value = await conn.fetchval(
        f"""
        WITH return_agent_day AS (
            SELECT
                st.import_month,
                st.sale_date,
                st.site_code,
                {_AGENT_KEY_SQL} AS agent_key,
                COUNT(DISTINCT st.bon_nr)::INT AS return_receipt_count
            FROM sales_transactions st
            JOIN stores s ON s.site_code = st.site_code
            WHERE {' AND '.join(clauses)}
            GROUP BY
                st.import_month,
                st.sale_date,
                st.site_code,
                {_AGENT_KEY_SQL}
        )
        SELECT COALESCE(SUM(return_receipt_count), 0)::INT
        FROM return_agent_day
        """,
        *params,
    )
    return int(value or 0)


async def _assert_null_receipt_is_non_counting(conn: asyncpg.Connection) -> None:
    identity = canonical_receipt_identity_sql("st")
    value = await conn.fetchval(
        f"""
        WITH st(sale_date, site_code, agent, bon_nr, quantity, is_cartela) AS (
            VALUES (
                DATE '2099-12-10', $1::TEXT, $2::TEXT,
                NULL::TEXT, -1::INTEGER, false
            )
        )
        SELECT COUNT(DISTINCT {identity})
            FILTER (
                WHERE NOT st.is_cartela
                  AND st.quantity < 0
                  AND st.bon_nr IS NOT NULL
            )
        FROM st
        """,
        _RETAIL_SITE,
        _AGENT_A,
    )
    assert value == 0


async def test_lot22_dashboard_scope_is_additive_at_reporting_agent_day_grain() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        try:
            snapshot_id = await _seed_authority(conn)

            # Same receipt + dimensions on two item rows -> one canonical receipt.
            for item_code in ("R1", "R2"):
                await _insert_sale(
                    conn,
                    snapshot_id,
                    sale_date=date(2099, 12, 1),
                    site_code=_RETAIL_SITE,
                    agent=_AGENT_A,
                    bon_nr="L22-SHARED",
                    item_code=item_code,
                )

            # Same bon number on another day and another agent -> distinct receipts.
            await _insert_sale(
                conn,
                snapshot_id,
                sale_date=date(2099, 12, 2),
                site_code=_RETAIL_SITE,
                agent=_AGENT_A,
                bon_nr="L22-SHARED",
                item_code="R3",
            )
            await _insert_sale(
                conn,
                snapshot_id,
                sale_date=date(2099, 12, 1),
                site_code=_RETAIL_SITE,
                agent=_AGENT_B,
                bon_nr="L22-SHARED",
                item_code="R4",
            )
            await _insert_sale(
                conn,
                snapshot_id,
                sale_date=date(2099, 12, 3),
                site_code=_RETAIL_SITE,
                agent=_AGENT_A,
                bon_nr="L22-CONTROL",
                item_code="R5",
            )

            # Historical retail row that current_scope must be able to remove.
            await _insert_sale(
                conn,
                snapshot_id,
                sale_date=date(2099, 12, 1),
                site_code=_CLOSED_SITE,
                agent=_AGENT_A,
                bon_nr="L22-CLOSED",
                item_code="CL1",
            )

            # Exists in raw transactions but canonical Dashboard scope excludes TR.
            await _insert_sale(
                conn,
                snapshot_id,
                sale_date=date(2099, 12, 1),
                site_code=_TR_SITE,
                agent=_AGENT_A,
                bon_nr="L22-TR",
                item_code="TR1",
            )

            # Excluded by Dashboard/reporting semantics.
            await _insert_sale(
                conn,
                snapshot_id,
                sale_date=date(2099, 12, 4),
                site_code=_RETAIL_SITE,
                agent=_AGENT_A,
                bon_nr="L22-CARTELA",
                item_code="C1",
                is_cartela=True,
            )
            await _insert_sale(
                conn,
                snapshot_id,
                sale_date=date(2099, 12, 5),
                site_code=_RETAIL_SITE,
                agent=_AGENT_A,
                bon_nr="L22-POSITIVE",
                item_code="P1",
                quantity=1,
            )
            await _assert_null_receipt_is_non_counting(conn)

            assert await conn.fetchval(
                "SELECT BOOL_AND(is_return = (quantity < 0)) "
                "FROM sales_transactions WHERE import_month = $1",
                _MONTH,
            ) is True

            # Raw population has six non-cartela return receipts: 4 active retail,
            # 1 inactive retail, 1 TR.  Dashboard scope removes TR.
            assert await _raw_population_count(conn) == 6
            assert await _dashboard_scoped_count(conn) == 5
            assert await _bucket_sum(conn) == 5

            # Current scope additionally removes the inactive retail store.
            current = {"current_scope": True}
            assert await _dashboard_scoped_count(conn, **current) == 4
            assert await _bucket_sum(conn, **current) == 4

            # Supported business scopes preserve additivity.
            for scope, expected in [
                ({"firma": "Mobiup"}, 5),
                ({"regional": _REGIONAL}, 5),
                ({"asm": _ASM}, 5),
                ({"site_code": _RETAIL_SITE}, 4),
                ({"site_code": _CLOSED_SITE}, 1),
                ({"site_code": _TR_SITE}, 0),
                ({"agent": _AGENT_A}, 4),
                ({"site_code": _RETAIL_SITE, "agent": _AGENT_A}, 3),
            ]:
                assert await _dashboard_scoped_count(conn, **scope) == expected
                assert await _bucket_sum(conn, **scope) == expected

            # The real History service path, unlike a bare repository call with
            # sales_clauses=[], applies scoped_clauses() and therefore excludes TR.
            service = _HistoryServiceShim(pool)
            historical_history = await load_monthly_history(
                service,
                _MONTH,
                1,
                None,
                None,
                None,
                None,
                None,
                current_scope=False,
            )
            assert historical_history.history[0].return_receipt_count == 5

            current_history = await load_monthly_history(
                service,
                _MONTH,
                1,
                None,
                None,
                None,
                None,
                None,
                current_scope=True,
            )
            assert current_history.history[0].return_receipt_count == 4

            # Store/agent/regional production query paths use the same scoped
            # distribution exclusion for their raw return_summary CTEs.
            stores = await _fetch_store_stats_rows(
                conn, _MONTH, None, None, None, None, None
            )
            assert {
                row["site_code"]: row["return_receipt_count"] for row in stores
            } == {_RETAIL_SITE: 4, _CLOSED_SITE: 1}

            current_stores = await _fetch_store_stats_rows(
                conn, _MONTH, None, None, None, None, None, current_scope=True
            )
            assert {
                row["site_code"]: row["return_receipt_count"]
                for row in current_stores
            } == {_RETAIL_SITE: 4}

            agents = await _fetch_agent_stats_rows(
                conn, _MONTH, None, None, None, None, None
            )
            assert {
                (row["site_code"], row["agent"]): row["return_receipt_count"]
                for row in agents
            } == {
                (_RETAIL_SITE, _AGENT_A): 3,
                (_RETAIL_SITE, _AGENT_B): 1,
                (_CLOSED_SITE, _AGENT_A): 1,
            }

            current_agents = await _fetch_agent_stats_rows(
                conn, _MONTH, None, None, None, None, None, current_scope=True
            )
            assert {
                (row["site_code"], row["agent"]): row["return_receipt_count"]
                for row in current_agents
            } == {
                (_RETAIL_SITE, _AGENT_A): 3,
                (_RETAIL_SITE, _AGENT_B): 1,
            }

            regional = await _fetch_regional_stats(
                conn, _MONTH, None, None, None, None, None
            )
            assert [
                (row["regional"], row["return_receipt_count"])
                for row in regional
            ] == [(_REGIONAL, 5)]

            current_regional = await _fetch_regional_stats(
                conn, _MONTH, None, None, None, None, None, current_scope=True
            )
            assert [
                (row["regional"], row["return_receipt_count"])
                for row in current_regional
            ] == [(_REGIONAL, 4)]

            reporting_exclusions = retail_exclusion_clauses(
                site_alias="st",
                store_alias="s",
            )
            assert reporting_exclusions == [
                "s.locatie NOT ILIKE 'TR %'",
                "NOT st.is_cartela",
            ]
            assert "s.locatie NOT ILIKE 'TR %'" in _REPORTING_MONTH_SQL_5
            assert "NOT st.is_cartela" in _REPORTING_MONTH_SQL_5
        finally:
            await _cleanup(conn)
