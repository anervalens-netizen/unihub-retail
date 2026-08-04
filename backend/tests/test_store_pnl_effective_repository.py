from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from db.connection import close_db_pool, get_pool
from repositories.store_pnl_effective import StorePnlEffectiveRepository


PERIOD = date(2099, 10, 1)
SITE_ACTUAL = "PNLACTUAL"
SITE_ESTIMATED = "PNLESTIMATED"


async def cleanup(conn) -> None:
    await conn.execute(
        "DELETE FROM store_pnl_monthly WHERE period = $1 AND source_site_code = ANY($2::text[])",
        PERIOD,
        [SITE_ACTUAL, SITE_ESTIMATED],
    )
    await conn.execute(
        "DELETE FROM store_pnl_site_links WHERE source_site_code = ANY($1::text[])",
        [SITE_ACTUAL, SITE_ESTIMATED],
    )
    await conn.execute(
        "DELETE FROM stores WHERE site_code = ANY($1::text[])",
        [SITE_ACTUAL, SITE_ESTIMATED],
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_actual_and_estimated_are_selected_per_store_month() -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await cleanup(conn)
            await conn.executemany(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    first_seen_month, last_seen_month, is_active
                ) VALUES ($1, $2, 'Mobiup', 'Test Regional', 'Test ASM', '2099-10', '2099-10', TRUE)
                """,
                [
                    (SITE_ACTUAL, "P&L Actual Store"),
                    (SITE_ESTIMATED, "P&L Estimated Store"),
                ],
            )
            await conn.executemany(
                """
                INSERT INTO store_pnl_monthly (
                    company_name, period, source_site_code, source_location_name,
                    category_code, category_name, amount, data_kind,
                    source_file, source_sha256
                ) VALUES ($1, $2, $3, $4, 'v1', 'Venit', $5, $6, $7, $8)
                """,
                [
                    (
                        "Mobiup",
                        PERIOD,
                        SITE_ACTUAL,
                        "P&L Actual Store",
                        Decimal("100.00"),
                        "actual",
                        "finance.xlsx",
                        "a" * 64,
                    ),
                    (
                        "Mobiup",
                        PERIOD,
                        SITE_ACTUAL,
                        "P&L Actual Store",
                        Decimal("999.00"),
                        "estimated",
                        "model:legacy",
                        "b" * 64,
                    ),
                    (
                        "Mobiup",
                        PERIOD,
                        SITE_ESTIMATED,
                        "P&L Estimated Store",
                        Decimal("200.00"),
                        "estimated",
                        "model:legacy",
                        "c" * 64,
                    ),
                ],
            )

            repo = StorePnlEffectiveRepository(pool)
            rows = await repo.rows(PERIOD, PERIOD, "Mobiup")
            by_site = {row["site_code"]: row for row in rows}

            assert set(by_site) == {SITE_ACTUAL, SITE_ESTIMATED}
            assert by_site[SITE_ACTUAL]["data_kind"] == "actual"
            assert by_site[SITE_ACTUAL]["amount"] == Decimal("100.00")
            assert by_site[SITE_ESTIMATED]["data_kind"] == "estimated"
            assert by_site[SITE_ESTIMATED]["amount"] == Decimal("200.00")

            annual = await repo.annual_rows("Mobiup", None)
            row = next(
                item
                for item in annual
                if item["year"] == 2099 and item["category_code"] == "v1"
            )
            assert row["amount"] == Decimal("300.00")
            assert row["store_count"] == 2
            assert row["is_estimated"] is True
    finally:
        async with pool.acquire() as conn:
            await cleanup(conn)
        await close_db_pool()
