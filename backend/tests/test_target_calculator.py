from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from repositories.target_calculator import TargetCalculatorRepository
from services.target_calculator import (
    CALCULATION_METHOD,
    allocate_with_floors,
    realized_for_calculation,
    shift_month,
    source_month_configuration,
)


def test_source_months_are_derived_from_target_month() -> None:
    assert source_month_configuration("2026-06") == [
        {"month": "2025-05", "label": "Luna anterioara anului trecut", "role": "previous_year_reference"},
        {"month": "2025-06", "label": "Aceeasi luna anul trecut", "role": "year_over_year"},
        {"month": "2026-05", "label": "Luna anterioara / floor", "role": "floor_reference"},
    ]
    assert shift_month("2026-01", -1) == "2025-12"
    assert CALCULATION_METHOD == "weighted_floor_forecast_v2"


def test_partial_reference_sales_are_projected_for_calculation() -> None:
    assert realized_for_calculation(Decimal("2608548.73"), Decimal(31) / Decimal(26)) == Decimal("3110192.72")


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
    conn.fetchval.return_value = 8

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

    assert await repo.save_draft_scenario(scenario, rows) == 8

    insert_sql = conn.fetchval.await_args.args[0]
    delete_sql = conn.execute.await_args.args[0]
    assert "ON CONFLICT (target_month) DO UPDATE" in insert_sql
    assert "WHERE target_scenarios.status = 'draft'" in insert_sql
    assert "DELETE FROM target_scenario_rows" in delete_sql
    conn.executemany.assert_awaited_once()


@pytest.mark.asyncio
async def test_recalculation_cannot_overwrite_a_finalized_month() -> None:
    repo, conn = make_repository_connection()
    conn.fetchval.return_value = None

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

    assert await repo.save_draft_scenario(scenario, []) is None
    conn.execute.assert_not_awaited()
    conn.executemany.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_replaces_official_targets_with_exact_approved_cohort() -> None:
    repo, conn = make_repository_connection()
    conn.fetchrow.return_value = {
        "target_month": "2026-06",
        "total_target": Decimal("100.00"),
        "status": "draft",
    }
    conn.fetchval.return_value = Decimal("100.00")

    assert await repo.finalize_scenario(8) is True

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
    }
    conn.fetchval.return_value = Decimal("99.00")

    assert await repo.finalize_scenario(8) is False
    conn.execute.assert_not_awaited()
