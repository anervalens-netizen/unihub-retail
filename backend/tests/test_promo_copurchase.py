"""Tests for promo co-purchase helper — aggregation logic + scope wiring."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from services.promo_copurchase import (
    PromoActualsError,
    PromoCoPurchaseResult,
    compute_promo_actuals_from_report,
    compute_promo_copurchase,
    compute_promo_same_model_pair,
)


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
            FakeRow(site_code="S1", agent="Agent1", item_code="CL1", units=4, gross_value=400),
            FakeRow(site_code="S1", agent="Agent2", item_code="CL2", units=1, gross_value=50),
            FakeRow(site_code="S2", agent="Agent1", item_code="CL1", units=2, gross_value=200),
            FakeRow(site_code="S3", agent="-", item_code="CL1", units=1, gross_value=100),
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
        assert result.discount_value == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_site_code_csv_scope_is_not_used_as_item_code_array(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        await compute_promo_copurchase(
            conn,
            month="2026-07",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            item_codes=["CL1", "CL2"],
            firma=None,
            regional=None,
            asm=None,
            site_code="FOCCRARF,CRFFEER",
            agent=None,
        )

        sql = conn.fetch.await_args.args[0]
        assert "st.item_code = ANY($4::TEXT[])" in sql
        assert "st.item_code = ANY($5::TEXT[])" not in sql
        assert "st.site_code = ANY(string_to_array($5::TEXT, ','))" in sql
        assert conn.fetch.await_args.args[5] == "FOCCRARF,CRFFEER"

    @pytest.mark.asyncio
    async def test_current_manager_scope_expands_regional_and_excludes_closed_stores(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        await compute_promo_copurchase(
            conn,
            month="2026-07",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            item_codes=["CL1"],
            firma=None,
            regional="Manager curent",
            asm=None,
            site_code=None,
            agent=None,
            current_scope=True,
            include_closed_stores=False,
        )

        sql = conn.fetch.await_args.args[0]
        assert "(s.regional = ANY(string_to_array($5::TEXT, ',')) OR s.asm = ANY(string_to_array($5::TEXT, ',')))" in sql
        assert "s.is_active = true" in sql


class TestComputePromoSameModelPair:
    @pytest.mark.asyncio
    async def test_matches_models_per_receipt_without_rejoining_mapping_rows(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(
            return_value=[
                FakeRow(
                    sale_date=date(2026, 7, 1),
                    site_code="S1",
                    agent="Agent1",
                    bon_nr="B1",
                    id=1,
                    item_code="SCR1",
                    unit_price=Decimal("120"),
                    quantity=1,
                ),
                FakeRow(
                    sale_date=date(2026, 7, 1),
                    site_code="S1",
                    agent="Agent1",
                    bon_nr="B1",
                    id=2,
                    item_code="CAM1",
                    unit_price=Decimal("80"),
                    quantity=1,
                ),
                FakeRow(
                    sale_date=date(2026, 7, 1),
                    site_code="S1",
                    agent="Agent1",
                    bon_nr="B1",
                    id=3,
                    item_code="CAM2",
                    unit_price=Decimal("50"),
                    quantity=1,
                ),
            ]
        )

        result = await compute_promo_same_model_pair(
            conn,
            month="2026-07",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            screen_code_models={"SCR1": {"phone-a"}},
            camera_code_models={
                "CAM1": {"phone-a"},
                "CAM2": {"phone-b"},
            },
            firma=None,
            regional=None,
            asm=None,
            site_code=None,
            agent=None,
        )

        sql = conn.fetch.await_args.args[0]
        assert "st.item_code = ANY($4::TEXT[])" in sql
        assert "st.item_code = ANY($5::TEXT[])" in sql
        assert "UNNEST" not in sql
        assert result.discounted_units == 1
        assert result.excluded_units[("S1", "Agent1", "CAM1")] == 1


class TestComputePromoActualsFromReport:
    @pytest.mark.asyncio
    async def test_no_actuals_source_returns_none_for_rule_fallback(self):
        conn = AsyncMock()
        result = await compute_promo_actuals_from_report(
            conn,
            month="2026-06",
            definition={},
            item_codes=["CL1"],
            firma=None,
            regional="Manager curent",
            asm=None,
            site_code=None,
            agent=None,
            current_scope=True,
            include_closed_stores=False,
        )
        assert result is None
        conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_configured_actuals_report_error_does_not_fallback_to_rules(self, tmp_path):
        source = tmp_path / "promo_actuals.xlsx"
        pd.DataFrame(
            [{"SiteCode": "S1", "Cod": "CL1", "Promo Luna Curenta": 5}]
        ).to_excel(source, sheet_name="Sheet1", index=False)

        conn = AsyncMock()
        with pytest.raises(PromoActualsError):
            await compute_promo_actuals_from_report(
                conn,
                month="2026-06",
                definition={
                    "actuals_source_file": str(source),
                    "actuals_sheet": "MissingSheet",
                    "actuals_cutoff_date": "2026-06-16",
                    "start_date": date(2026, 6, 1),
                    "end_date": date(2026, 6, 30),
                },
                item_codes=["CL1"],
                firma=None,
                regional=None,
                asm=None,
                site_code=None,
                agent=None,
            )
        conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_loads_report_units_and_allocates_to_agents(self, tmp_path):
        source = tmp_path / "promo_actuals.xlsx"
        pd.DataFrame(
            [
                {
                    "SiteCode": "S1",
                    "Cod": "CL1",
                    "Promo Luna Curenta": 5,
                    "PromoValoare Luna Curenta": 1000,
                },
                {
                    "SiteCode": "S1",
                    "Cod": "CL2",
                    "Promo Luna Curenta": 99,
                    "PromoValoare Luna Curenta": 9999,
                },
            ]
        ).to_excel(source, sheet_name="AccesoriPromoLunar", index=False)

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            return_value=[
                FakeRow(site_code="S1", item_code="CL1", promo_units=5, agent="Agent1", positive_qty=8),
                FakeRow(site_code="S1", item_code="CL1", promo_units=5, agent="Agent2", positive_qty=2),
            ]
        )

        result = await compute_promo_actuals_from_report(
            conn,
            month="2026-06",
            definition={
                "actuals_source_file": str(source),
                "actuals_sheet": "AccesoriPromoLunar",
                "actuals_cutoff_date": "2026-06-16",
                "start_date": date(2026, 6, 1),
                "end_date": date(2026, 6, 30),
            },
            item_codes=["CL1"],
            firma=None,
            regional="Manager curent",
            asm=None,
            site_code=None,
            agent=None,
            current_scope=True,
            include_closed_stores=False,
        )

        assert result is not None
        assert result.discounted_units == 5
        assert result.qualifying_bons == 5
        assert result.active_stores == 1
        assert result.active_agents == 2
        assert result.excluded_units[("S1", "Agent1", "CL1")] == 4
        assert result.excluded_units[("S1", "Agent2", "CL1")] == 1
        assert result.excluded_discount_values[("S1", "Agent1", "CL1")] == Decimal("160")
        assert result.excluded_discount_values[("S1", "Agent2", "CL1")] == Decimal("40")
        assert result.discount_value == Decimal("200")
        sql = conn.fetch.await_args.args[0]
        assert "(s.regional = ANY(string_to_array($7::TEXT, ',')) OR s.asm = ANY(string_to_array($7::TEXT, ',')))" in sql
        assert "s.is_active = true" in sql

    @pytest.mark.asyncio
    async def test_agent_filter_is_applied_after_allocation(self, tmp_path):
        source = tmp_path / "promo_actuals.xlsx"
        pd.DataFrame(
            [{"SiteCode": "S1", "Cod": "CL1", "Promo Luna Curenta": 5}]
        ).to_excel(source, sheet_name="AccesoriPromoLunar", index=False)

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            return_value=[
                FakeRow(site_code="S1", item_code="CL1", promo_units=5, agent="Agent1", positive_qty=8),
                FakeRow(site_code="S1", item_code="CL1", promo_units=5, agent="Agent2", positive_qty=2),
            ]
        )

        result = await compute_promo_actuals_from_report(
            conn,
            month="2026-06",
            definition={
                "actuals_source_file": str(source),
                "actuals_sheet": "AccesoriPromoLunar",
                "actuals_cutoff_date": "2026-06-16",
                "start_date": date(2026, 6, 1),
                "end_date": date(2026, 6, 30),
            },
            item_codes=["CL1"],
            firma=None,
            regional=None,
            asm=None,
            site_code=None,
            agent="Agent2",
        )

        assert result is not None
        assert result.discounted_units == 1
        assert result.excluded_units == {("S1", "Agent2", "CL1"): 1}
