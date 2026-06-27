"""Tests for CampaignsService.get_promotions_incentives — mock-based."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.campaigns import CampaignsService


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


def _mock_pool_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.fetch_promo_total = AsyncMock(return_value=None)
    repo.fetch_promo_store_rows = AsyncMock(return_value=[])
    repo.fetch_incentive_store_rows = AsyncMock(return_value=[])
    repo.fetch_incentive_agent_rows = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service_and_conn(mock_repo):
    pool, conn = _mock_pool_conn()
    service = CampaignsService(mock_repo, pool)
    return service, conn


class TestPromoIncentivesNoConfig:
    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition", return_value=(None, None))
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    async def test_no_promo_no_incentive(self, mock_summary, mock_inc, mock_promo, mock_config, service_and_conn):
        service, conn = service_and_conn
        from models import PromoIncentiveSummary
        mock_summary.return_value = PromoIncentiveSummary()
        result = await service.get_promotions_incentives(
            "2026-05-01", "2026-05-31", None, None, None, None, None
        )
        assert result["promo_total_qty"] == 0
        assert result["top_stores"] == []
        assert result["top_agents"] == []
        assert result["incentive_categories"] == []
        assert result["has_active_promotion"] is False

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition")
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    async def test_with_active_promotion(self, mock_summary, mock_inc, mock_promo, mock_config, service_and_conn, mock_repo):
        service, conn = service_and_conn
        mock_promo.return_value = (
            {
                "title": "Promo Mai",
                "description": "Desc",
                "item_codes": ["COD1", "COD2"],
                "start_date": date(2026, 5, 1),
                "end_date": date(2026, 5, 31),
            },
            None,
        )
        from models import PromoIncentiveSummary
        mock_summary.return_value = PromoIncentiveSummary(
            promo_qty=100, promo_impact=Decimal("5000")
        )
        mock_repo.fetch_promo_total.return_value = FakeRow(total_qty=150)
        mock_repo.fetch_promo_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", qty=80, total_qty=100, firma="F1"),
        ]
        result = await service.get_promotions_incentives(
            "2026-05-01", "2026-05-31", None, None, None, None, None
        )
        assert result["has_active_promotion"] is True
        assert result["promo_total_qty"] == 150
        assert result["promo_title"] == "Promo Mai"
        assert len(result["top_stores"]) == 1

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition", return_value=(None, None))
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.campaigns._get_store_incentive_multipliers", new_callable=AsyncMock)
    async def test_with_incentive_campaign(self, mock_mults, mock_summary, mock_inc, mock_promo, mock_config, service_and_conn, mock_repo):
        service, conn = service_and_conn
        mock_inc.return_value = {
            "title": "Incentive Mai",
            "description": "Desc",
            "reward_map": {"COD1": 10.0},
            "subtitle": None,
        }
        mock_mults.return_value = ({"S1": 1.0}, {"S1": 1.05})
        from models import PromoIncentiveSummary
        mock_summary.return_value = PromoIncentiveSummary(
            incentive_qty=50, incentive_value=Decimal("500")
        )
        mock_repo.fetch_incentive_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", firma="F1", item_code="COD1", qty=30),
        ]
        mock_repo.fetch_incentive_agent_rows.return_value = [
            FakeRow(agent="Agent1", site_code="S1", item_code="COD1", qty=20),
            *[
                FakeRow(agent=f"Agent{index}", site_code="S1", item_code="COD1", qty=1)
                for index in range(2, 22)
            ],
        ]
        result = await service.get_promotions_incentives(
            "2026-05-01", "2026-05-31", None, None, None, None, None
        )
        assert result["incentive_title"] == "Incentive Mai"
        assert result["incentive_product_count"] == 1
        assert len(result["top_agents"]) == 21
        assert result["top_agents"][0].agent_name == "Agent1"
        assert result["top_agents"][0].incentive_potential == 200.0
        assert result["top_stores"][0].incentive_potential == 300.0

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition")
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.campaigns._get_store_incentive_multipliers", new_callable=AsyncMock)
    @patch("services.campaigns.compute_promo_copurchase", new_callable=AsyncMock)
    async def test_with_both_promo_and_incentive(self, mock_cp, mock_mults, mock_summary, mock_inc, mock_promo, mock_config, service_and_conn, mock_repo):
        service, conn = service_and_conn
        from services.promo_copurchase import PromoCoPurchaseResult
        mock_cp.return_value = PromoCoPurchaseResult()
        mock_promo.return_value = (
            {
                "title": "Promo",
                "description": "D",
                "item_codes": ["P1"],
                "start_date": date(2026, 5, 1),
                "end_date": date(2026, 5, 31),
            },
            None,
        )
        mock_inc.return_value = {
            "title": "Incentive",
            "description": "D",
            "reward_map": {"I1": 5.0},
            "subtitle": None,
        }
        mock_mults.return_value = ({"S1": 1.0}, {"S1": 1.0})
        from models import PromoIncentiveSummary
        mock_summary.return_value = PromoIncentiveSummary(
            promo_qty=50, promo_impact=Decimal("2500"),
            incentive_qty=30, incentive_value=Decimal("150"),
        )
        mock_repo.fetch_promo_total.return_value = FakeRow(total_qty=80)
        mock_repo.fetch_promo_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", qty=50, total_qty=70, firma="F1"),
        ]
        mock_repo.fetch_incentive_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", firma="F1", item_code="I1", qty=20),
        ]
        mock_repo.fetch_incentive_agent_rows.return_value = [
            FakeRow(agent="Agent1", site_code="S1", item_code="I1", qty=10),
        ]
        result = await service.get_promotions_incentives(
            "2026-05-01", "2026-05-31", None, None, None, None, None
        )
        assert result["has_active_promotion"] is True
        assert result["promo_title"] == "Promo"
        assert result["incentive_title"] == "Incentive"
        assert result["incentive_product_count"] == 1
        assert len(result["top_stores"]) == 1

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition")
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.campaigns._get_store_incentive_multipliers", new_callable=AsyncMock)
    @patch("services.campaigns.compute_promo_copurchase", new_callable=AsyncMock)
    async def test_copurchase_excludes_discounted_units_from_incentive(
        self, mock_cp, mock_mults, mock_summary, mock_inc, mock_promo, mock_config, service_and_conn, mock_repo
    ):
        """Unitatile reduse in promo (co-purchase) nu se incentiveaza: agent, magazin si headline."""
        service, conn = service_and_conn
        from decimal import Decimal
        from models import PromoIncentiveSummary
        from services.promo_copurchase import PromoCoPurchaseResult

        mock_promo.return_value = (
            {
                "title": "Promo",
                "description": "D",
                "item_codes": ["I1"],
                "start_date": date(2026, 6, 1),
                "end_date": date(2026, 6, 30),
            },
            None,
        )
        mock_inc.return_value = {
            "title": "Incentive", "description": "D",
            "reward_map": {"I1": 5.0}, "subtitle": None,
        }
        mock_mults.return_value = ({"S1": 1.0}, {"S1": 1.0})
        # Summary-ul Hub este deja corectat de promo actuals/co-purchase.
        mock_summary.return_value = PromoIncentiveSummary(
            incentive_qty=6, incentive_value=Decimal("30")
        )
        # 4 unitati reduse pe (S1, Agent1, I1) -> excluse din incentive
        mock_cp.return_value = PromoCoPurchaseResult(
            qualifying_bons=4, discounted_units=4,
            active_stores=1, active_agents=1,
            excluded_units={("S1", "Agent1", "I1"): 4},
        )
        mock_repo.fetch_promo_total.return_value = FakeRow(total_qty=10)
        mock_repo.fetch_promo_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", qty=6, total_qty=10, firma="F1"),
        ]
        mock_repo.fetch_incentive_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", firma="F1", item_code="I1", qty=10),
        ]
        mock_repo.fetch_incentive_agent_rows.return_value = [
            FakeRow(agent="Agent1", site_code="S1", item_code="I1", qty=10),
        ]
        result = await service.get_promotions_incentives(
            "2026-06-01", "2026-06-30", None, None, None, None, None
        )
        # Agent: (10 - 4) * 5 * 1.0 = 30, qty_sold = 6
        assert result["top_agents"][0].val_incentive == 30.0
        assert result["top_agents"][0].qty_sold == 6
        # Magazin: (10 - 4) * 5 * 1.0 = 30
        assert result["top_stores"][0].incentive_value == 30.0
        # Headline-ul vine din summary-ul deja corectat; nu se scade de doua ori.
        assert result["incentive_value"] == 30.0
        assert result["incentive_qty"] == 6
        # Tier 5 RON: 6 unitati incentivate
        assert result["incentive_categories"][0].qty == 6
        # Metrici promo co-purchase surfaced in Focus (consistente cu Hub)
        assert result["promo_qualifying_bons"] == 4
        assert result["promo_discounted_units"] == 4
        assert result["promo_active_stores"] == 1
        assert result["promo_active_agents"] == 1
        assert result["promo_agents"][0].agent_name == "Agent1"
        assert result["promo_agents"][0].promo_bons == 4
        # Top Magazine — Incentive: qty = unitati incentive nete, nu bonuri promo.
        assert result["top_stores"][0].qty == 6
        assert result["top_stores"][0].incentive_potential == 30.0
        # Top Magazine — Promo foloseste camp separat pentru bonuri co-purchase.
        assert result["top_stores"][0].promo_bons == 4

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definitions")
    @patch("services.campaigns.parse_promotion_definition")
    @patch("services.campaigns.load_promotion_rule_products")
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.campaigns._get_store_incentive_multipliers", new_callable=AsyncMock)
    @patch("services.campaigns.compute_promo_copurchase", new_callable=AsyncMock)
    @patch("services.campaigns.compute_promo_trigger_discounted", new_callable=AsyncMock)
    async def test_all_active_promo_discounted_units_are_excluded_from_incentive(
        self,
        mock_trigger,
        mock_cp,
        mock_mults,
        mock_summary,
        mock_inc,
        mock_products,
        mock_selected,
        mock_definitions,
        mock_config,
        service_and_conn,
        mock_repo,
    ):
        from models import PromoIncentiveSummary
        from services.promo_copurchase import PromoCoPurchaseResult

        selected = {
            "key": "selected",
            "title": "Selected",
            "description": "",
            "rule_type": "selected_item_copurchase",
            "item_codes": ["I1"],
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 30),
        }
        extra = {
            "key": "extra",
            "title": "Extra",
            "description": "",
            "rule_type": "trigger_discounted",
            "source_file": "extra.xlsx",
            "trigger_sheet": "A",
            "discounted_sheet": "B",
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 30),
        }
        mock_definitions.return_value = ([selected, extra], None)
        mock_selected.return_value = (selected, None)
        mock_products.side_effect = [
            ({"item_codes": ["I1"]}, None),
            ({"trigger_codes": ["T1"], "discounted_codes": ["I2"]}, None),
        ]
        mock_cp.return_value = PromoCoPurchaseResult(
            qualifying_bons=1,
            discounted_units=1,
            active_stores=1,
            active_agents=1,
            excluded_units={("S1", "Agent1", "I1"): 1},
        )
        mock_trigger.return_value = PromoCoPurchaseResult(
            qualifying_bons=2,
            discounted_units=2,
            active_stores=1,
            active_agents=1,
            excluded_units={("S1", "Agent1", "I2"): 2},
        )
        mock_inc.return_value = {
            "title": "Incentive",
            "description": "",
            "reward_map": {"I1": 5.0, "I2": 10.0},
            "subtitle": None,
        }
        mock_mults.return_value = ({"S1": 1.0}, {"S1": 1.0})
        mock_summary.return_value = PromoIncentiveSummary(
            incentive_qty=7,
            incentive_value=Decimal("75"),
        )
        mock_repo.fetch_promo_total.return_value = FakeRow(total_qty=1)
        mock_repo.fetch_promo_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", qty=1, total_qty=1, firma="F1"),
        ]
        mock_repo.fetch_incentive_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", firma="F1", item_code="I1", qty=5),
            FakeRow(site_code="S1", locatie="Store 1", firma="F1", item_code="I2", qty=5),
        ]
        service, conn = service_and_conn
        mock_repo.fetch_incentive_agent_rows.return_value = [
            FakeRow(agent="Agent1", site_code="S1", item_code="I1", qty=5),
            FakeRow(agent="Agent1", site_code="S1", item_code="I2", qty=5),
        ]

        result = await service.get_promotions_incentives(
            "2026-06-01", "2026-06-30", None, None, None, None, None, "selected"
        )

        assert result["promo_qualifying_bons"] == 1
        assert result["incentive_qty"] == 7
        assert result["incentive_value"] == 75.0
        assert result["top_agents"][0].qty_sold == 7
        assert result["top_agents"][0].val_incentive == 50.0

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition", return_value=(None, None))
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.campaigns._get_store_incentive_multipliers", new_callable=AsyncMock)
    async def test_incentive_no_promo_builds_stores_from_incentive(self, mock_mults, mock_summary, mock_inc, mock_promo, mock_config, service_and_conn, mock_repo):
        service, conn = service_and_conn
        mock_inc.return_value = {
            "title": "Inc",
            "description": "",
            "reward_map": {"I1": 8.0},
            "subtitle": None,
        }
        mock_mults.return_value = ({"S1": 0.5}, {"S1": 0.95})
        from models import PromoIncentiveSummary
        mock_summary.return_value = PromoIncentiveSummary()
        mock_repo.fetch_incentive_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", firma="F1", item_code="I1", qty=10),
        ]
        mock_repo.fetch_incentive_agent_rows.return_value = []
        result = await service.get_promotions_incentives(
            "2026-05-01", "2026-05-31", None, None, None, None, None
        )
        assert len(result["top_stores"]) == 1
        assert result["top_stores"][0].incentive_value > 0

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition")
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    async def test_with_filters(self, mock_summary, mock_inc, mock_promo, mock_config, service_and_conn, mock_repo):
        service, conn = service_and_conn
        mock_promo.return_value = (
            {
                "title": "Promo",
                "description": "",
                "item_codes": ["P1"],
                "start_date": date(2026, 5, 1),
                "end_date": date(2026, 5, 31),
            },
            None,
        )
        from models import PromoIncentiveSummary
        mock_summary.return_value = PromoIncentiveSummary()
        mock_repo.fetch_promo_total.return_value = FakeRow(total_qty=10)
        mock_repo.fetch_promo_store_rows.return_value = []
        result = await service.get_promotions_incentives(
            "2026-05-01", "2026-05-31", "FirmaA", "R1", "A1", "SITE01", "Agent1"
        )
        assert result is not None
