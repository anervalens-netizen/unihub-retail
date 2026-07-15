from __future__ import annotations

import asyncio
import os

import pytest

from db.connection import close_db_pool, get_pool
from repositories.grile import GrileRepository


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]


async def test_grile_run_reservation_is_atomic_and_reusable() -> None:
    pool = await get_pool()
    repo = GrileRepository(pool)
    run_month = "2099-11"

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM grile_runs WHERE run_month = $1",
                run_month,
            )

        reservations = await asyncio.gather(
            repo.reserve_run(
                run_month=run_month,
                source="manual",
                source_snapshot_id=None,
                triggered_by_sub="synthetic-subject-one",
            ),
            repo.reserve_run(
                run_month=run_month,
                source="manual",
                source_snapshot_id=None,
                triggered_by_sub="synthetic-subject-two",
            ),
        )
        run_ids = [run_id for run_id in reservations if run_id is not None]
        assert len(run_ids) == 1
        assert reservations.count(None) == 1

        run_id = int(run_ids[0])
        assert await repo.start_run(run_id, progress_total=3) is True
        assert await repo.start_run(run_id, progress_total=3) is False
        assert await repo.reserve_run(
            run_month=run_month,
            source="auto",
            source_snapshot_id=None,
            triggered_by_sub=None,
        ) is None

        await repo.finalize_run(
            run_id,
            status="completed",
            ok_count=3,
            problem_count=0,
            error_count=0,
            duration_ms=10,
        )
        next_run_id = await repo.reserve_run(
            run_month=run_month,
            source="manual",
            source_snapshot_id=None,
            triggered_by_sub="synthetic-subject-next",
        )
        assert next_run_id is not None
        assert int(next_run_id) != run_id
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM grile_runs WHERE run_month = $1",
                run_month,
            )
        await close_db_pool()


async def test_grile_run_reservation_recovers_an_expired_lease() -> None:
    pool = await get_pool()
    repo = GrileRepository(pool)
    run_month = "2099-10"

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM grile_runs WHERE run_month = $1",
                run_month,
            )
            stale_id = await conn.fetchval(
                """
                INSERT INTO grile_runs (
                    run_month, source, status, heartbeat_at, created_at
                )
                VALUES (
                    $1, 'manual', 'queued',
                    now() - interval '3 hours',
                    now() - interval '3 hours'
                )
                RETURNING id
                """,
                run_month,
            )

        replacement_id = await repo.reserve_run(
            run_month=run_month,
            source="auto",
            source_snapshot_id=None,
            triggered_by_sub=None,
        )
        assert replacement_id is not None
        assert int(replacement_id) != int(stale_id)

        async with pool.acquire() as conn:
            statuses = await conn.fetch(
                """
                SELECT id, status
                FROM grile_runs
                WHERE run_month = $1
                ORDER BY id
                """,
                run_month,
            )
        assert [row["status"] for row in statuses] == ["failed", "queued"]
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM grile_runs WHERE run_month = $1",
                run_month,
            )
        await close_db_pool()
