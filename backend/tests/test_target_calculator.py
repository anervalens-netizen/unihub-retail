from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from auth import AuthClaims
from db.connection import close_db_pool, get_pool
from repositories.target_calculator import (
    TargetCalculatorRepository,
    TargetScenarioFinalizedError,
    TargetScenarioVersionConflict,
)
from routers.target_calculator import can_finalize_targets, require_target_owner
from services.target_calculator import (
    CALCULATION_METHOD,
    allocate_with_floors,
    realized_for_calculation,
    seasonality_pair_configuration,
    shift_month,
    source_month_configuration,
    weighted_ratio,
)


def auth_claims(email: str) -> AuthClaims:
    return AuthClaims(
        sub=email,
        email=email,
        preferred_username=email,
        groups=[],
        iss="test",
        aud="test",
        iat=0,
        exp=0,
        raw={},
    )


def test_source_months_are_derived_from_target_month() -> None:
    assert source_month_configuration("2026-06") == [
        {"month": "2023-05", "label": "Baza sezoniera Y-3", "role": "seasonality_base_y3"},
        {"month": "2023-06", "label": "Luna target Y-3", "role": "seasonality_target_y3"},
        {"month": "2024-05", "label": "Baza sezoniera Y-2", "role": "seasonality_base_y2"},
        {"month": "2024-06", "label": "Luna target Y-2", "role": "seasonality_target_y2"},
        {"month": "2025-05", "label": "Baza sezoniera Y-1", "role": "seasonality_base_y1"},
        {"month": "2025-06", "label": "Luna target Y-1", "role": "seasonality_target_y1"},
        {"month": "2026-05", "label": "Forecast luna curenta", "role": "floor_reference"},
    ]
    assert shift_month("2026-01", -1) == "2025-12"
    assert CALCULATION_METHOD == "seasonal_blended_multiyear_v1"


def test_only_owner_can_finalize_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGET_CALCULATOR_FINALIZER_EMAILS", raising=False)

    assert can_finalize_targets(auth_claims("aner.valens@gmail.com")) is True
    assert can_finalize_targets(auth_claims("elena.minca@example.com")) is False

    with pytest.raises(HTTPException) as exc_info:
        require_target_owner(auth_claims("elena.minca@example.com"))
    assert exc_info.value.status_code == 403


def test_finalizer_allowlist_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_CALCULATOR_FINALIZER_EMAILS", "owner@example.com, backup@example.com")

    assert can_finalize_targets(auth_claims("BACKUP@example.com")) is True
    assert can_finalize_targets(auth_claims("aner.valens@gmail.com")) is False


def test_partial_reference_sales_are_projected_for_calculation() -> None:
    assert realized_for_calculation(Decimal("2608548.73"), Decimal(31) / Decimal(26)) == Decimal("3110192.72")


def test_multiyear_seasonality_blends_recent_years_more_heavily() -> None:
    pairs = seasonality_pair_configuration("2026-07", 2)
    values = {
        "2025-06": Decimal("100000"),
        "2025-07": Decimal("130000"),
        "2024-06": Decimal("100000"),
        "2024-07": Decimal("90000"),
    }

    multiyear_factor, details = weighted_ratio(pairs, values)
    single_year_factor, _ = weighted_ratio(pairs[:1], values)

    assert single_year_factor == Decimal("1.3")
    assert multiyear_factor == Decimal("1.18")
    assert [item["year_offset"] for item in details] == [1, 2]


def test_allocation_redistributes_after_applying_floor() -> None:
    rows = [
        {"calculated_weight": Decimal("0.90"), "floor_target": Decimal("100"), "is_floor_limited": False},
        {"calculated_weight": Decimal("0.09"), "floor_target": Decimal("100"), "is_floor_limited": False},
        {"calculated_weight": Decimal("0.01"), "floor_target": Decimal("100"), "is_floor_limited": False},
    ]

    allocated, warnings = allocate_with_floors(rows, Decimal("1000"))

    assert warnings == []
    assert sum(row["proposed_target"] for row in allocated) == Decimal("1000.00")
    assert allocated[0]["proposed_target"] == Decimal("800.00")
    assert allocated[1]["proposed_target"] == Decimal("100.00")
    assert allocated[2]["proposed_target"] == Decimal("100.00")
    assert allocated[1]["is_floor_limited"] is True
    assert allocated[2]["is_floor_limited"] is True


def test_allocation_warns_when_budget_cannot_cover_floors() -> None:
    rows = [
        {"calculated_weight": Decimal("0.5"), "floor_target": Decimal("100"), "is_floor_limited": False},
        {"calculated_weight": Decimal("0.5"), "floor_target": Decimal("100"), "is_floor_limited": False},
    ]

    allocated, warnings = allocate_with_floors(rows, Decimal("150"))

    assert sum(row["proposed_target"] for row in allocated) == Decimal("200.00")
    assert len(warnings) == 1


def make_repository_connection() -> tuple[TargetCalculatorRepository, AsyncMock]:
    conn = MagicMock()
    conn.fetchrow = AsyncMock()
    conn.fetchval = AsyncMock()
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=transaction)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return TargetCalculatorRepository(pool), conn


@pytest.mark.asyncio
async def test_recalculation_replaces_the_single_draft_for_target_month() -> None:
    repo, conn = make_repository_connection()
    conn.fetchrow.return_value = {
        "id": 8,
        "status": "draft",
        "revision": 3,
    }

    scenario = {
        "target_month": "2026-06",
        "cohort_month": "2026-05",
        "total_target": Decimal("100.00"),
        "min_floor": Decimal("35.00"),
        "previous_month_floor_pct": Decimal("0.90"),
        "calculation_method": CALCULATION_METHOD,
        "source_months": [],
        "warnings": [],
    }
    rows = [{
        "site_code": "OPEN01",
        "locatie": "Magazin",
        "firma": "Mobiup",
        "regional": "Manager",
        "asm": "ASM",
        "calculated_weight": Decimal("1"),
        "floor_target": Decimal("35.00"),
        "proposed_target": Decimal("100.00"),
        "is_floor_limited": False,
        "history": [],
    }]

    assert await repo.save_draft_scenario(scenario, rows, expected_revision=3) == 8

    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert "pg_advisory_xact_lock" in statements[0]
    assert "UPDATE target_scenarios" in statements[1]
    assert "revision = revision + 1" in statements[1]
    delete_sql = statements[2]
    assert "DELETE FROM target_scenario_rows" in delete_sql
    conn.executemany.assert_awaited_once()


@pytest.mark.asyncio
async def test_recalculation_cannot_overwrite_a_finalized_month() -> None:
    repo, conn = make_repository_connection()
    conn.fetchrow.return_value = {
        "id": 8,
        "status": "finalized",
        "revision": 4,
    }

    scenario = {
        "target_month": "2026-06",
        "cohort_month": "2026-05",
        "total_target": Decimal("100.00"),
        "min_floor": Decimal("35.00"),
        "previous_month_floor_pct": Decimal("0.90"),
        "calculation_method": CALCULATION_METHOD,
        "source_months": [],
        "warnings": [],
    }

    with pytest.raises(TargetScenarioFinalizedError):
        await repo.save_draft_scenario(scenario, [], expected_revision=4)

    assert conn.execute.await_count == 1
    conn.executemany.assert_not_awaited()


@pytest.mark.asyncio
async def test_recalculation_rejects_a_stale_revision() -> None:
    repo, conn = make_repository_connection()
    conn.fetchrow.return_value = {
        "id": 8,
        "status": "draft",
        "revision": 4,
    }

    with pytest.raises(TargetScenarioVersionConflict):
        await repo.save_draft_scenario(
            {
                "target_month": "2026-06",
                "cohort_month": "2026-05",
                "total_target": Decimal("100.00"),
                "min_floor": Decimal("35.00"),
                "previous_month_floor_pct": Decimal("0.90"),
                "calculation_method": CALCULATION_METHOD,
                "source_months": [],
                "warnings": [],
            },
            [],
            expected_revision=3,
        )

    assert conn.execute.await_count == 1
    conn.executemany.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_concurrent_recalculations_allow_exactly_one_writer() -> None:
    pool = await get_pool()
    repo = TargetCalculatorRepository(pool)
    target_month = "2099-12"
    scenario = {
        "target_month": target_month,
        "cohort_month": "2099-11",
        "total_target": Decimal("100.00"),
        "min_floor": Decimal("35.00"),
        "previous_month_floor_pct": Decimal("0.90"),
        "calculation_method": CALCULATION_METHOD,
        "source_months": [],
        "warnings": [],
    }

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM target_scenarios WHERE target_month = $1",
                target_month,
            )

        first_results = await asyncio.gather(
            repo.save_draft_scenario(scenario, [], expected_revision=None),
            repo.save_draft_scenario(scenario, [], expected_revision=None),
            return_exceptions=True,
        )
        assert sum(isinstance(result, int) for result in first_results) == 1
        assert sum(
            isinstance(result, TargetScenarioVersionConflict)
            for result in first_results
        ) == 1

        second_results = await asyncio.gather(
            repo.save_draft_scenario(scenario, [], expected_revision=1),
            repo.save_draft_scenario(scenario, [], expected_revision=1),
            return_exceptions=True,
        )
        assert sum(isinstance(result, int) for result in second_results) == 1
        assert sum(
            isinstance(result, TargetScenarioVersionConflict)
            for result in second_results
        ) == 1

        async with pool.acquire() as conn:
            stored = await conn.fetchrow(
                """
                SELECT COUNT(*) OVER () AS scenario_count, revision
                FROM target_scenarios
                WHERE target_month = $1
                """,
                target_month,
            )
        assert stored is not None
        assert stored["scenario_count"] == 1
        assert stored["revision"] == 2
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM target_scenarios WHERE target_month = $1",
                target_month,
            )
        await close_db_pool()


@pytest.mark.asyncio
async def test_finalize_replaces_official_targets_with_exact_approved_cohort() -> None:
    repo, conn = make_repository_connection()
    conn.fetchrow.return_value = {
        "target_month": "2026-06",
        "total_target": Decimal("100.00"),
        "status": "draft",
        "revision": 2,
    }
    conn.fetchval.side_effect = [Decimal("100.00"), 0]

    assert await repo.finalize_scenario(8, expected_revision=2) is True

    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert "DELETE FROM store_targets" in statements[0]
    assert "site_code NOT IN" in statements[0]
    assert "INSERT INTO store_targets" in statements[1]
    assert "UPDATE target_scenarios" in statements[2]


@pytest.mark.asyncio
async def test_finalize_does_not_publish_or_delete_when_final_total_changed() -> None:
    repo, conn = make_repository_connection()
    conn.fetchrow.return_value = {
        "target_month": "2026-06",
        "total_target": Decimal("100.00"),
        "status": "draft",
        "revision": 2,
    }
    conn.fetchval.side_effect = [Decimal("99.00"), 0]

    assert await repo.finalize_scenario(8, expected_revision=2) is False
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_does_not_publish_when_final_targets_are_blank() -> None:
    repo, conn = make_repository_connection()
    conn.fetchrow.return_value = {
        "target_month": "2026-06",
        "total_target": Decimal("100.00"),
        "status": "draft",
        "revision": 2,
    }
    conn.fetchval.side_effect = [Decimal("100.00"), 1]

    assert await repo.finalize_scenario(8, expected_revision=2) is False
    conn.execute.assert_not_awaited()
