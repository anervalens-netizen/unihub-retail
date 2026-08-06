"""Tests for CampaignsService.get_promotions_incentives — mock-based."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import PromoIncentiveSummary
from services.campaigns import CampaignsService
from services.promo_copurchase import PromoCoPurchaseResult
from services.promotion_evaluation import (
    PromotionEvaluation,
    PromotionEvaluationStatus,
)


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


def _mock_pool_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.transaction = MagicMock()
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = AsyncMock(return_value=conn)
    pool.release = AsyncMock(return_value=None)
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
    async def test_reuses_period_evaluations_calculated_by_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        service_and_conn,
    ) -> None:
        promotion = {
            "key": "promo",
            "title": "Promo",
            "description": "",
            "start_date": date(2026, 7, 1),
            "end_date": date(2026, 7, 31),
        }
        periods = [
            {
                "valid_from": date(2026, 7, 1),
                "valid_to": date(2026, 7, 9),
                "products": [{"item_code": "I1", "reward_value": 5.0}],
            },
            {
                "valid_from": date(2026, 7, 10),
                "valid_to": date(2026, 7, 31),
                "products": [{"item_code": "I1", "reward_value": 10.0}],
            },
        ]
        evaluation = PromotionEvaluation(
            result=PromoCoPurchaseResult(),
            item_codes=["I1"],
            rule_type="selected_item_copurchase",
            status=PromotionEvaluationStatus.COMPLETE,
        )

        monkeypatch.setattr(
            "services.campaigns.load_special_cards_config",
            lambda: ({}, None),
        )
        monkeypatch.setattr(
            "services.campaigns.parse_promotion_definitions",
            lambda _config, _month: ([promotion], None),
        )
        monkeypatch.setattr(
            "services.campaigns.parse_promotion_definition",
            lambda _config, _month, promotion_key=None: (promotion, None),
        )
        monkeypatch.setattr(
            "services.campaigns.get_incentive_campaign",
            AsyncMock(
                return_value={
                    "title": "Incentive",
                    "description": "",
                    "item_codes": ["I1"],
                    "periods": periods,
                }
            ),
        )
        monkeypatch.setattr(
            "services.campaigns._get_store_incentive_multipliers",
            AsyncMock(return_value=({}, {})),
        )
        compute = AsyncMock(return_value=evaluation)
        monkeypatch.setattr(
            "services.campaigns._compute_promotion_result",
            compute,
        )

        async def summary_with_cached_periods(**kwargs):
            context = kwargs["campaign_context"]
            for period in periods:
                key = context.period_evaluation_key(
                    promotion,
                    period["valid_from"],
                    period["valid_to"],
                )
                context.period_evaluations[key] = evaluation
            return PromoIncentiveSummary()

        monkeypatch.setattr(
            "services.campaigns._fetch_promo_incentive_summary",
            summary_with_cached_periods,
        )
        service, _conn = service_and_conn

        await service.get_promotions_incentives(
            "2026-07-01",
            "2026-07-31",
            None,
            None,
            None,
            None,
            None,
            view="incentive",
        )

        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_split_mechanisms_do_not_reuse_cumulative_actuals(
        self,
        monkeypatch: pytest.MonkeyPatch,
        service_and_conn,
    ) -> None:
        promotion = {
            "key": "promo",
            "title": "Promo",
            "description": "",
            "start_date": date(2026, 7, 1),
            "end_date": date(2026, 7, 31),
            "actuals_source_file": "promo.xlsx",
            "actuals_cutoff_date": "2026-07-24",
        }
        periods = [
            {
                "valid_from": date(2026, 7, 1),
                "valid_to": date(2026, 7, 9),
                "products": [{"item_code": "I1", "reward_value": 5.0}],
            },
            {
                "valid_from": date(2026, 7, 10),
                "valid_to": date(2026, 7, 31),
                "products": [{"item_code": "I1", "reward_value": 10.0}],
            },
        ]
        monkeypatch.setattr("services.campaigns.load_special_cards_config", lambda: ({}, None))
        monkeypatch.setattr(
            "services.campaigns.parse_promotion_definitions",
            lambda _config, _month: ([promotion], None),
        )
        monkeypatch.setattr(
            "services.campaigns.parse_promotion_definition",
            lambda _config, _month, promotion_key=None: (promotion, None),
        )
        monkeypatch.setattr(
            "services.campaigns.get_incentive_campaign",
            AsyncMock(return_value={
                "title": "Incentive",
                "description": "",
                "reward_map": {"I1": 10.0},
                "item_codes": ["I1"],
                "periods": periods,
            }),
        )
        monkeypatch.setattr(
            "services.campaigns._fetch_promo_incentive_summary",
            AsyncMock(return_value=PromoIncentiveSummary()),
        )
        monkeypatch.setattr(
            "services.campaigns._get_store_incentive_multipliers",
            AsyncMock(return_value=({}, {})),
        )
        evaluation = PromotionEvaluation(
            result=PromoCoPurchaseResult(),
            item_codes=["I1"],
            rule_type="selected_item_copurchase",
            status=PromotionEvaluationStatus.COMPLETE,
        )
        compute = AsyncMock(return_value=evaluation)
        monkeypatch.setattr("services.campaigns._compute_promotion_result", compute)
        service, _conn = service_and_conn

        await service.get_promotions_incentives(
            "2026-07-01",
            "2026-07-31",
            None,
            None,
            None,
            None,
            None,
            view="incentive",
            current_scope=True,
        )

        assert compute.await_count == 3
        assert compute.await_args_list[0].kwargs["definition"]["actuals_source_file"] == "promo.xlsx"
        assert compute.await_args_list[1].kwargs["definition"]["actuals_source_file"] is None
        assert compute.await_args_list[2].kwargs["definition"]["actuals_source_file"] is None
        assert all(call.kwargs["current_scope"] is True for call in compute.await_args_list)

    @pytest.mark.asyncio
    async def test_current_scope_is_forwarded_to_incentive_sources(
        self,
        monkeypatch: pytest.MonkeyPatch,
        service_and_conn,
        mock_repo,
    ) -> None:
        period = {
            "valid_from": date(2026, 7, 1),
            "valid_to": date(2026, 7, 31),
            "products": [{"item_code": "I1", "reward_value": 5.0}],
        }
        monkeypatch.setattr("services.campaigns.load_special_cards_config", lambda: ({}, None))
        monkeypatch.setattr(
            "services.campaigns.parse_promotion_definitions",
            lambda _config, _month: ([], None),
        )
        monkeypatch.setattr(
            "services.campaigns.parse_promotion_definition",
            lambda _config, _month, promotion_key=None: (None, None),
        )
        monkeypatch.setattr(
            "services.campaigns.get_incentive_campaign",
            AsyncMock(return_value={
                "title": "Incentive",
                "description": "",
                "reward_map": {"I1": 5.0},
                "item_codes": ["I1"],
                "periods": [period],
            }),
        )
        summary = AsyncMock(return_value=PromoIncentiveSummary())
        multipliers = AsyncMock(return_value=({}, {}))
        monkeypatch.setattr("services.campaigns._fetch_promo_incentive_summary", summary)
        monkeypatch.setattr("services.campaigns._get_store_incentive_multipliers", multipliers)
        service, _conn = service_and_conn

        await service.get_promotions_incentives(
            "2026-07-01",
            "2026-07-31",
            None,
            None,
            None,
            None,
            None,
            view="incentive",
            current_scope=True,
            include_closed_stores=False,
        )

        summary_call = summary.await_args
        multipliers_call = multipliers.await_args
        assert summary_call is not None
        assert multipliers_call is not None
        assert summary_call.kwargs["current_scope"] is True
        assert summary_call.kwargs["include_closed_stores"] is False
        assert multipliers_call.kwargs["current_scope"] is True
        mock_repo.fetch_incentive_store_rows.assert_awaited_once()
        assert mock_repo.fetch_incentive_store_rows.await_args.kwargs["current_scope"] is True
        assert mock_repo.fetch_incentive_agent_rows.await_args.kwargs["current_scope"] is True

    @pytest.mark.asyncio
    async def test_incentive_is_unavailable_when_any_active_promo_is_invalid(
        self,
        monkeypatch: pytest.MonkeyPatch,
        service_and_conn,
    ) -> None:
        selected = {
            "key": "selected",
            "title": "Selected",
            "description": "",
            "item_codes": ["P1"],
            "start_date": date(2026, 7, 1),
            "end_date": date(2026, 7, 31),
        }
        extra = {**selected, "key": "extra", "title": "Extra"}
        monkeypatch.setattr("services.campaigns.load_special_cards_config", lambda: ({}, None))
        monkeypatch.setattr(
            "services.campaigns.parse_promotion_definitions",
            lambda _config, _month: ([selected, extra], None),
        )
        monkeypatch.setattr(
            "services.campaigns.parse_promotion_definition",
            lambda _config, _month, promotion_key=None: (selected, None),
        )
        monkeypatch.setattr(
            "services.campaigns.get_incentive_campaign",
            AsyncMock(return_value={
                "title": "Incentive",
                "description": "",
                "reward_map": {"I1": 10.0},
                "item_codes": ["I1"],
            }),
        )
        monkeypatch.setattr(
            "services.campaigns._fetch_promo_incentive_summary",
            AsyncMock(return_value=PromoIncentiveSummary()),
        )
        monkeypatch.setattr(
            "services.campaigns._get_store_incentive_multipliers",
            AsyncMock(return_value=({}, {})),
        )
        monkeypatch.setattr(
            "services.campaigns._compute_promotion_result",
            AsyncMock(side_effect=[
                PromotionEvaluation(
                    result=PromoCoPurchaseResult(),
                    item_codes=["P1"],
                    rule_type="selected_item_copurchase",
                    status=PromotionEvaluationStatus.COMPLETE,
                ),
                PromotionEvaluation(
                    result=None,
                    item_codes=["P2"],
                    rule_type="selected_item_copurchase",
                    status=PromotionEvaluationStatus.INVALID,
                    warning="Sursa extra este invalida.",
                ),
            ]),
        )
        service, _conn = service_and_conn

        result = await service.get_promotions_incentives(
            "2026-07-01", "2026-07-31", None, None, None, None, None, "selected"
        )

        assert result["incentive_calculation_status"] == "invalid"
        assert result["incentive_qty"] is None
        assert result["incentive_value"] is None
        assert result["top_agents"] == []
        assert result["top_stores"] == []

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
            FakeRow(agent="Agent1", site_code="S1", locatie="Store 1", firma="F1", item_code="COD1", qty=20),
            *[
                FakeRow(agent=f"Agent{index}", site_code="S1", locatie="Store 1", firma="F1", item_code="COD1", qty=1)
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
        assert result["top_agents"][0].incentive_potential == 150.0
        assert result["top_stores"][0].incentive_potential == 300.0
        assert sum(row.qty_sold for row in result["top_agents"]) == result["top_stores"][0].qty
        assert sum(row.incentive_potential for row in result["top_agents"]) == result["top_stores"][0].incentive_potential
        assert result["incentive_category_breakdown"][0].qty == 30
        assert result["incentive_category_breakdown"][0].qualified_qty == 30
        assert result["incentive_category_breakdown"][0].potential == 300.0
        assert result["incentive_category_breakdown"][0].value == 300.0

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition", return_value=(None, None))
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.campaigns._get_store_incentive_multipliers", new_callable=AsyncMock)
    async def test_incentive_agent_rows_remain_scoped_to_each_store(
        self, mock_mults, mock_summary, mock_inc, mock_promo, mock_config,
        service_and_conn, mock_repo,
    ):
        service, _conn = service_and_conn
        mock_inc.return_value = {
            "title": "Incentive Mai", "description": "",
            "reward_map": {"COD1": 10.0}, "subtitle": None,
        }
        mock_mults.return_value = (
            {"S1": 1.0, "S2": 0.5, "S3": 0.0},
            {"S1": 1.0, "S2": 0.95, "S3": 0.8},
        )
        mock_summary.return_value = PromoIncentiveSummary()
        mock_repo.fetch_incentive_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", firma="F1", item_code="COD1", qty=2),
            FakeRow(site_code="S2", locatie="Store 2", firma="F1", item_code="COD1", qty=3),
            FakeRow(site_code="S3", locatie="Store 3", firma="F1", item_code="COD1", qty=4),
        ]
        mock_repo.fetch_incentive_agent_rows.return_value = [
            FakeRow(agent="Agent1", site_code="S1", locatie="Store 1", firma="F1", item_code="COD1", qty=2),
            FakeRow(agent="Agent1", site_code="S2", locatie="Store 2", firma="F1", item_code="COD1", qty=3),
            FakeRow(agent="Agent1", site_code="S3", locatie="Store 3", firma="F1", item_code="COD1", qty=4),
        ]

        result = await service.get_promotions_incentives(
            "2026-05-01", "2026-05-31", None, None, None, None, None
        )

        assert len(result["top_agents"]) == 3
        assert {row.store_name.split(" - ")[0] for row in result["top_agents"]} == {"S1", "S2", "S3"}
        for store in result["top_stores"]:
            site_code = store.store_name.split(" - ")[0]
            agents = [row for row in result["top_agents"] if row.store_name.startswith(f"{site_code} - ")]
            assert sum(row.qty_sold for row in agents) == store.qty
            assert sum(row.val_incentive for row in agents) == store.incentive_value
        category = result["incentive_category_breakdown"][0]
        assert category.qty == 9
        assert category.qualified_qty == 5
        assert category.potential == 90.0
        assert category.value == 35.0

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition", return_value=(None, None))
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.campaigns._get_store_incentive_multipliers", new_callable=AsyncMock)
    async def test_agent_returns_reconcile_to_canonical_store_incentive(
        self, mock_mults, mock_summary, mock_inc, mock_promo, mock_config,
        service_and_conn, mock_repo,
    ):
        service, _conn = service_and_conn
        mock_inc.return_value = {
            "title": "Incentive Mai", "description": "",
            "reward_map": {"COD1": 5.0}, "subtitle": None,
        }
        mock_mults.return_value = ({"S1": 1.0}, {"S1": 1.0})
        mock_summary.return_value = PromoIncentiveSummary()
        mock_repo.fetch_incentive_store_rows.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", firma="F1", item_code="COD1", qty=2),
        ]
        mock_repo.fetch_incentive_agent_rows.return_value = [
            FakeRow(agent="Agent1", site_code="S1", locatie="Store 1", firma="F1", item_code="COD1", qty=3),
            FakeRow(agent="Agent2", site_code="S1", locatie="Store 1", firma="F1", item_code="COD1", qty=-1),
        ]

        result = await service.get_promotions_incentives(
            "2026-05-01", "2026-05-31", None, None, None, None, None
        )

        assert sum(row.qty_sold for row in result["top_agents"]) == result["top_stores"][0].qty == 2
        assert sum(row.val_incentive for row in result["top_agents"]) == result["top_stores"][0].incentive_value == 10.0

    @pytest.mark.asyncio
    @patch("services.campaigns.load_special_cards_config", return_value=({}, None))
    @patch("services.campaigns.parse_promotion_definition")
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.campaigns._get_store_incentive_multipliers", new_callable=AsyncMock)
    @patch("services.promotion_evaluation.compute_promo_copurchase", new_callable=AsyncMock)
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
            FakeRow(agent="Agent1", site_code="S1", locatie="Store 1", firma="F1", item_code="I1", qty=10),
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
    @patch("services.promotion_evaluation.compute_promo_copurchase", new_callable=AsyncMock)
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
            FakeRow(agent="Agent1", site_code="S1", locatie="Store 1", firma="F1", item_code="I1", qty=10),
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
    @patch("services.promotion_evaluation.load_promotion_rule_products")
    @patch("services.campaigns.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.campaigns._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.campaigns._get_store_incentive_multipliers", new_callable=AsyncMock)
    @patch("services.promotion_evaluation.compute_promo_copurchase", new_callable=AsyncMock)
    @patch("services.promotion_evaluation.compute_promo_trigger_discounted", new_callable=AsyncMock)
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
            FakeRow(agent="Agent1", site_code="S1", locatie="Store 1", firma="F1", item_code="I1", qty=5),
            FakeRow(agent="Agent1", site_code="S1", locatie="Store 1", firma="F1", item_code="I2", qty=5),
        ]

        result = await service.get_promotions_incentives(
            "2026-06-01", "2026-06-30", None, None, None, None, None, "selected"
        )

        assert result["promo_qualifying_bons"] == 1
        assert result["incentive_qty"] == 7
        assert result["incentive_value"] == 50.0
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
