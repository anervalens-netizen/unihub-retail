from __future__ import annotations

import os
from datetime import date
from io import BytesIO

import asyncpg
import pandas as pd
import pytest

from db.connection import close_db_pool, get_pool
from repositories.stores import StoresRepository
from services.importer import (
    SALES_COLUMNS,
    build_import_coverage_report,
    import_sales_file,
    upsert_stores,
)


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


def sales_workbook(frame: pd.DataFrame) -> bytes:
    source = frame[SALES_COLUMNS].copy()
    source["Data"] = source["Data"].map(lambda value: value.strftime("%d.%m.%Y"))
    output = BytesIO()
    source.to_excel(output, index=False)
    return output.getvalue()


async def store_state(
    conn: asyncpg.Connection,
    site_code: str,
) -> dict[str, object]:
    row = await conn.fetchrow(
        """
        SELECT locatie, firma, regional, asm, is_active,
               first_seen_month, last_seen_month, updated_at
        FROM stores
        WHERE site_code = $1
        """,
        site_code,
    )
    assert row is not None
    return dict(row)


async def seed_completed_snapshot(
    conn: asyncpg.Connection,
    *,
    import_month: str,
    filename: str,
    site_code: str,
) -> None:
    snapshot_id = await conn.fetchval(
        """
        INSERT INTO import_snapshots (
            import_month, filename, rows_in_file, rows_imported,
            status, is_month_final
        )
        VALUES ($1, $2, 1, 1, 'completed', true)
        RETURNING id
        """,
        import_month,
        filename,
    )
    assert snapshot_id is not None
    await conn.execute(
        """
        INSERT INTO sales_transactions (
            import_month, sale_date, site_code, bon_nr, item_code, item_name,
            quantity, unit_price, total_value, agent,
            is_cartela, is_return, snapshot_id
        )
        VALUES (
            $1, $2, $3, 'BASELINE-RECEIPT', 'BASELINE-ITEM',
            'Baseline synthetic item', 1, 10, 10, 'SYNTHETIC-AGENT',
            false, false, $4
        )
        """,
        import_month,
        date.fromisoformat(f"{import_month}-01"),
        site_code,
        snapshot_id,
    )


async def import_month_state(
    conn: asyncpg.Connection,
    *,
    import_month: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    snapshots = await conn.fetch(
        "SELECT * FROM import_snapshots WHERE import_month = $1 ORDER BY id",
        import_month,
    )
    transactions = await conn.fetch(
        "SELECT * FROM sales_transactions WHERE import_month = $1 ORDER BY id",
        import_month,
    )
    return [dict(row) for row in snapshots], [dict(row) for row in transactions]


async def assert_rejected_workbook_has_no_database_effects(
    conn: asyncpg.Connection,
    frame: pd.DataFrame,
    *,
    filename: str,
    site_code: str,
    error_pattern: str,
) -> None:
    import_month = frame.iloc[0]["Data"].strftime("%Y-%m")
    existing_filename = f"existing-{filename}"
    await seed_completed_snapshot(
        conn,
        import_month=import_month,
        filename=existing_filename,
        site_code=site_code,
    )
    before = await store_state(conn, site_code)
    month_state_before = await import_month_state(
        conn,
        import_month=import_month,
    )

    with pytest.raises(ValueError, match=error_pattern):
        await import_sales_file(conn, sales_workbook(frame), filename)

    assert await store_state(conn, site_code) == before
    assert await import_month_state(
        conn,
        import_month=import_month,
    ) == month_state_before
    assert await conn.fetchval(
        "SELECT count(*) FROM import_snapshots WHERE filename = $1",
        filename,
    ) == 0


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


async def test_conflicting_store_metadata_is_rejected_before_any_database_write() -> None:
    pool = await get_pool()
    site_code = "P0CONFLICT-01"
    filename = "synthetic-p0-conflict.xlsx"
    frame = sales_frame([site_code])
    conflicting = frame.copy()
    conflicting.loc[0, "Nr"] = "RECEIPT-CONFLICT"
    conflicting.loc[0, "Locatie"] = "Contradictory synthetic store"
    frame = pd.concat([frame, conflicting], ignore_index=True)
    try:
        async with pool.acquire() as conn:
            await seed_stores(conn, [site_code])
            await assert_rejected_workbook_has_no_database_effects(
                conn,
                frame,
                filename=filename,
                site_code=site_code,
                error_pattern="contradictorii",
            )
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM sales_transactions WHERE site_code = $1", site_code
            )
            await conn.execute(
                "DELETE FROM import_snapshots WHERE filename IN ($1, $2)",
                filename,
                f"existing-{filename}",
            )
            await conn.execute("DELETE FROM stores WHERE site_code = $1", site_code)
        await close_db_pool()


async def test_duplicate_rows_are_rejected_before_any_database_write() -> None:
    pool = await get_pool()
    site_code = "P0DUPLICATE-01"
    filename = "synthetic-p0-duplicate.xlsx"
    row = sales_frame([site_code])
    frame = pd.concat([row, row], ignore_index=True)
    try:
        async with pool.acquire() as conn:
            await seed_stores(conn, [site_code])
            await assert_rejected_workbook_has_no_database_effects(
                conn,
                frame,
                filename=filename,
                site_code=site_code,
                error_pattern="duplicate",
            )
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM sales_transactions WHERE site_code = $1", site_code
            )
            await conn.execute(
                "DELETE FROM import_snapshots WHERE filename IN ($1, $2)",
                filename,
                f"existing-{filename}",
            )
            await conn.execute("DELETE FROM stores WHERE site_code = $1", site_code)
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
