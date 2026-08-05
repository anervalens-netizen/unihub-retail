from __future__ import annotations

import os

import pytest

import services.visits_sync as visits_sync
from db.connection import close_db_pool, get_pool


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]


def _row(asm: str | None, month: str, total_visits: int = 3) -> dict:
    return {
        "asm": asm,
        "month": month,
        "total_visits": total_visits,
        "avg_completion": 90.0,
        "avg_duration": 1.5,
        "distinct_stores": 2,
        "checklist_score": 80.0,
        "approved_pct": 75.0,
    }


async def test_visits_snapshot_replace_removes_stale_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM visits_snapshot")
            await conn.execute(
                """
                INSERT INTO visits_snapshot (asm, month, total_visits)
                VALUES ('STALE', '2099-01', 1)
                """
            )
            async def read_rows(_conn: object) -> list[dict]:
                return [_row("CURRENT", "2099-02")]

            monkeypatch.setattr(visits_sync, "_read_postgres_aggregates", read_rows)

            count = await visits_sync.sync_visits_snapshot(conn)
            rows = await conn.fetch(
                "SELECT asm, month, total_visits FROM visits_snapshot ORDER BY asm"
            )

        assert count == 1
        assert [dict(row) for row in rows] == [
            {"asm": "CURRENT", "month": "2099-02", "total_visits": 3}
        ]
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM visits_snapshot")
        await close_db_pool()


async def test_visits_snapshot_failure_rolls_back_previous_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM visits_snapshot")
            await conn.execute(
                """
                INSERT INTO visits_snapshot (asm, month, total_visits)
                VALUES ('KNOWN_GOOD', '2099-03', 7)
                """
            )
            async def read_rows(_conn: object) -> list[dict]:
                return [_row(None, "2099-04")]

            monkeypatch.setattr(visits_sync, "_read_postgres_aggregates", read_rows)

            with pytest.raises(Exception):
                await visits_sync.sync_visits_snapshot(conn)
            row = await conn.fetchrow(
                "SELECT asm, month, total_visits FROM visits_snapshot"
            )

        assert dict(row) == {
            "asm": "KNOWN_GOOD",
            "month": "2099-03",
            "total_visits": 7,
        }
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM visits_snapshot")
        await close_db_pool()
