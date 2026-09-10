"""Characterize whether return-receipt counts fit the existing reporting grain.

Lot 22 is deliberately characterization-only.  The current Dashboard raw
return query is the parity authority.  This test proves two independent facts:

1. canonical return-receipt identity is additive when pre-aggregated at
   (month, sale_date, site_code, canonical agent) grain; and
2. the existing reporting read-model filter set is not currently equivalent to
   the raw Dashboard return query because reporting excludes ``TR `` locations.

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
from services.dashboard.queries import _fetch_regional_stats
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
_TR_SITE = "V3-L22-TR"
_REGIONAL = "V3 Lot22 Regional"
_ASM = "V3 Lot22 ASM"
_AGENT_A = "V3 Lot22 Agent A"
_AGENT_B = "V3 Lot22 Agent B"
_AGENT_KEY_SQL = "COALESCE(NULLIF(BTRIM(st.agent), ''), '<unknown>')"


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM sales_transactions WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_day WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM reporting_agent_month WHERE import_month = $1", _MONTH)
    await conn.execute("DELETE FROM import_snapshots WHERE import_month = $1", _MONTH)
    await conn.execute(
        "DELETE FROM stores WHERE site_code IN ($1, $2)",
        _RETAIL_SITE,
        _TR_SITE,
    )


async def _seed_authority(conn: asyncpg.Connection) -> int:
    await conn.execute(
        """
        INSERT INTO stores
            (site_code, locatie, firma, regional, asm, is_active,
             first_seen_month, last_seen_month)
        VALUES
            ($1, 'Lot22 Retail', 'Mobiup', $3, $4, true, $5, $5),
            ($2, 'TR Lot22 Distribution', 'Mobiup', $3, $4, true, $5, $5)
        """,
        _RETAIL_SITE,
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

    # Regional Dashboard rows are driven by the existing read model.  Seed one
    # normal-retail row so the regional projection exists; deliberately do not
    # seed a TR read-model row because the real refresh excludes TR locations.
    await conn.execute(
        """
        INSERT INTO reporting_agent_month
            (import_month, site_code, locatie, firma, regional, asm, agent,
             total_sales, total_quantity, focus_quantity, receipt_count,
             receipt_2plus_count, receipt_1_count, receipt_2_count,
             receipt_3_count, receipt_4plus_count, working_days)
        VALUES
            ($1, $2, 'Lot22 Retail', 'Mobiup', $3, $4, $5,
             100, 1, 0, 1, 0, 1, 0, 0, 0, 1)
        """,
        _MONTH,
        _RETAIL_SITE,
        _REGIONAL,
        _ASM,
        _AGENT_A,
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


async def _canonical_raw_count(
    conn: asyncpg.Connection,
    *,
    site_code: str | None = None,
    agent: str | None = None,
) -> int:
    identity = canonical_receipt_identity_sql("st")
    clauses = [
        "st.import_month = $1",
        "NOT st.is_cartela",
        "st.quantity < 0",
        "st.bon_nr IS NOT NULL",
    ]
    params: list[object] = [_MONTH]
    if site_code is not None:
        params.append(site_code)
        clauses.append(f"st.site_code = ${len(params)}")
    if agent is not None:
        params.append(agent)
        clauses.append(f"st.agent = ${len(params)}")
    value = await conn.fetchval(
        f"""
        SELECT COUNT(DISTINCT {identity})::INT
        FROM sales_transactions st
        WHERE {' AND '.join(clauses)}
        """,
        *params,
    )
    return int(value or 0)


async def _bucket_sum(
    conn: asyncpg.Connection,
    *,
    apply_existing_reporting_filters: bool,
    site_code: str | None = None,
    agent: str | None = None,
) -> int:
    clauses = [
        "st.import_month = $1",
        "NOT st.is_cartela",
        "st.quantity < 0",
        "st.bon_nr IS NOT NULL",
    ]
    if apply_existing_reporting_filters:
        # Use the exact shared exclusion helper rather than restating the
        # distribution rule differently in this characterization.
        clauses = [
            "st.import_month = $1",
            *retail_exclusion_clauses(site_alias="st", store_alias="s"),
            "st.quantity < 0",
            "st.bon_nr IS NOT NULL",
        ]
    params: list[object] = [_MONTH]
    if site_code is not None:
        params.append(site_code)
        clauses.append(f"st.site_code = ${len(params)}")
    if agent is not None:
        params.append(agent)
        clauses.append(f"st.agent = ${len(params)}")

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


async def test_lot22_return_receipt_grain_is_additive_but_reporting_filters_drift() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
        try:
            snapshot_id = await _seed_authority(conn)

            # Same receipt, same canonical identity, two item rows -> one.
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

            # Same bon_nr in a new day and under a new agent -> two more
            # canonical receipts because those dimensions are part of identity.
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

            # Current Dashboard raw return query includes this TR-location row;
            # current reporting refresh excludes it through retail_filters.
            await _insert_sale(
                conn,
                snapshot_id,
                sale_date=date(2099, 12, 1),
                site_code=_TR_SITE,
                agent=_AGENT_A,
                bon_nr="L22-TR",
                item_code="TR1",
            )

            # Cartela returns are excluded by both semantics.
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
            # Positive sale is not a return.
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

            raw_global = await _canonical_raw_count(conn)
            additive_same_rows = await _bucket_sum(
                conn,
                apply_existing_reporting_filters=False,
            )
            additive_reporting_rows = await _bucket_sum(
                conn,
                apply_existing_reporting_filters=True,
            )

            # Four normal-retail receipts + one TR receipt.
            assert raw_global == 5
            # The existing agent-day grain is mathematically sufficient when
            # fed the same row set as the canonical raw query.
            assert additive_same_rows == raw_global
            # The existing reporting row filter changes that row set.
            assert additive_reporting_rows == 4

            # Scope additivity remains exact for ordinary retail slices.
            assert await _canonical_raw_count(conn, site_code=_RETAIL_SITE) == 4
            assert await _bucket_sum(
                conn,
                apply_existing_reporting_filters=False,
                site_code=_RETAIL_SITE,
            ) == 4
            assert await _canonical_raw_count(
                conn,
                site_code=_RETAIL_SITE,
                agent=_AGENT_A,
            ) == 3
            assert await _bucket_sum(
                conn,
                apply_existing_reporting_filters=False,
                site_code=_RETAIL_SITE,
                agent=_AGENT_A,
            ) == 3

            # The exact drift is isolated to row-inclusion semantics, not
            # receipt identity or the proposed aggregation grain.
            assert await _canonical_raw_count(conn, site_code=_TR_SITE) == 1
            assert await _bucket_sum(
                conn,
                apply_existing_reporting_filters=True,
                site_code=_TR_SITE,
            ) == 0

            history = await DashboardRepository(pool).fetch_monthly_history(
                [], [_MONTH, 1]
            )
            assert history
            assert history[0]["return_receipt_count"] == 5

            # A normal-retail regional base row exists, and the current raw
            # return_summary contributes the TR receipt because both stores
            # share the same regional value.
            regional = await _fetch_regional_stats(
                conn, _MONTH, None, None, None, None, None
            )
            assert [
                (row["regional"], row["return_receipt_count"])
                for row in regional
            ] == [(_REGIONAL, 5)]

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
