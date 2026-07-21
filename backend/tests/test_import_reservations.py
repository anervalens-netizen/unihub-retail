from __future__ import annotations

import asyncio
import os
from datetime import date

import pandas as pd
import pytest

import services.importer as importer
from db.connection import close_db_pool, get_pool
from services.importer import (
    ImportAlreadyRunningError,
    reconcile_interrupted_imports,
    reserve_snapshot,
)


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]


async def test_import_snapshot_reservation_is_atomic_and_recovers_stale() -> None:
    pool = await get_pool()
    import_month = "2099-09"
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM import_snapshots WHERE import_month = $1",
                import_month,
            )

        async def reserve(filename: str) -> int | Exception:
            try:
                async with pool.acquire() as conn:
                    return await reserve_snapshot(
                        conn,
                        import_month,
                        filename,
                        rows_in_file=1,
                    )
            except Exception as exc:  # noqa: BLE001 - asserted below
                return exc

        results = await asyncio.gather(reserve("first.xlsx"), reserve("second.xlsx"))
        assert sum(isinstance(result, int) for result in results) == 1
        assert sum(
            isinstance(result, ImportAlreadyRunningError)
            for result in results
        ) == 1

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE import_snapshots
                SET heartbeat_at = now() - interval '2 hours'
                WHERE import_month = $1 AND status = 'processing'
                """,
                import_month,
            )
            replacement_id = await reserve_snapshot(
                conn,
                import_month,
                "replacement.xlsx",
                rows_in_file=1,
            )
            statuses = await conn.fetch(
                """
                SELECT id, status, finished_at
                FROM import_snapshots
                WHERE import_month = $1
                ORDER BY id
                """,
                import_month,
            )
        assert replacement_id is not None
        assert [row["status"] for row in statuses] == ["failed", "processing"]
        assert statuses[0]["finished_at"] is not None
        assert statuses[1]["finished_at"] is None
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM import_snapshots WHERE import_month = $1",
                import_month,
            )
        await close_db_pool()


async def test_worker_restart_reconciliation_allows_immediate_retry() -> None:
    pool = await get_pool()
    import_month = "2099-10"
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM import_snapshots WHERE import_month = $1",
                import_month,
            )
            interrupted_id = await reserve_snapshot(
                conn,
                import_month,
                "interrupted.xlsx",
                rows_in_file=1,
            )

        reconciled = await reconcile_interrupted_imports(pool)
        assert interrupted_id in reconciled

        async with pool.acquire() as conn:
            replacement_id = await reserve_snapshot(
                conn,
                import_month,
                "retry.xlsx",
                rows_in_file=1,
            )
            rows = await conn.fetch(
                """
                SELECT id, status, error_message, finished_at
                FROM import_snapshots
                WHERE import_month = $1
                ORDER BY id
                """,
                import_month,
            )

        assert replacement_id != interrupted_id
        assert [row["status"] for row in rows] == ["failed", "processing"]
        assert "restartul workerului" in rows[0]["error_message"]
        assert rows[0]["finished_at"] is not None
        assert rows[1]["finished_at"] is None
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM import_snapshots WHERE import_month = $1",
                import_month,
            )
        await close_db_pool()


async def test_failed_reimport_restores_the_previous_completed_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    import_month = "2099-08"
    old_snapshot_id: int | None = None
    frame = pd.DataFrame(
        [
            {
                "Data": date(2099, 8, 1),
                "SiteCode": "ROLLBACK01",
                "ItemCode": "ITEM01",
                "ItemName": "Produs",
                "Cantitate": 1,
                "Brand": "Brand",
                "Pret": 10,
                "Valoare": 10,
                "Locatie": "Rollback Store",
                "Firma": "Mobiup",
                "ASM": "Manager",
                "Regional": "Manager",
                "Nr": "BON1",
                "Categorie": "Accesorii",
                "SubCategorie": "Test",
                "Agent": "Agent Test",
                "is_cartela": False,
                "is_return": False,
            }
        ]
    )

    async def fail_insert(*args: object, **kwargs: object) -> int:
        raise RuntimeError("simulated insert failure")

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM import_snapshots WHERE import_month = $1",
                import_month,
            )
            old_snapshot_id = await conn.fetchval(
                """
                INSERT INTO import_snapshots (
                    import_month, filename, rows_in_file, rows_imported,
                    status, is_month_final
                )
                VALUES ($1, 'previous.xlsx', 1, 1, 'completed', false)
                RETURNING id
                """,
                import_month,
            )

        monkeypatch.setattr(importer, "insert_transactions", fail_insert)
        async with pool.acquire() as conn:
            with pytest.raises(RuntimeError, match="simulated insert failure"):
                await importer.import_sales_dataframe(conn, frame, "replacement.xlsx")

        async with pool.acquire() as conn:
            snapshots = await conn.fetch(
                """
                SELECT id, status, filename
                FROM import_snapshots
                WHERE import_month = $1
                ORDER BY id
                """,
                import_month,
            )
        assert [(row["id"], row["status"], row["filename"]) for row in snapshots] == [
            (old_snapshot_id, "completed", "previous.xlsx"),
            (snapshots[1]["id"], "failed", "replacement.xlsx"),
        ]
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM import_snapshots WHERE import_month = $1",
                import_month,
            )
            await conn.execute(
                "DELETE FROM stores WHERE site_code = 'ROLLBACK01'",
            )
        await close_db_pool()
