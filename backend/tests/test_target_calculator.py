from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

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
    allocate_with_bounds,
    allocate_with_floors,
    percent_change,
    realized_for_calculation,
    seasonality_pair_configuration,
    seasonal_year_weights,
    shift_month,
    source_month_configuration,
    weighted_available,
    weighted_ratio,
)


def auth_claims(email: str, groups: list[str] | None = None) -> AuthClaims:
    return AuthClaims(
        sub=email,
        email=email,
        preferred_username=email,
        groups=groups or [],
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


def _request(path: str) -> Request:
    request = Request({"type": "http", "method": "POST", "path": path, "headers": []})
    request.scope["route"] = SimpleNamespace(path=path)
    return request


def test_only_dedicated_group_can_finalize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGET_CALCULATOR_FINALIZER_GROUPS", raising=False)
    assert can_finalize_targets(auth_claims("owner@example.invalid")) is False
    monkeypatch.setenv("TARGET_CALCULATOR_FINALIZER_GROUPS", "unihub-target-finalizer")
    assert can_finalize_targets(auth_claims("owner@example.invalid", ["UNIHUB-TARGET-FINALIZER"])) is True
    assert can_finalize_targets(auth_claims("owner@example.invalid", ["unihub-admin"])) is False

    with pytest.raises(HTTPException) as exc_info:
        require_target_owner(_request("/api/target-calculator/scenarios/calculate"), auth_claims("owner@example.invalid"))
    assert exc_info.value.status_code == 403


def test_target_finalizer_groups_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_CALCULATOR_FINALIZER_GROUPS", "target-one, target-two")

    assert can_finalize_targets(auth_claims("owner@example.invalid", ["TARGET-TWO"])) is True
    assert can_finalize_targets(auth_claims("owner@example.invalid", ["unihub-grile-admin"])) is False


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


def test_helper_edges_for_seasonality_and_growth() -> None:
    assert percent_change(100, 0) is None
    assert seasonal_year_weights(3) == [Decimal("0.50"), Decimal("0.30"), Decimal("0.20")]
    assert weighted_available({"store": (None, Decimal("0.5"))}) is None
    factor, details = weighted_ratio(
        seasonality_pair_configuration("2026-07", 1),
        {"2025-06": Decimal("0"), "2025-07": Decimal("100")},
    )
    assert factor is None
    assert details[0]["ratio"] is None


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


def bounded_row(
    weight: str,
    floor: str,
    cap: str,
) -> dict[str, object]:
    return {
        "calculated_weight": Decimal(weight),
        "floor_target": Decimal(floor),
        "cap_target": Decimal(cap),
        "is_floor_limited": False,
        "is_cap_limited": False,
        "allocation_reason": "proportional",
        "flags": [],
    }


def test_bounded_allocation_handles_empty_input() -> None:
    assert allocate_with_bounds([], Decimal("100")) == ([], [])


def test_bounded_allocation_warns_when_budget_cannot_cover_floors() -> None:
    rows = [bounded_row("0.5", "100", "200"), bounded_row("0.5", "100", "200")]

    allocated, warnings = allocate_with_bounds(rows, Decimal("150"))

    assert sum(row["proposed_target"] for row in allocated) == Decimal("200.00")
    assert warnings
    assert all(row["is_floor_limited"] for row in allocated)
    assert all("FLOOR_APPLIED" in row["flags"] for row in allocated)


def test_bounded_allocation_warns_when_budget_exceeds_caps() -> None:
    rows = [bounded_row("0.5", "0", "50"), bounded_row("0.5", "0", "50")]

    allocated, warnings = allocate_with_bounds(rows, Decimal("150"))

    assert sum(row["proposed_target"] for row in allocated) == Decimal("100.00")
    assert warnings
    assert all(row["is_cap_limited"] for row in allocated)
    assert all("CAP_APPLIED" in row["flags"] for row in allocated)


def test_bounded_allocation_handles_zero_weights_and_iterative_bounds() -> None:
    zero_rows = [bounded_row("0", "0", "100"), bounded_row("0", "0", "100")]
    zero_allocated, zero_warnings = allocate_with_bounds(zero_rows, Decimal("50"))
    assert zero_warnings == []
    assert [row["proposed_target"] for row in zero_allocated] == [Decimal("25.00"), Decimal("25.00")]

    floor_rows = [bounded_row("0.99", "0", "100"), bounded_row("0.01", "40", "100")]
    floor_allocated, _ = allocate_with_bounds(floor_rows, Decimal("100"))
    assert floor_allocated[1]["is_floor_limited"] is True
    assert "FLOOR_APPLIED" in floor_allocated[1]["flags"]
    assert sum(row["proposed_target"] for row in floor_allocated) == Decimal("100.00")

    cap_rows = [bounded_row("0.99", "0", "50"), bounded_row("0.01", "0", "100")]
    cap_allocated, _ = allocate_with_bounds(cap_rows, Decimal("100"))
    assert cap_allocated[0]["is_cap_limited"] is True
    assert "CAP_APPLIED" in cap_allocated[0]["flags"]
    assert sum(row["proposed_target"] for row in cap_allocated) == Decimal("100.00")


def test_bounded_allocation_rounding_marks_bound_when_single_row_cannot_absorb_diff() -> None:
    positive_rows = [
        bounded_row("1", "0", "33.335"),
        bounded_row("1", "0", "33.335"),
        bounded_row("1", "0", "33.335"),
    ]
    positive_allocated, positive_warnings = allocate_with_bounds(positive_rows, Decimal("100"))
    assert positive_warnings == []
    assert sum(row["proposed_target"] for row in positive_allocated) == Decimal("100.00")
    assert any(row["is_cap_limited"] for row in positive_allocated)

    negative_rows = [
        bounded_row("1", "33.335", "100"),
        bounded_row("1", "33.335", "100"),
        bounded_row("1", "33.335", "100"),
    ]
    negative_allocated, negative_warnings = allocate_with_bounds(negative_rows, Decimal("100.01"))
    assert negative_warnings == []
    assert sum(row["proposed_target"] for row in negative_allocated) == Decimal("100.01")
    assert any(row["is_floor_limited"] for row in negative_allocated)


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
async def test_source_metrics_falls_back_to_historical_monthly_without_duplicates() -> None:
    repo, conn = make_repository_connection()
    conn.fetch = AsyncMock(return_value=[])

    await repo.get_source_metrics(["SITE01"], ["2023-07", "2025-07"])

    sql = conn.fetch.await_args.args[0]
    assert "historical_monthly_sales hms" in sql
    assert "NOT EXISTS" in sql
    assert "combined_sales" in sql
    assert conn.fetch.await_args.args[1] == ["2023-07", "2025-07"]
    assert conn.fetch.await_args.args[2] == ["SITE01"]


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
