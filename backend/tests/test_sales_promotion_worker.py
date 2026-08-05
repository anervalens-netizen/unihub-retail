from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import routers.filters
import services.imports
import services.retail_metrics
import services.sales_generation_flow
import worker
from services.sales_generation import SalesGenerationConflictError


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False


def _promotion_connection() -> tuple[MagicMock, MagicMock]:
    conn = MagicMock()
    conn.transaction.return_value = _AsyncContext(None)
    pool = MagicMock()
    pool.acquire.return_value = _AsyncContext(conn)
    return pool, conn


def _promoted_row() -> dict[str, object]:
    return {
        "import_month": "2026-08",
        "filename": "sales.xlsx",
        "rows_in_file": 10,
        "rows_imported": 8,
        "is_month_final": False,
        "coverage_report": {"stores_present_count": 2},
        "manifest": {"generation_state": "promoted", "rows_filtered": 2},
    }


@pytest.mark.asyncio
async def test_promotion_worker_claims_with_import_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, conn = _promotion_connection()
    conn.fetchval = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_promoted_row())
    claim = AsyncMock(return_value="previous-owner")
    promote = AsyncMock(return_value=(8, 3))
    restore = AsyncMock()
    monkeypatch.setattr(services.sales_generation_flow, "claim_validated_sales_generation", claim)
    monkeypatch.setattr(services.sales_generation_flow, "promote_sales_generation", promote)
    monkeypatch.setattr(services.sales_generation_flow, "restore_sales_generation_claim", restore)
    clear_filters = MagicMock()
    update_metrics = AsyncMock()
    trigger_grile = AsyncMock()
    monkeypatch.setattr(routers.filters, "clear_filter_options_cache", clear_filters)
    monkeypatch.setattr(services.retail_metrics, "update_business_metrics", update_metrics)
    monkeypatch.setattr(services.imports, "trigger_grile_check_after_import", trigger_grile)

    result = await worker.promote_sales_background(
        {"db_pool": pool},
        214,
        "a" * 36,
        "new-owner",
        "b" * 64,
        "owner:123",
    )

    claim.assert_awaited_once_with(
        conn,
        snapshot_id=214,
        generation_token="a" * 36,
        expected_manifest_sha256="b" * 64,
        new_owner_id="new-owner",
    )
    promote.assert_awaited_once_with(
        conn,
        snapshot_id=214,
        generation_token="a" * 36,
        owner_id="new-owner",
        expected_manifest_sha256="b" * 64,
        requested_by_sub="owner:123",
        override_reason=None,
    )
    restore.assert_not_awaited()
    assert result["generation_state"] == "promoted"
    assert result["snapshot_id"] == 214
    update_metrics.assert_awaited_once_with(pool)
    trigger_grile.assert_awaited_once_with("2026-08", 214)


@pytest.mark.asyncio
async def test_promotion_worker_restores_claim_when_promotion_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, conn = _promotion_connection()
    conn.fetchval = AsyncMock(return_value=None)
    claim = AsyncMock(return_value="previous-owner")
    promote = AsyncMock(side_effect=RuntimeError("promotion failed"))
    restore = AsyncMock()
    monkeypatch.setattr(services.sales_generation_flow, "claim_validated_sales_generation", claim)
    monkeypatch.setattr(services.sales_generation_flow, "promote_sales_generation", promote)
    monkeypatch.setattr(services.sales_generation_flow, "restore_sales_generation_claim", restore)

    with pytest.raises(RuntimeError, match="promotion failed"):
        await worker.promote_sales_background(
            {"db_pool": pool},
            214,
            "a" * 36,
            "new-owner",
            "b" * 64,
            "owner:123",
        )

    restore.assert_awaited_once_with(
        conn,
        snapshot_id=214,
        generation_token="a" * 36,
        current_owner_id="new-owner",
        previous_owner_id="previous-owner",
    )


@pytest.mark.asyncio
async def test_promotion_worker_does_not_restore_when_claim_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, conn = _promotion_connection()
    claim = AsyncMock(side_effect=SalesGenerationConflictError("stale generation"))
    restore = AsyncMock()
    monkeypatch.setattr(services.sales_generation_flow, "claim_validated_sales_generation", claim)
    monkeypatch.setattr(services.sales_generation_flow, "restore_sales_generation_claim", restore)

    with pytest.raises(SalesGenerationConflictError, match="stale generation"):
        await worker.promote_sales_background(
            {"db_pool": pool},
            214,
            "a" * 36,
            "new-owner",
            "b" * 64,
            "owner:123",
        )

    restore.assert_not_awaited()
