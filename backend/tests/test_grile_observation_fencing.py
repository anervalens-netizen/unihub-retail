from __future__ import annotations

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

_MONTH = "2099-09"
_SITE = "P11OBS"


def _success(target: int) -> dict:
    return {
        "site_code": _SITE,
        "completion_pct": 100,
        "grila_target": target,
        "grila_sales": target,
        "db_target": target,
        "db_sales_mtd": target,
        "fill_status": "COMPLETAT",
        "target_status": "OK",
        "sales_status": "OK",
        "tolerance": 1,
        "raw_summary": {"missing_days": [], "days_elapsed": 2},
        "content_sha256": f"{target:064x}",
    }


def _error() -> dict:
    return {
        "site_code": _SITE,
        "db_target": 200,
        "db_sales_mtd": 200,
        "tolerance": 1,
        "error_code": "STRUCTURAL_INVALID",
        "error_message": "range order changed",
        "content_sha256": None,
    }


async def _cleanup(conn) -> None:
    await conn.execute("DELETE FROM grile_store_current_status WHERE run_month = $1 AND site_code = $2", _MONTH, _SITE)
    await conn.execute("DELETE FROM grile_store_refreshes WHERE run_month = $1 AND site_code = $2", _MONTH, _SITE)
    await conn.execute("DELETE FROM grile_runs WHERE run_month = $1", _MONTH)
    await conn.execute("DELETE FROM grile_store_projection_generations WHERE run_month = $1 AND site_code = $2", _MONTH, _SITE)
    await conn.execute("DELETE FROM stores WHERE site_code = $1", _SITE)


async def test_immutable_observations_fence_stale_full_run_and_keep_last_success() -> None:
    pool = await get_pool()
    repo = GrileRepository(pool)
    try:
        async with pool.acquire() as conn:
            await _cleanup(conn)
            await conn.execute(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm, is_active,
                    first_seen_month, last_seen_month
                ) VALUES ($1, 'P1.1 observation test', 'Mobiup', 'Synthetic', 'Synthetic', true, $2, $2)
                """,
                _SITE,
                _MONTH,
            )

        run_id = await repo.reserve_run(
            run_month=_MONTH,
            source="manual",
            source_snapshot_id=None,
            triggered_by_sub="p11-test",
        )
        assert run_id is not None
        full_generations = await repo.claim_run(
            int(run_id),
            progress_total=1,
            site_codes=[_SITE],
        )
        assert full_generations == {_SITE: 1}

        refresh_id = await repo.reserve_store_refresh(
            run_month=_MONTH,
            site_code=_SITE,
            requested_by_sub="p11-test",
        )
        assert refresh_id is not None
        assert await repo.reserve_store_refresh(
            run_month=_MONTH,
            site_code=_SITE,
            requested_by_sub="parallel-test",
        ) is None
        refresh = await repo.claim_store_refresh(int(refresh_id))
        assert refresh is not None
        assert int(refresh["generation"]) == 2
        assert await repo.complete_store_refresh(
            int(refresh_id),
            _success(200),
            status="completed",
        ) is True

        # The full run read first but persists an error later. Its immutable row is
        # retained, while its older generation cannot become the latest provider
        # failure after a newer successful store refresh.
        assert await repo.record_full_observation(
            int(run_id),
            _error(),
            generation=full_generations[_SITE],
            checked_by_sub="p11-test",
        ) is False
        current_after_stale_error = await repo.get_current_status(_MONTH, _SITE)
        assert current_after_stale_error is not None
        assert int(current_after_stale_error["generation"]) == 2
        assert current_after_stale_error["last_error_code"] is None
        await repo.finalize_run(
            int(run_id),
            status="completed",
            ok_count=0,
            problem_count=0,
            error_count=1,
            duration_ms=1,
        )

        failed_refresh_id = await repo.reserve_store_refresh(
            run_month=_MONTH,
            site_code=_SITE,
            requested_by_sub="p11-test",
        )
        assert failed_refresh_id is not None
        failed_refresh = await repo.claim_store_refresh(int(failed_refresh_id))
        assert failed_refresh is not None
        assert int(failed_refresh["generation"]) == 3
        assert await repo.complete_store_refresh(
            int(failed_refresh_id),
            _error(),
            status="failed",
            error_code="STRUCTURAL_INVALID",
            error_message="range order changed",
        ) is True

        current = await repo.get_current_status(_MONTH, _SITE)
        assert current is not None
        assert int(current["generation"]) == 2
        assert int(current["grila_target"]) == 200
        assert current["error_code"] is None
        assert current["last_error_code"] == "STRUCTURAL_INVALID"
        assert current["last_success_checked_at"] is not None
        assert current["last_error_checked_at"] is not None

        async with pool.acquire() as conn:
            observation_count = await conn.fetchval(
                "SELECT count(*) FROM grile_store_observations WHERE run_month = $1 AND site_code = $2",
                _MONTH,
                _SITE,
            )
        assert observation_count == 3
    finally:
        async with pool.acquire() as conn:
            await _cleanup(conn)
        await close_db_pool()
