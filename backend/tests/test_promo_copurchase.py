"""Tests for promo co-purchase helper — aggregation logic + scope wiring."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from services.promo_copurchase import PromoCoPurchaseResult, compute_promo_copurchase


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


class TestExcludedAggregation:
    def test_excluded_by_site_item_sums_over_agents(self):
        result = PromoCoPurchaseResult(
            excluded_units={
                ("S1", "AgentA", "CL1"): 3,
                ("S1", "AgentB", "CL1"): 2,
                ("S2", "AgentA", "CL2"): 5,
            }
        )
        by_site_item = result.excluded_by_site_item()
        assert by_site_item[("S1", "CL1")] == 5  # 3 + 2 across agents
        assert by_site_item[("S2", "CL2")] == 5
        assert len(by_site_item) == 2

    def test_empty_result_defaults(self):
        result = PromoCoPurchaseResult()
        assert result.qualifying_bons == 0
        assert result.discounted_units == 0
        assert result.excluded_by_site_item() == {}


class TestComputePromoCoPurchase:
    @pytest.mark.asyncio
    async def test_no_item_codes_short_circuits(self):
        conn = AsyncMock()
        result = await compute_promo_copurchase(
            conn,
            month="2026-06",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            item_codes=[],
            firma=None, regional=None, asm=None, site_code=None, agent=None,
        )
        assert result == PromoCoPurchaseResult()
        conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_derives_aggregates_from_discounted_rows(self):
        conn = AsyncMock()
        # 1 discounted unit per qualifying bon, grouped by (site, agent, item)
        conn.fetch = AsyncMock(return_value=[
            FakeRow(site_code="S1", agent="Agent1", item_code="CL1", units=4),
            FakeRow(site_code="S1", agent="Agent2", item_code="CL2", units=1),
            FakeRow(site_code="S2", agent="Agent1", item_code="CL1", units=2),
            FakeRow(site_code="S3", agent="-", item_code="CL1", units=1),
        ])
        result = await compute_promo_copurchase(
            conn,
            month="2026-06",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            item_codes=["CL1", "CL2"],
            firma=None, regional=None, asm=None, site_code=None, agent=None,
        )
        assert result.qualifying_bons == 8  # 4 + 1 + 2 + 1
        assert result.discounted_units == 8
        assert result.active_stores == 3  # S1, S2, S3
        assert result.active_agents == 2  # Agent1, Agent2 ('-' excluded)
        assert result.excluded_units[("S1", "Agent1", "CL1")] == 4
        assert result.excluded_by_site_item()[("S1", "CL1")] == 4
