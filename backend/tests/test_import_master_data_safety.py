from __future__ import annotations

import os
from datetime import date

import asyncpg
import pandas as pd
import pytest

from db.connection import close_db_pool, get_pool
from repositories.stores import StoresRepository
from services.importer import build_import_coverage_report, upsert_stores


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]


def sales_frame(site_codes: list[str], *, company: str = "Synthetic-A") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Data": date(2098, 1, 2),
                "SiteCode": site_code,
                "ItemCode": f"ITEM-{index:02d}",
                "ItemName": "Synthetic item",
                "Cantitate": 1,
                "Brand": "Synthetic brand",
                "Pret": 10,
                "Valoare": 10,
                "Locatie": f"Synthetic store {index:02d}",
                "Firma": company,
                "ASM": "Synthetic manager",
                "Regional": "Synthetic region",
                "Nr": f"RECEIPT-{index:02d}",
                "Categorie": "Synthetic category",
                "SubCategorie": "Synthetic subcategory",
                "Agent": "SYNTHETIC-AGENT",
                "is_cartela": False,
                "is_return": False,
            }
            for index, site_code in enumerate(site_codes, start=1)
        ]
    )


async def seed_stores(
    conn: asyncpg.Connection,
    site_codes: list[str],
    *,
    company: str = "Synthetic-A",
    active: bool = True,
) -> None:
    await conn.executemany(
        """
        INSERT INTO stores (
            site_code, locatie, firma, regional, asm,
            is_active, first_seen_month, last_seen_month
        )
        VALUES ($1, $2, $3, 'Synthetic region', 'Synthetic manager', $4, '2097-12', '2097-12')
        """,
        [
            (site_code, f"Synthetic store {index:02d}", company, active)
            for index, site_code in enumerate(site_codes, start=1)
        ],
    )


@pytest.mark.parametrize("incoming_count", [10, 9])
async def test_complete_and_ninety_percent_files_never_deactivate_absent_stores(
    incoming_count: int,
) -> None:
    pool = await get_pool()
    site_codes = [f"P0SAFE-{incoming_count}-{index:02d}" for index in range(10)]
    try:
        async with pool.acquire() as conn, conn.transaction():
            await seed_stores(conn, site_codes)
            frame = sales_frame(site_codes[:incoming_count])

            coverage = await build_import_coverage_report(conn, frame)
            await upsert_stores(conn, frame, "2098-01")

            statuses = await conn.fetch(
                "SELECT site_code, is_active FROM stores WHERE site_code = ANY($1::text[])",
                site_codes,
            )
            assert len(statuses) == 10
            assert all(bool(row["is_active"]) for row in statuses)
            assert coverage["incoming_store_count"] == incoming_count
            assert coverage["missing_active_store_count"] == 10 - incoming_count
            assert coverage["store_activity_writes"] == 0
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM stores WHERE site_code = ANY($1::text[])", site_codes
            )
        await close_db_pool()


async def test_single_company_file_does_not_change_other_company_activity() -> None:
    pool = await get_pool()
    first = ["P0FIRM-A1", "P0FIRM-A2"]
    second = ["P0FIRM-B1", "P0FIRM-B2"]
    try:
        async with pool.acquire() as conn, conn.transaction():
            await seed_stores(conn, first, company="Synthetic-A")
            await seed_stores(conn, second, company="Synthetic-B")

            await upsert_stores(
                conn,
                sales_frame(first, company="Synthetic-A"),
                "2098-02",
            )

            statuses = await conn.fetch(
                "SELECT is_active FROM stores WHERE site_code = ANY($1::text[])",
                second,
            )
            assert len(statuses) == 2
            assert all(bool(row["is_active"]) for row in statuses)
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM stores WHERE site_code = ANY($1::text[])", first + second
            )
        await close_db_pool()


async def test_inactive_store_is_not_reactivated_by_reappearance() -> None:
    pool = await get_pool()
    site_code = "P0INACTIVE-01"
    try:
        async with pool.acquire() as conn, conn.transaction():
            await seed_stores(conn, [site_code], active=False)

            await upsert_stores(conn, sales_frame([site_code]), "2098-03")

            assert await conn.fetchval(
                "SELECT is_active FROM stores WHERE site_code = $1", site_code
            ) is False
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM stores WHERE site_code = $1", site_code)
        await close_db_pool()


async def test_historical_import_inserts_new_store_inactive() -> None:
    pool = await get_pool()
    site_code = "P0HISTORICAL-01"
    marker = "synthetic-p0-historical-latest.xlsx"
    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO import_snapshots (import_month, filename, status)
                VALUES ('9999-12', $1, 'completed')
                """,
                marker,
            )

            await upsert_stores(conn, sales_frame([site_code]), "2098-03")

            assert await conn.fetchval(
                "SELECT is_active FROM stores WHERE site_code = $1", site_code
            ) is False
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM stores WHERE site_code = $1", site_code)
            await conn.execute("DELETE FROM import_snapshots WHERE filename = $1", marker)
        await close_db_pool()


async def test_explicit_activity_change_is_atomic_and_audited_by_subject() -> None:
    pool = await get_pool()
    site_code = "P0ACTIVITY-01"
    try:
        async with pool.acquire() as conn:
            await seed_stores(conn, [site_code])
        repo = StoresRepository(pool)

        event = await repo.change_activity(
            site_code=site_code,
            expected_is_active=True,
            new_is_active=False,
            reason="Synthetic business approval for closure",
            requested_by_sub="synthetic-oidc-subject",
        )

        assert event is not None
        async with pool.acquire() as conn:
            stored = await conn.fetchrow(
                """
                SELECT s.is_active, e.previous_is_active, e.new_is_active,
                       e.requested_by_sub
                FROM stores s
                JOIN store_activity_events e USING (site_code)
                WHERE s.site_code = $1
                """,
                site_code,
            )
        assert stored is not None
        assert stored["is_active"] is False
        assert stored["previous_is_active"] is True
        assert stored["new_is_active"] is False
        assert stored["requested_by_sub"] == "synthetic-oidc-subject"

        with pytest.raises(RuntimeError, match="concurrently"):
            await repo.change_activity(
                site_code=site_code,
                expected_is_active=True,
                new_is_active=False,
                reason="Synthetic stale concurrent closure request",
                requested_by_sub="different-synthetic-subject",
            )
        async with pool.acquire() as conn:
            assert await conn.fetchval(
                "SELECT count(*) FROM store_activity_events WHERE site_code = $1",
                site_code,
            ) == 1
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM store_activity_events WHERE site_code = $1", site_code
            )
            await conn.execute("DELETE FROM stores WHERE site_code = $1", site_code)
        await close_db_pool()
