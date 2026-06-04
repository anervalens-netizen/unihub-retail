"""Unit tests for AgentsService — mock-based, no DB needed."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agents import AgentsService, get_prev_month, month_index_expr


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


def test_get_prev_month_standard():
    assert get_prev_month("2026-05") == "2026-04"
    assert get_prev_month("2026-01") == "2025-12"
    assert get_prev_month("2024-03") == "2024-02"


def test_get_prev_month_january():
    assert get_prev_month("2023-01") == "2022-12"


def test_month_index_expr():
    expr = month_index_expr("col")
    assert "col" in expr
    assert "SUBSTRING" in expr
    assert "12" in expr


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get_overview_stats = AsyncMock()
    repo.get_churn_count = AsyncMock(return_value=0)
    repo.get_movement = AsyncMock(return_value=[])
    repo.get_agents_list = AsyncMock(return_value=[])
    repo.get_agent_profile = AsyncMock()
    repo.get_agent_history = AsyncMock(return_value=[])
    repo.get_stores_coverage = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_repo):
    return AgentsService(mock_repo)


class TestAgentsOverview:
    @pytest.mark.asyncio
    async def test_overview_empty(self, service, mock_repo):
        mock_repo.get_overview_stats.return_value = None
        result = await service.get_agents_overview("2026-05", None, None, None, None, None)
        assert result.active_count == 0
        assert result.retention_rate is None
        assert result.churned_total_count == 0

    @pytest.mark.asyncio
    async def test_overview_with_data(self, service, mock_repo):
        mock_repo.get_overview_stats.return_value = FakeRow(
            active_count=25,
            new_count=5,
            reactivated_count=2,
            left_count=3,
            prev_active_count=20,
            stayed_count=17,
            stable_count=10,
            total_unique=50,
            avg_seniority=Decimal("8.5"),
        )
        mock_repo.get_churn_count.return_value = 7
        result = await service.get_agents_overview("2026-05", None, None, None, None, None)
        assert result.active_count == 25
        assert result.new_count == 5
        assert result.retention_rate == Decimal("85.0")
        assert result.churned_total_count == 7
        assert result.stability_rate == Decimal("40.0")

    @pytest.mark.asyncio
    async def test_overview_with_filters(self, service, mock_repo):
        mock_repo.get_overview_stats.return_value = FakeRow(
            active_count=5, new_count=1, reactivated_count=0,
            left_count=0, prev_active_count=0, stayed_count=0,
            stable_count=2, total_unique=5, avg_seniority=Decimal("3.0"),
        )
        result = await service.get_agents_overview("2026-05", "FirmaA", "RegX", None, None, None)
        assert result.active_count == 5
        assert result.retention_rate is None


class TestAgentsMovement:
    @pytest.mark.asyncio
    async def test_movement_empty(self, service):
        result = await service.get_agents_movement("2026-05", None, None, None, None, None)
        assert result.history == []

    @pytest.mark.asyncio
    async def test_movement_with_rows(self, service, mock_repo):
        mock_repo.get_movement.return_value = [
            FakeRow(month="2026-04", active=10, new=2, reactivated=1, churned=0, net_growth=2, is_baseline=False),
            FakeRow(month="2026-05", active=12, new=3, reactivated=0, churned=1, net_growth=2, is_baseline=False),
        ]
        result = await service.get_agents_movement("2026-05", None, None, None, None, None)
        assert len(result.history) == 2
        assert result.history[0].month == "2026-04"
        assert result.history[1].active == 12
        assert result.history[1].churned == 1


class TestAgentsList:
    @pytest.mark.asyncio
    async def test_list_empty(self, service):
        result = await service.get_agents_list("2026-05", None, None, None, None, None)
        assert result.items == []

    @pytest.mark.asyncio
    async def test_list_with_rows(self, service, mock_repo):
        mock_repo.get_agents_list.return_value = [
            FakeRow(
                agent="Agent1", store_name="Store A", active_in_month=True,
                is_new=True, is_reactivated=False, total_sales=Decimal("5000"),
                total_quantity=50, current_status="active",
            ),
        ]
        result = await service.get_agents_list("2026-05", None, None, None, None, None)
        assert len(result.items) == 1
        assert result.items[0].agent == "Agent1"
        assert result.items[0].is_new is True

    @pytest.mark.asyncio
    async def test_list_with_search(self, service, mock_repo):
        mock_repo.get_agents_list.return_value = []
        result = await service.get_agents_list("2026-05", "test_search", None, None, None, None)
        assert result.items == []
        call_args = mock_repo.get_agents_list.call_args
        assert "%test_search%" in call_args[0][1]


class TestAgentProfile:
    @pytest.mark.asyncio
    async def test_profile_not_found(self, service, mock_repo):
        mock_repo.get_agent_profile.return_value = None
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await service.get_agent_profile("NonExistent", "2026-05")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_profile_found(self, service, mock_repo):
        mock_repo.get_agent_profile.return_value = FakeRow(
            agent="Agent1", first_seen_month="2024-01", last_seen_month="2026-05",
            active_months_count=10, distinct_store_count=3, distinct_firma_count=1,
            distinct_regional_count=1, distinct_asm_count=1, months_since_last_seen=0,
            reactivation_count=1, longest_active_streak=8,
            career_total_sales=Decimal("50000"), career_total_quantity=500,
            avg_monthly_sales=Decimal("5000"), best_month="2026-03",
            best_month_sales=Decimal("8000"), current_status="active",
        )
        result = await service.get_agent_profile("Agent1", "2026-05")
        assert result.agent == "Agent1"
        assert result.current_status == "active"


class TestAgentHistory:
    @pytest.mark.asyncio
    async def test_history_empty(self, service):
        result = await service.get_agent_history("Agent1")
        assert result.history == []

    @pytest.mark.asyncio
    async def test_history_with_rows(self, service, mock_repo):
        mock_repo.get_agent_history.return_value = [
            FakeRow(
                month="2026-04", total_sales=Decimal("3000"),
                total_quantity=30, receipt_count=20,
                active_store_count=2, is_active=True,
            ),
        ]
        result = await service.get_agent_history("Agent1")
        assert len(result.history) == 1


class TestStoresCoverage:
    @pytest.mark.asyncio
    async def test_coverage_empty(self, service):
        result = await service.get_stores_coverage("2026-05", None, None, None)
        assert result.active_stores_count == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_coverage_with_data(self, service, mock_repo):
        mock_repo.get_stores_coverage.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", firma="F1", regional="R1",
                    asm="A1", agent_count=2, status="covered", has_changes=True),
            FakeRow(site_code="S2", locatie="Store 2", firma="F1", regional="R1",
                    asm="A1", agent_count=0, status="uncovered", has_changes=False),
            FakeRow(site_code="S3", locatie="Store 3", firma="F1", regional="R1",
                    asm="A1", agent_count=0, status="closed", has_changes=False),
        ]
        result = await service.get_stores_coverage("2026-05", "F1", "R1", "A1")
        assert result.active_stores_count == 1
        assert result.uncovered_stores_count == 1
        assert result.closed_stores_count == 1
        assert result.modified_stores_count == 1
        assert len(result.items) == 3
