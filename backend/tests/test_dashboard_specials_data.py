from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import PromoIncentiveSummary
from services.dashboard.queries import DashboardCampaignContext
from services.dashboard.specials_data import _get_special_cards_data


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


@pytest.mark.asyncio
async def test_special_cards_reuses_context_and_scans_incentive_rows_once() -> None:
    context = DashboardCampaignContext(
        config_error=None,
        promotion_definitions=[],
        promotion_definition=None,
        promotion_error=None,
        incentive_campaign={
            "month": "2026-05",
            "title": "Incentive",
            "subtitle": "",
            "description": "",
            "reward_map": {"C1": 10.0},
        },
        promotion_results=[],
        promo_excluded_units={},
    )
    conn = AsyncMock()
    conn.fetch.return_value = [
        FakeRow(
            is_meta=False,
            site_code="S1",
            item_code="C1",
            net_quantity=4,
            positive_quantity=5,
            return_quantity=-1,
            active_stores=0,
            active_agents=0,
            active_codes=0,
        ),
        FakeRow(
            is_meta=True,
            site_code=None,
            item_code=None,
            net_quantity=0,
            positive_quantity=0,
            return_quantity=0,
            active_stores=1,
            active_agents=2,
            active_codes=1,
        ),
    ]
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    connection_released = asyncio.Event()

    async def release_connection(*_args):
        connection_released.set()
        return False

    pool.acquire.return_value.__aexit__ = AsyncMock(side_effect=release_connection)
    shared_summary = PromoIncentiveSummary(
        incentive_qty=4,
        incentive_value=Decimal("40"),
    )

    async def shared_summary_after_connection_release():
        await connection_released.wait()
        return shared_summary

    summary_task = asyncio.create_task(shared_summary_after_connection_release())

    with (
        patch(
            "services.dashboard.specials_data.get_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ),
        patch(
            "services.dashboard.specials_data._load_dashboard_campaign_context",
            new_callable=AsyncMock,
        ) as mock_load_context,
        patch(
            "services.dashboard.specials_data._get_store_incentive_multipliers",
            new_callable=AsyncMock,
            return_value=({"S1": 1.0}, {"S1": 1.0}),
        ) as mock_store_multipliers,
        patch(
            "services.dashboard.specials_data._fetch_promo_incentive_summary",
            new_callable=AsyncMock,
        ) as mock_fetch_summary,
    ):
        cards = await asyncio.wait_for(
            _get_special_cards_data(
                "2026-05",
                None,
                "Regional curent",
                None,
                None,
                None,
                current_scope=True,
                include_closed_stores=False,
                campaign_context=context,
                promo_incentive_summary=summary_task,
            ),
            timeout=1,
        )

    assert [card.key for card in cards] == ["incentive"]
    assert cards[0].highlight_value == "40 RON"
    mock_load_context.assert_not_awaited()
    mock_fetch_summary.assert_not_awaited()
    conn.fetch.assert_awaited_once()
    sql = conn.fetch.await_args.args[0]
    assert "WITH filtered AS MATERIALIZED" in sql
    assert "UNION ALL" in sql
    assert "JOIN stores s ON s.site_code = agg.site_code" in sql
    assert "s.is_active = true" in sql
    multiplier_call = mock_store_multipliers.await_args
    assert multiplier_call is not None
    assert multiplier_call.kwargs == {
        "current_scope": True,
        "include_closed_stores": False,
    }
