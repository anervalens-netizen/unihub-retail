"""Characterization tests for the Target Calculator repository mixins.

The C6 decomposition split ``backend/repositories/target_calculator.py``
into three focused mixins (sources / scenarios / detail) plus a thin
facade. These tests exercise the public repository methods that the new
mixins own, using the same ``make_repository_connection``-style mock
pattern as the existing ``test_target_calculator.py`` suite.

Scope:
- cover each new method at least once via the real method body;
- pin the SQL intent (tables / joins / filters / order) so accidental
  schema drift is caught;
- pin the expected argument shape (positional or keyword) so the
  facade/mixin split cannot silently change the call sites used by
  the Target Calculator service layer.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from repositories.target_calculator import (
    TargetCalculatorRepository,
    TargetScenarioAlgorithmMismatch,
    TargetScenarioFinalizedError,
    TargetScenarioVersionConflict,
)


def _make_repository_connection() -> tuple[TargetCalculatorRepository, MagicMock]:
    conn = MagicMock()
    conn.fetchrow = AsyncMock()
    conn.fetchval = AsyncMock()
    conn.fetch = AsyncMock()
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


# ---------------------------------------------------------------------------
# Sources mixin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sources_get_latest_sales_month_returns_value() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchval.return_value = "2026-05"

    result = await repo.get_latest_sales_month()

    assert result == "2026-05"
    sql = conn.fetchval.await_args.args[0]
    assert "MAX(import_month)" in sql
    assert "FROM reporting_agent_month" in sql
    assert conn.fetchval.await_args.args[1:] == ()


@pytest.mark.asyncio
async def test_sources_get_latest_sales_month_with_before_month_uses_filter() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchval.return_value = "2026-04"

    result = await repo.get_latest_sales_month(before_month="2026-05")

    assert result == "2026-04"
    sql = conn.fetchval.await_args.args[0]
    assert "import_month < $1" in sql
    assert conn.fetchval.await_args.args[1:] == ("2026-05",)


@pytest.mark.asyncio
async def test_sources_get_target_total_returns_decimal_zero_when_missing() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchval.return_value = None

    result = await repo.get_target_total("2026-06")

    assert result == Decimal(0)
    sql = conn.fetchval.await_args.args[0]
    assert "FROM store_targets" in sql


@pytest.mark.asyncio
async def test_sources_get_target_total_returns_decimal_sum() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchval.return_value = Decimal("1234.56")

    result = await repo.get_target_total("2026-06")

    assert result == Decimal("1234.56")


@pytest.mark.asyncio
async def test_sources_get_active_cohort_passes_args_and_excludes_site() -> None:
    repo, conn = _make_repository_connection()
    conn.fetch.return_value = []

    await repo.get_active_cohort("2026-05", target_month="2026-06")

    sql = conn.fetch.await_args.args[0]
    args = conn.fetch.await_args.args
    assert "target_calculator_store_exclusions" in sql
    assert "is_active = TRUE" in sql
    assert "GROUP BY" in sql
    assert args[1] == "2026-05"
    assert args[2] == "2026-06"


@pytest.mark.asyncio
async def test_sources_get_target_rule_exception_master_returns_empty_for_empty_input() -> None:
    repo, conn = _make_repository_connection()

    result = await repo.get_target_rule_exception_master([])

    assert result == []
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_sources_get_target_rule_exception_master_returns_rows() -> None:
    repo, conn = _make_repository_connection()
    conn.fetch.return_value = [{"site_code": "S01", "locatie": "L01"}]

    result = await repo.get_target_rule_exception_master(["S01"])

    assert len(result) == 1
    sql = conn.fetch.await_args.args[0]
    assert "FROM stores" in sql
    assert conn.fetch.await_args.args[1] == ["S01"]


@pytest.mark.asyncio
async def test_sources_get_source_metrics_returns_empty_for_missing_args() -> None:
    repo, conn = _make_repository_connection()

    assert await repo.get_source_metrics([], ["2026-05"]) == []
    assert await repo.get_source_metrics(["S01"], []) == []
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_sources_get_source_metrics_uses_historical_fallback() -> None:
    repo, conn = _make_repository_connection()
    conn.fetch.return_value = []

    await repo.get_source_metrics(["S01"], ["2025-07"])

    sql = conn.fetch.await_args.args[0]
    assert "historical_monthly_sales" in sql
    assert "combined_sales" in sql
    assert conn.fetch.await_args.args[1] == ["2025-07"]
    assert conn.fetch.await_args.args[2] == ["S01"]


@pytest.mark.asyncio
async def test_sources_get_effective_target_rule_set_passes_target_month() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "id": 1,
        "version": 7,
        "effective_from_month": "2026-01",
        "effective_to_month": None,
        "rules": {},
        "rules_sha256": "deadbeef",
    }

    result = await repo.get_effective_target_rule_set("2026-06")

    assert result["id"] == 1
    sql = conn.fetchrow.await_args.args[0]
    assert "target_calculator_effective_rule_sets" in sql
    assert conn.fetchrow.await_args.args[1] == "2026-06"


@pytest.mark.asyncio
async def test_sources_get_profitability_inputs_short_circuits_on_empty() -> None:
    repo, conn = _make_repository_connection()

    result = await repo.get_profitability_inputs(site_codes=[], target_month="2026-06")

    assert result == {
        "pnl_months": [],
        "pnl_rows": [],
        "forecast_run": None,
        "forecast_rows": [],
    }
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_sources_get_profitability_inputs_aggregates_pnl_and_forecast() -> None:
    repo, conn = _make_repository_connection()
    conn.fetch.side_effect = [
        [],  # pnl months (empty -> second pnl query skipped)
    ]
    conn.fetchrow.return_value = None  # no forecast run

    result = await repo.get_profitability_inputs(
        site_codes=["S01"],
        target_month="2026-06",
    )

    assert result["pnl_months"] == []
    assert result["pnl_rows"] == []
    assert result["forecast_run"] is None
    assert result["forecast_rows"] == []
    # Single pnl months fetch (pnl rows query skipped due to short-circuit)
    assert conn.fetch.await_count == 1


# ---------------------------------------------------------------------------
# Scenarios mixin
# ---------------------------------------------------------------------------


def _scenario_payload() -> dict[str, Any]:
    return {
        "target_month": "2026-06",
        "cohort_month": "2026-05",
        "total_target": Decimal("100.00"),
        "min_floor": Decimal("0.00"),
        "previous_month_floor_pct": 0.05,
        "calculation_method": "weighted",
        "source_months": [{"month": "2026-05", "label": "current"}],
        "warnings": [],
        "calculation_params": {},
        "calculation_input_sha256": "aaa",
        "profitability_input_sha256": "bbb",
    }


@pytest.mark.asyncio
async def test_scenarios_save_draft_inserts_when_no_existing() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = None  # no existing scenario
    conn.fetchval.return_value = 42

    scenario_id = await repo.save_draft_scenario(
        _scenario_payload(), rows=[], expected_revision=None,
    )

    assert scenario_id == 42
    # pg_advisory lock + lookup + insert + delete + executemany
    conn.execute.assert_awaited()
    insert_sql = conn.fetchval.await_args.args[0]
    assert "INSERT INTO target_scenarios" in insert_sql


@pytest.mark.asyncio
async def test_scenarios_save_draft_updates_existing_draft() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "id": 8,
        "status": "draft",
        "revision": 2,
        "calculation_method": "weighted",
    }

    scenario_id = await repo.save_draft_scenario(
        _scenario_payload(), rows=[], expected_revision=2,
    )

    assert scenario_id == 8
    executed = [call.args[0] for call in conn.execute.await_args_list]
    assert any("UPDATE target_scenarios" in sql for sql in executed)


@pytest.mark.asyncio
async def test_scenarios_save_draft_rejects_finalized_existing() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "id": 8,
        "status": "finalized",
        "revision": 2,
        "calculation_method": "weighted",
    }

    with pytest.raises(TargetScenarioFinalizedError):
        await repo.save_draft_scenario(
            _scenario_payload(), rows=[], expected_revision=2,
        )


@pytest.mark.asyncio
async def test_scenarios_save_draft_rejects_calculation_method_mismatch() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "id": 8,
        "status": "draft",
        "revision": 2,
        "calculation_method": "legacy",
    }

    with pytest.raises(TargetScenarioAlgorithmMismatch):
        await repo.save_draft_scenario(
            _scenario_payload(), rows=[], expected_revision=2,
        )


@pytest.mark.asyncio
async def test_scenarios_save_draft_rejects_stale_revision() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "id": 8,
        "status": "draft",
        "revision": 3,
        "calculation_method": "weighted",
    }

    with pytest.raises(TargetScenarioVersionConflict):
        await repo.save_draft_scenario(
            _scenario_payload(), rows=[], expected_revision=2,
        )


@pytest.mark.asyncio
async def test_scenarios_save_draft_insert_rejects_revision_when_provided() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = None  # no existing scenario

    with pytest.raises(TargetScenarioVersionConflict):
        await repo.save_draft_scenario(
            _scenario_payload(), rows=[], expected_revision=1,
        )


@pytest.mark.asyncio
async def test_scenarios_list_scenarios_passes_limit() -> None:
    repo, conn = _make_repository_connection()
    conn.fetch.return_value = []

    await repo.list_scenarios(limit=7)

    sql = conn.fetch.await_args.args[0]
    assert "FROM target_scenarios ts" in sql
    assert "LEFT JOIN target_scenario_rows" in sql
    assert conn.fetch.await_args.args[1] == 7


@pytest.mark.asyncio
async def test_scenarios_get_scenario_passes_id() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = None

    await repo.get_scenario(99)

    sql = conn.fetchrow.await_args.args[0]
    assert "FROM target_scenarios ts" in sql
    assert "WHERE ts.id = $1" in sql
    assert conn.fetchrow.await_args.args[1] == 99


@pytest.mark.asyncio
async def test_scenarios_get_scenario_rows_passes_id() -> None:
    repo, conn = _make_repository_connection()
    conn.fetch.return_value = []

    await repo.get_scenario_rows(99)

    sql = conn.fetch.await_args.args[0]
    assert "FROM target_scenario_rows" in sql
    assert "WHERE scenario_id = $1" in sql
    assert conn.fetch.await_args.args[1] == 99


@pytest.mark.asyncio
async def test_scenarios_update_final_targets_rejects_finalized() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {"status": "finalized", "revision": 2}

    updated = await repo.update_final_targets(
        8,
        [{"site_code": "S01", "final_target": Decimal("10.00")}],
        expected_revision=2,
    )
    assert updated == 0


@pytest.mark.asyncio
async def test_scenarios_update_final_targets_rejects_stale_revision() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {"status": "draft", "revision": 3}

    with pytest.raises(TargetScenarioVersionConflict):
        await repo.update_final_targets(
            8,
            [{"site_code": "S01", "final_target": Decimal("10.00")}],
            expected_revision=2,
        )


@pytest.mark.asyncio
async def test_scenarios_update_final_targets_partial_returns_existing_count() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {"status": "draft", "revision": 2}
    conn.fetchval.return_value = 1  # only 1 row matches

    updated = await repo.update_final_targets(
        8,
        [
            {"site_code": "S01", "final_target": Decimal("10.00")},
            {"site_code": "INVALID", "final_target": Decimal("20.00")},
        ],
        expected_revision=2,
    )
    assert updated == 1


@pytest.mark.asyncio
async def test_scenarios_update_final_targets_empty_short_circuits() -> None:
    repo, conn = _make_repository_connection()

    updated = await repo.update_final_targets(8, [], expected_revision=2)
    assert updated == 0
    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_scenarios_update_final_targets_full_writes_executemany_and_revision() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {"status": "draft", "revision": 2}
    conn.fetchval.return_value = 2  # all 2 rows match

    updated = await repo.update_final_targets(
        8,
        [
            {"site_code": "S01", "final_target": Decimal("10.00"), "override_reason": "reason-1"},
            {"site_code": "S02", "final_target": Decimal("20.00"), "note": "note-2"},
        ],
        expected_revision=2,
        actor="owner-sub",
    )

    assert updated == 2
    # The CASE-based override SQL with $1/$2/$3/$4/$5/$6 must be the
    # executemany statement.
    update_sql, _ = conn.executemany.await_args.args
    assert "UPDATE target_scenario_rows" in update_sql
    assert "manager_override_target" in update_sql
    assert "manager_override_at = CASE" in update_sql
    # Revision-bump UPDATE on target_scenarios
    executed = [call.args[0] for call in conn.execute.await_args_list]
    assert any("revision = revision + 1" in sql for sql in executed)


@pytest.mark.asyncio
async def test_scenarios_finalize_writes_targets_and_marks_finalized() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "target_month": "2026-06",
        "total_target": Decimal("100.00"),
        "status": "draft",
        "revision": 2,
    }
    conn.fetchval.side_effect = [Decimal("100.00"), 0]  # 0 pending finals, total matches

    finalized = await repo.finalize_scenario(8, expected_revision=2)

    assert finalized is True
    executed = [call.args[0] for call in conn.execute.await_args_list]
    # DELETE orphans + UPSERT store_targets + mark scenario finalized
    assert any("DELETE FROM store_targets" in sql for sql in executed)
    assert any("INSERT INTO store_targets" in sql for sql in executed)
    assert any("status = 'finalized'" in sql for sql in executed)


@pytest.mark.asyncio
async def test_scenarios_finalize_rejects_finalized_scenario() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = None  # no scenario

    assert await repo.finalize_scenario(8, expected_revision=2) is False


@pytest.mark.asyncio
async def test_scenarios_finalize_rejects_stale_revision() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "target_month": "2026-06",
        "total_target": Decimal("100.00"),
        "status": "draft",
        "revision": 3,
    }

    with pytest.raises(TargetScenarioVersionConflict):
        await repo.finalize_scenario(8, expected_revision=2)


@pytest.mark.asyncio
async def test_scenarios_finalize_rejects_when_pending_finals() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "target_month": "2026-06",
        "total_target": Decimal("100.00"),
        "status": "draft",
        "revision": 2,
    }
    conn.fetchval.side_effect = [Decimal("80.00"), 2]  # 2 pending finals

    assert await repo.finalize_scenario(8, expected_revision=2) is False


@pytest.mark.asyncio
async def test_scenarios_finalize_rejects_total_mismatch() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "target_month": "2026-06",
        "total_target": Decimal("100.00"),
        "status": "draft",
        "revision": 2,
    }
    conn.fetchval.side_effect = [Decimal("99.00"), 0]  # 0 pending, wrong total

    assert await repo.finalize_scenario(8, expected_revision=2) is False


# ---------------------------------------------------------------------------
# Detail mixin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_get_store_detail_returns_none_when_no_scenario() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = None

    assert await repo.get_store_detail(scenario_id=8, site_code="S01") is None


@pytest.mark.asyncio
async def test_detail_get_store_detail_aggregates_history_and_agents() -> None:
    repo, conn = _make_repository_connection()
    conn.fetchrow.return_value = {
        "id": 8,
        "target_month": "2026-06",
        "cohort_month": "2026-05",
        "total_target": Decimal("100.00"),
        "site_code": "S01",
        "locatie": "L01",
        "firma": "F01",
        "regional": "R01",
        "asm": "A01",
        "proposed_target": Decimal("50.00"),
        "final_target": Decimal("50.00"),
        "history": "{}",
    }
    conn.fetch.side_effect = [[], []]  # history rows, agent rows

    result = await repo.get_store_detail(scenario_id=8, site_code="S01")

    assert result is not None
    assert "scenario" in result
    assert result["history"] == []
    assert result["agents"] == []
    # First fetch is history, second is agents
    history_sql = conn.fetch.call_args_list[0].args[0]
    agent_sql = conn.fetch.call_args_list[1].args[0]
    assert "month_axis" in history_sql
    assert "current_agents" in agent_sql


# ---------------------------------------------------------------------------
# Sources mixin: pnl/forecast helpers exercised via profitability_inputs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sources_get_profitability_inputs_uses_required_categories() -> None:
    repo, conn = _make_repository_connection()
    conn.fetch.side_effect = [
        [],  # pnl months query (short-circuits second pnl fetch)
    ]
    conn.fetchrow.return_value = None  # no forecast run

    await repo.get_profitability_inputs(
        site_codes=["S01"], target_month="2026-06",
    )

    pnl_sql = conn.fetch.call_args_list[0].args[0]
    assert "store_pnl_monthly pnl" in pnl_sql
    assert "category_code = ANY($2::TEXT[])" in pnl_sql

    forecast_run_sql = conn.fetchrow.await_args.args[0]
    assert "FROM ai_forecast_runs" in forecast_run_sql
    assert "metric = 'sales_value'" in forecast_run_sql


@pytest.mark.asyncio
async def test_sources_get_profitability_inputs_handles_present_forecast_run() -> None:
    repo, conn = _make_repository_connection()
    forecast_run = {
        "id": 17,
        "forecast_month": "2026-06",
        "source_month": "2026-05",
    }
    conn.fetch.side_effect = [
        [],  # pnl months (empty -> second pnl fetch skipped)
        [{"site_code": "S01", "forecast_sales": Decimal("9000")}],  # forecast rows
    ]
    conn.fetchrow.return_value = forecast_run

    result = await repo.get_profitability_inputs(
        site_codes=["S01"], target_month="2026-06",
    )

    assert result["forecast_run"] == forecast_run
    assert len(result["forecast_rows"]) == 1
    assert result["forecast_rows"][0]["site_code"] == "S01"


@pytest.mark.asyncio
async def test_sources_get_profitability_inputs_pnl_rows_when_three_months() -> None:
    repo, conn = _make_repository_connection()
    conn.fetch.side_effect = [
        [
            {"period": date(2026, 3, 1)},
            {"period": date(2026, 4, 1)},
            {"period": date(2026, 5, 1)},
        ],  # 3 distinct months -> trigger pnl_rows fetch
        [{"site_code": "S01", "category_code": "c11", "amount": Decimal("123.45")}],
    ]
    conn.fetchrow.return_value = None  # no forecast run

    result = await repo.get_profitability_inputs(
        site_codes=["S01"], target_month="2026-06",
    )

    assert len(result["pnl_rows"]) == 1
    assert result["pnl_rows"][0]["site_code"] == "S01"
    assert result["pnl_rows"][0]["amount"] == Decimal("123.45")
    assert result["pnl_months"] == ["2026-03", "2026-04", "2026-05"]
