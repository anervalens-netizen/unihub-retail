"""Deterministic PostgreSQL proof for the shared sales/CRM month fence.

The two writer/read-publish protocols use the same transaction-scoped advisory
fence. These tests deliberately coordinate with events and observe the lock
through ``pg_try_advisory_xact_lock``; no sleep is used for correctness.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
import json
import os
from unittest.mock import AsyncMock

import pandas as pd
import pytest

import services.crm as crm_module
import services.sales_generation_flow as sales_flow
from db.connection import close_db_pool, get_pool
from services.crm import CrmService
from services.importer import import_sales_dataframe
from repositories.crm import CrmRepository
from services.sales_generation import (
    MONTH_FENCE_NAMESPACE,
    acquire_month_fence,
    month_fence_key,
)


pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL through the immutable test harness",
)

MONTH = "2099-12"
OTHER_MONTH = "2100-01"
SITE = "CRM-SALES-FENCE-L47"


def _sales_frame(total_value: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Data": date(2099, 12, 1),
                "SiteCode": SITE,
                "ItemCode": "FENCE-ITEM",
                "ItemName": "Fence item",
                "Cantitate": 1,
                "Brand": "Fence Brand",
                "Pret": total_value,
                "Valoare": total_value,
                "Locatie": "Fence Store",
                "Firma": "Mobicell",
                "ASM": "Fence ASM",
                "Regional": "Fence Regional",
                "Nr": f"FENCE-{total_value}",
                "Categorie": "Accesorii",
                "SubCategorie": "Fence",
                "Agent": "Fence Agent",
                "is_cartela": False,
                "is_return": False,
            }
        ]
    )


async def _cleanup(conn) -> None:
    await conn.execute(
        "ALTER TABLE sales_generation_promotions DISABLE TRIGGER trg_sales_generation_promotions_immutable"
    )
    try:
        await conn.execute(
            "DELETE FROM sales_generation_promotions WHERE import_month IN ($1, $2)",
            MONTH,
            OTHER_MONTH,
        )
    finally:
        await conn.execute(
            "ALTER TABLE sales_generation_promotions ENABLE TRIGGER trg_sales_generation_promotions_immutable"
        )
    await conn.execute(
        "DELETE FROM sales_generation_heads WHERE import_month IN ($1, $2)",
        MONTH,
        OTHER_MONTH,
    )
    await conn.execute(
        "DELETE FROM sales_transactions WHERE import_month IN ($1, $2)",
        MONTH,
        OTHER_MONTH,
    )
    await conn.execute(
        "DELETE FROM store_targets WHERE site_code = $1", SITE
    )
    await conn.execute(
        "DELETE FROM store_scores WHERE site_code = $1", SITE
    )
    await conn.execute(
        "DELETE FROM reporting_agent_month WHERE site_code = $1", SITE
    )
    await conn.execute(
        "DELETE FROM stores WHERE site_code = $1", SITE
    )
    await conn.execute(
        "UPDATE import_snapshots SET previous_snapshot_id = NULL "
        "WHERE import_month IN ($1, $2)",
        MONTH,
        OTHER_MONTH,
    )
    await conn.execute(
        "ALTER TABLE sales_import_stage_rows DISABLE TRIGGER trg_sales_stage_mutation"
    )
    try:
        await conn.execute(
            "DELETE FROM import_snapshots WHERE import_month IN ($1, $2)",
            MONTH,
            OTHER_MONTH,
        )
    finally:
        await conn.execute(
            "ALTER TABLE sales_import_stage_rows ENABLE TRIGGER trg_sales_stage_mutation"
        )


@pytest.fixture
async def fence_pool():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _cleanup(conn)
    yield pool
    async with pool.acquire() as conn:
        await _cleanup(conn)
    await close_db_pool()


async def _seed_generations(pool):
    async with pool.acquire() as conn:
        baseline = await import_sales_dataframe(
            conn,
            _sales_frame(100),
            "fence-baseline.xlsx",
            source_sha256="1" * 64,
            cutoff_date=date(2099, 12, 1),
            requested_by_sub="test:fence-baseline",
        )
        await conn.execute(
            "INSERT INTO store_targets (site_code, import_month, target_value, source_file) "
            "VALUES ($1, $2, 1000.00, 'fence-target.xlsx')",
            SITE,
            MONTH,
        )
        candidate = await import_sales_dataframe(
            conn,
            _sales_frame(500),
            "fence-candidate.xlsx",
            source_sha256="2" * 64,
            cutoff_date=date(2099, 12, 1),
            stage_only=True,
            requested_by_sub="test:fence-candidate",
        )
    assert baseline.generation_state == "promoted"
    assert candidate.generation_state == "validated"
    assert candidate.generation_token is not None
    assert candidate.owner_id is not None
    assert candidate.manifest_sha256 is not None
    return baseline, candidate


async def _promote(pool, candidate):
    async with pool.acquire() as conn:
        return await sales_flow.promote_sales_generation(
            conn,
            snapshot_id=candidate.snapshot_id,
            generation_token=str(candidate.generation_token),
            owner_id=str(candidate.owner_id),
            expected_manifest_sha256=str(candidate.manifest_sha256),
            requested_by_sub="test:fence-promoter",
        )


async def _try_fence(pool, month: str) -> bool:
    async with pool.acquire() as conn:
        async with conn.transaction():
            return bool(
                await conn.fetchval(
                    "SELECT pg_try_advisory_xact_lock($1, $2)",
                    MONTH_FENCE_NAMESPACE,
                    month_fence_key(month),
                )
            )


async def _reporting_total(pool) -> Decimal | None:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT SUM(total_sales) FROM reporting_agent_month "
            "WHERE import_month = $1 AND site_code = $2",
            MONTH,
            SITE,
        )


async def _score_row(pool):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT score, breakdown FROM store_scores "
            "WHERE score_month = $1 AND site_code = $2",
            MONTH,
            SITE,
        )


def _breakdown(row) -> dict:
    breakdown = row["breakdown"]
    if isinstance(breakdown, str):
        breakdown = json.loads(breakdown)
    return breakdown


@pytest.mark.anyio
async def test_promotion_first_fences_crm_until_new_generation_commits(fence_pool, monkeypatch):
    _, candidate = await _seed_generations(fence_pool)
    rebuild_entered = asyncio.Event()
    release_rebuild = asyncio.Event()
    crm_fence_attempted = asyncio.Event()
    crm_calculation_entered = asyncio.Event()

    real_rebuild = sales_flow.rebuild_reporting_month
    real_crm_fence = crm_module.acquire_month_fence
    real_calculation = CrmService.calculate_scores_for_month

    async def gated_rebuild(conn, month):
        assert month == MONTH
        rebuild_entered.set()
        await release_rebuild.wait()
        return await real_rebuild(conn, month)

    async def observed_crm_fence(conn, month):
        crm_fence_attempted.set()
        return await real_crm_fence(conn, month)

    async def observed_calculation(self, month, *, connection=None):
        crm_calculation_entered.set()
        return await real_calculation(self, month, connection=connection)

    monkeypatch.setattr(sales_flow, "rebuild_reporting_month", gated_rebuild)
    monkeypatch.setattr(crm_module, "acquire_month_fence", observed_crm_fence)
    monkeypatch.setattr(
        crm_module,
        "_query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(CrmService, "calculate_scores_for_month", observed_calculation)

    promotion_task = asyncio.create_task(_promote(fence_pool, candidate))
    await asyncio.wait_for(rebuild_entered.wait(), timeout=10)

    crm_service = CrmService(CrmRepository(fence_pool), fence_pool)
    crm_task = asyncio.create_task(crm_service.recalculate_scores(MONTH))
    await asyncio.wait_for(crm_fence_attempted.wait(), timeout=10)

    assert await _try_fence(fence_pool, MONTH) is False
    assert not crm_calculation_entered.is_set(), (
        "CRM must not begin its authoritative calculation while promotion "
        "holds the shared month fence"
    )

    release_rebuild.set()
    promotion_result = await promotion_task
    assert promotion_result == (1, 2)
    await asyncio.wait_for(crm_task, timeout=10)

    assert await _reporting_total(fence_pool) == Decimal("500")
    score_row = await _score_row(fence_pool)
    assert score_row is not None
    assert score_row["score"] == 45
    assert _breakdown(score_row)["target_attainment"] == 50.0


@pytest.mark.anyio
async def test_crm_first_fences_promotion_until_old_generation_commits(fence_pool, monkeypatch):
    baseline, candidate = await _seed_generations(fence_pool)
    crm_calculation_entered = asyncio.Event()
    release_calculation = asyncio.Event()
    promotion_fence_attempted = asyncio.Event()

    real_calculation = CrmService.calculate_scores_for_month
    real_promotion_fence = sales_flow.acquire_month_fence

    async def gated_calculation(self, month, *, connection=None):
        crm_calculation_entered.set()
        await release_calculation.wait()
        return await real_calculation(self, month, connection=connection)

    async def observed_promotion_fence(conn, month):
        promotion_fence_attempted.set()
        return await real_promotion_fence(conn, month)

    monkeypatch.setattr(CrmService, "calculate_scores_for_month", gated_calculation)
    monkeypatch.setattr(
        crm_module,
        "_query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(sales_flow, "acquire_month_fence", observed_promotion_fence)

    crm_service = CrmService(CrmRepository(fence_pool), fence_pool)
    crm_task = asyncio.create_task(crm_service.recalculate_scores(MONTH))
    await asyncio.wait_for(crm_calculation_entered.wait(), timeout=10)
    assert await _try_fence(fence_pool, MONTH) is False

    promotion_task = asyncio.create_task(_promote(fence_pool, candidate))
    await asyncio.wait_for(promotion_fence_attempted.wait(), timeout=10)
    assert await _try_fence(fence_pool, MONTH) is False

    async with fence_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT snapshot_id FROM sales_generation_heads WHERE import_month = $1",
            MONTH,
        ) == baseline.snapshot_id
    assert await _reporting_total(fence_pool) == Decimal("100")

    release_calculation.set()
    await asyncio.wait_for(crm_task, timeout=10)
    old_score = await _score_row(fence_pool)
    assert old_score is not None
    assert old_score["score"] == 29
    assert _breakdown(old_score)["target_attainment"] == 10.0

    promotion_result = await asyncio.wait_for(promotion_task, timeout=10)
    assert promotion_result == (1, 2)
    assert await _reporting_total(fence_pool) == Decimal("500")
    final_score = await _score_row(fence_pool)
    assert final_score is not None
    assert final_score["score"] == 29
    assert _breakdown(final_score)["target_attainment"] == 10.0


@pytest.mark.anyio
async def test_different_month_fences_are_independent(fence_pool):
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    release = asyncio.Event()

    async def holder(month: str, entered: asyncio.Event):
        async with fence_pool.acquire() as conn:
            async with conn.transaction():
                await acquire_month_fence(conn, month)
                entered.set()
                await release.wait()

    first = asyncio.create_task(holder(MONTH, first_entered))
    second = asyncio.create_task(holder(OTHER_MONTH, second_entered))
    await asyncio.wait_for(
        asyncio.gather(first_entered.wait(), second_entered.wait()),
        timeout=10,
    )
    assert await _try_fence(fence_pool, MONTH) is False
    assert await _try_fence(fence_pool, OTHER_MONTH) is False
    release.set()
    await asyncio.gather(first, second)


@pytest.mark.anyio
async def test_month_fence_releases_after_exception_and_cancellation(fence_pool):
    exception_entered = asyncio.Event()
    waiter_entered = asyncio.Event()

    async def failing_holder():
        async with fence_pool.acquire() as conn:
            async with conn.transaction():
                await acquire_month_fence(conn, MONTH)
                exception_entered.set()
                raise RuntimeError("rollback fence test")

    async def waiter(entered: asyncio.Event):
        async with fence_pool.acquire() as conn:
            async with conn.transaction():
                await acquire_month_fence(conn, MONTH)
                entered.set()

    failing = asyncio.create_task(failing_holder())
    await asyncio.wait_for(exception_entered.wait(), timeout=10)
    with pytest.raises(RuntimeError, match="rollback fence test"):
        await failing
    waiting_after_exception = asyncio.create_task(waiter(waiter_entered))
    await asyncio.wait_for(waiter_entered.wait(), timeout=10)
    await waiting_after_exception

    cancellation_entered = asyncio.Event()
    cancellation_release = asyncio.Event()
    cancellation_waiter_entered = asyncio.Event()

    async def cancellable_holder():
        async with fence_pool.acquire() as conn:
            async with conn.transaction():
                await acquire_month_fence(conn, MONTH)
                cancellation_entered.set()
                await cancellation_release.wait()

    cancellable = asyncio.create_task(cancellable_holder())
    await asyncio.wait_for(cancellation_entered.wait(), timeout=10)
    cancellation_waiter = asyncio.create_task(waiter(cancellation_waiter_entered))
    assert await _try_fence(fence_pool, MONTH) is False
    cancellable.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancellable
    await asyncio.wait_for(cancellation_waiter_entered.wait(), timeout=10)
    await cancellation_waiter
