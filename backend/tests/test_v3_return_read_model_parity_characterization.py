"""Characterize return-receipt parity at the existing reporting grain.

Lot 22 is characterization-only.  It distinguishes unscoped raw transaction
population from the real Dashboard scope policy.  Dashboard scope excludes
``TR `` distribution locations and cartele; current scope may additionally
exclude inactive stores.  The test asks whether canonical return-receipt
identity remains additive at reporting-agent-day grain under those exact row
selection semantics.

No production query or schema is changed.
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
_RETAIL = "V3-L22-RETAIL"
_CLOSED = "V3-L22-CLOSED"
_TR = "V3-L22-TR"
_REGIONAL = "V3 Lot22 Regional"
_ASM = "V3 Lot22 ASM"
_AGENT_A = "V3 Lot22 Agent A"
_AGENT_B = "V3 Lot22 Agent B"
_AGENT_KEY_SQL = "COALESCE(NULLIF(BTRIM(st.agent), ''), '<unknown>')"


class _HistoryServiceShim:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.repo = DashboardRepository(pool)
        self.pool = pool

    def _pool_for(self, _deadline: object | None) -> asyncpg.Pool:
        return self.pool


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM sales_transactions WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_day WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_month WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM import_snapshots WHERE import_month = $1", _MONTH)
    await conn.execute(
        "DELETE FROM stores WHERE site_code = ANY($1::TEXT[])",
        [_RETAIL, _CLOSED, _TR],
    )


async def _insert_reporting_row(
    conn: asyncpg.Connection,
    *,
    site_code: str,
    locatie: str,
    agent: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO reporting_agent_day
            (import_month, sale_date, site_code, locatie, firma, regional, asm,
             agent, total_sales, total_quantity, focus_quantity, receipt_count,
             receipt_2plus_count, receipt_1_count, receipt_2_count,
             receipt_3_count, receipt_4plus_count)
        VALUES
            ($1, DATE '2099-12-01', $2, $3, 'Mobiup', $4, $5, $6,
             100, 1, 0, 1, 0, 1, 0, 0, 0)
        """,
        _MONTH,
        site_code,
        locatie,
        _REGIONAL,
        _ASM,
        agent,
    )
    await conn.execute(
        """
        INSERT INTO reporting_agent_month
            (import_month, site_code, locatie, firma, regional, asm, agent,
             total_sales, total_quantity, focus_quantity, receipt_count,
             receipt_2plus_count, receipt_1_count, receipt_2_count,
             receipt_3_count, receipt_4plus_count, working_days)
        VALUES
            ($1, $2, $3, 'Mobiup', $4, $5, $6,
             100, 1, 0, 1, 0, 1, 0, 0, 0, 1)
        """,
        _MONTH,
        site_code,
        locatie,
        _REGIONAL,
        _ASM,
        agent,
    )


async def _seed(conn: asyncpg.Connection) -> int:
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
        _RETAIL,
        _CLOSED,
        _TR,
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

    # Reporting refresh includes normal/inactive retail history but excludes TR.
    await _insert_reporting_row(
        conn, site_code=_RETAIL, locatie="Lot22 Retail", agent=_AGENT_A
    )
    await _insert_reporting_row(
        conn, site_code=_RETAIL, locatie="Lot22 Retail", agent=_AGENT_B
    )
    await _insert_reporting_row(
        conn, site_code=_CLOSED, locatie="Lot22 Closed", agent=_AGENT_A
    )
    return int(snapshot["id"])


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
            ($1, $2, $3, $4, $5, 'Lot22 item', $6, 10, $6 * 10,
             $7, $8, $6 < 0, $9)
        """,
        _MONTH,
        date(2099, 12, day),
        site,
        bon,
        item,
        quantity,
        agent,
        cartela,
        snapshot_id,
    )


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


async def _scoped_count(conn: asyncpg.Connection, **scope: object) -> int:
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


async def _bucket_sum(conn: asyncpg.Connection, **scope: object) -> int:
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
                st.import_month, st.sale_date, st.site_code, {_AGENT_KEY_SQL}
        )
        SELECT COALESCE(SUM(return_receipt_count), 0)::INT
        FROM return_agent_day
        """,
        *params,
    )
    return int(value or 0)


async def _raw_population_count(conn: asyncpg.Connection) -> int:
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


async def _assert_null_is_ignored(conn: asyncpg.Connection) -> None:
    identity = canonical_receipt_identity_sql("st")
    value = await conn.fetchval(
        f"""
        WITH st(sale_date, site_code, agent, bon_nr, quantity, is_cartela) AS (
            VALUES (DATE '2099-12-10', $1::TEXT, $2::TEXT, NULL::TEXT, -1, false)
        )
        SELECT COUNT(DISTINCT {identity})
            FILTER (WHERE NOT st.is_cartela AND st.quantity < 0 AND st.bon_nr IS NOT NULL)
        FROM st
        """,
        _RETAIL,
        _AGENT_A,
    )
    assert value == 0


async def test_lot22_dashboard_scope_is_additive_at_reporting_agent_day_grain() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        try:
            snapshot = await _seed(conn)

            # Active retail: four canonical receipts. Duplicate item rows on the
            # first receipt must not double count it.
            await _sale(conn, snapshot, day=1, site=_RETAIL, agent=_AGENT_A, bon="SHARED", item="R1")
            await _sale(conn, snapshot, day=1, site=_RETAIL, agent=_AGENT_A, bon="SHARED", item="R2")
            await _sale(conn, snapshot, day=2, site=_RETAIL, agent=_AGENT_A, bon="SHARED", item="R3")
            await _sale(conn, snapshot, day=1, site=_RETAIL, agent=_AGENT_B, bon="SHARED", item="R4")
            await _sale(conn, snapshot, day=3, site=_RETAIL, agent=_AGENT_A, bon="CONTROL", item="R5")

            # One historical inactive retail receipt and one distribution receipt.
            await _sale(conn, snapshot, day=1, site=_CLOSED, agent=_AGENT_A, bon="CLOSED", item="CL1")
            await _sale(conn, snapshot, day=1, site=_TR, agent=_AGENT_A, bon="TR", item="TR1")

            # Non-contributing controls.
            await _sale(conn, snapshot, day=4, site=_RETAIL, agent=_AGENT_A, bon="CARTELA", item="C1", cartela=True)
            await _sale(conn, snapshot, day=5, site=_RETAIL, agent=_AGENT_A, bon="POSITIVE", item="P1", quantity=1)
            await _assert_null_is_ignored(conn)

            assert await conn.fetchval(
                "SELECT BOOL_AND(is_return = (quantity < 0)) "
                "FROM sales_transactions WHERE import_month = $1",
                _MONTH,
            ) is True

            # Unscoped raw population = 4 active retail + 1 closed + 1 TR.
            assert await _raw_population_count(conn) == 6

            # Real historical Dashboard scope removes TR but keeps inactive history.
            assert await _scoped_count(conn) == 5
            assert await _bucket_sum(conn) == 5

            # Current scope removes the inactive store as well.
            assert await _scoped_count(conn, current_scope=True) == 4
            assert await _bucket_sum(conn, current_scope=True) == 4

            # Firm/regional/ASM/site/agent slicing preserves exact additivity.
            cases = [
                ({"firma": "Mobiup"}, 5),
                ({"regional": _REGIONAL}, 5),
                ({"asm": _ASM}, 5),
                ({"site_code": _RETAIL}, 4),
                ({"site_code": _CLOSED}, 1),
                ({"site_code": _TR}, 0),
                ({"agent": _AGENT_A}, 4),
                ({"site_code": _RETAIL, "agent": _AGENT_A}, 3),
            ]
            for scope, expected in cases:
                assert await _scoped_count(conn, **scope) == expected
                assert await _bucket_sum(conn, **scope) == expected

            # Exercise the actual History service policy.  A bare repository call
            # with sales_clauses=[] is not the production service path.
            service = _HistoryServiceShim(pool)
            historical = await load_monthly_history(
                service, _MONTH, 1, None, None, None, None, None,
                current_scope=False,
            )
            current = await load_monthly_history(
                service, _MONTH, 1, None, None, None, None, None,
                current_scope=True,
            )
            assert historical.history[0].return_receipt_count == 5
            assert current.history[0].return_receipt_count == 4

            stores = await _fetch_store_stats_rows(
                conn, _MONTH, None, None, None, None, None
            )
            assert {row["site_code"]: row["return_receipt_count"] for row in stores} == {
                _RETAIL: 4,
                _CLOSED: 1,
            }
            current_stores = await _fetch_store_stats_rows(
                conn, _MONTH, None, None, None, None, None, current_scope=True
            )
            assert {row["site_code"]: row["return_receipt_count"] for row in current_stores} == {
                _RETAIL: 4,
            }

            agents = await _fetch_agent_stats_rows(
                conn, _MONTH, None, None, None, None, None
            )
            assert {
                (row["site_code"], row["agent"]): row["return_receipt_count"]
                for row in agents
            } == {
                (_RETAIL, _AGENT_A): 3,
                (_RETAIL, _AGENT_B): 1,
                (_CLOSED, _AGENT_A): 1,
            }
            current_agents = await _fetch_agent_stats_rows(
                conn, _MONTH, None, None, None, None, None, current_scope=True
            )
            assert {
                (row["site_code"], row["agent"]): row["return_receipt_count"]
                for row in current_agents
            } == {
                (_RETAIL, _AGENT_A): 3,
                (_RETAIL, _AGENT_B): 1,
            }

            regional = await _fetch_regional_stats(
                conn, _MONTH, None, None, None, None, None
            )
            current_regional = await _fetch_regional_stats(
                conn, _MONTH, None, None, None, None, None, current_scope=True
            )
            assert [(row["regional"], row["return_receipt_count"]) for row in regional] == [
                (_REGIONAL, 5)
            ]
            assert [
                (row["regional"], row["return_receipt_count"])
                for row in current_regional
            ] == [(_REGIONAL, 4)]

            exclusions = retail_exclusion_clauses(site_alias="st", store_alias="s")
            assert exclusions == ["s.locatie NOT ILIKE 'TR %'", "NOT st.is_cartela"]
            assert "s.locatie NOT ILIKE 'TR %'" in _REPORTING_MONTH_SQL_5
            assert "NOT st.is_cartela" in _REPORTING_MONTH_SQL_5
        finally:
            await _cleanup(conn)
