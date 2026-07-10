"""Extended tests for dashboard_specials.py pure functions."""
from __future__ import annotations

from datetime import date

from services.dashboard_specials import (
    format_currency,
    format_int,
    format_percent,
    incentive_multiplier,
    month_overlaps_period,
    _parse_single_promotion,
    parse_promotion_definition,
    _parse_single_incentive,
    parse_incentive_definition,
    build_promotion_card,
    build_incentive_card,
)


class TestFormatters:
    def test_format_currency(self):
        assert format_currency(12345) == "12.345 RON"
        assert format_currency(0) == "0 RON"
        assert format_currency(1000000) == "1.000.000 RON"

    def test_format_int(self):
        assert format_int(12345) == "12.345"
        assert format_int(0) == "0"

    def test_format_percent(self):
        assert format_percent(85.5) == "85.50%"
        assert format_percent(None) == "-"
        assert format_percent(0) == "0.00%"


class TestMonthOverlapsPeriod:
    def test_month_in_range(self):
        assert month_overlaps_period("2026-05", date(2026, 5, 1), date(2026, 5, 31))

    def test_month_overlaps_partial(self):
        assert month_overlaps_period("2026-05", date(2026, 5, 15), date(2026, 6, 15))

    def test_month_before_range(self):
        assert not month_overlaps_period("2026-04", date(2026, 5, 1), date(2026, 6, 30))

    def test_month_after_range(self):
        assert not month_overlaps_period("2026-07", date(2026, 5, 1), date(2026, 6, 30))

    def test_invalid_month(self):
        assert not month_overlaps_period("invalid", date(2026, 5, 1), date(2026, 6, 30))


class TestIncentiveMultiplier:
    def test_zero_achievement(self):
        assert incentive_multiplier(0.0) == 0.0

    def test_below_threshold(self):
        assert incentive_multiplier(0.5) == 0.0

    def test_at_threshold(self):
        result = incentive_multiplier(0.9)
        assert result == 0.5

    def test_old_half_threshold_is_not_eligible(self):
        assert incentive_multiplier(0.89) == 0.0

    def test_99_percent_is_still_half(self):
        assert incentive_multiplier(0.99) == 0.5

    def test_above_target(self):
        result = incentive_multiplier(1.1)
        assert result >= 1.0

    def test_exact_100(self):
        result = incentive_multiplier(1.0)
        assert result >= 1.0


class TestParseSinglePromotion:
    def test_valid_promotion(self):
        raw = {
            "title": "Promotie Mai",
            "item_codes": ["COD1", "COD2"],
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
        }
        result, error = _parse_single_promotion(raw)
        assert error is None
        assert result is not None
        assert result["title"] == "Promotie Mai"
        assert len(result["item_codes"]) == 2

    def test_missing_codes(self):
        raw = {"start_date": "2026-05-01", "end_date": "2026-05-31"}
        result, error = _parse_single_promotion(raw)
        assert result is None
        assert "item_codes" in error

    def test_invalid_dates(self):
        raw = {"item_codes": ["COD1"], "start_date": "invalid", "end_date": "2026-05-31"}
        result, error = _parse_single_promotion(raw)
        assert result is None
        assert "start_date" in error or "format" in error

    def test_end_before_start(self):
        raw = {"item_codes": ["COD1"], "start_date": "2026-05-31", "end_date": "2026-05-01"}
        result, error = _parse_single_promotion(raw)
        assert result is None
        assert "invalida" in error


class TestParsePromotionDefinition:
    def test_no_promotions_key(self):
        result, error = parse_promotion_definition({}, "2026-05")
        assert result is None
        assert error is None

    def test_promotions_not_list(self):
        result, error = parse_promotion_definition({"promotions": "not a list"}, "2026-05")
        assert result is None
        assert "array" in error

    def test_promotions_match(self):
        config = {
            "promotions": [
                {
                    "title": "Promo Mai",
                    "item_codes": ["COD1"],
                    "start_date": "2026-05-01",
                    "end_date": "2026-05-31",
                }
            ]
        }
        result, error = parse_promotion_definition(config, "2026-05")
        assert error is None
        assert result is not None
        assert result["title"] == "Promo Mai"

    def test_promotions_no_match(self):
        config = {
            "promotions": [
                {
                    "title": "Promo Aprilie",
                    "item_codes": ["COD1"],
                    "start_date": "2026-04-01",
                    "end_date": "2026-04-30",
                }
            ]
        }
        result, error = parse_promotion_definition(config, "2026-05")
        assert result is None
        assert error is None

    def test_backward_compat_single(self):
        config = {
            "promotion": {
                "item_codes": ["COD1"],
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
            }
        }
        result, error = parse_promotion_definition(config, "2026-05")
        assert result is not None
        assert error is None

    def test_backward_compat_no_match(self):
        config = {
            "promotion": {
                "item_codes": ["COD1"],
                "start_date": "2026-04-01",
                "end_date": "2026-04-30",
            }
        }
        result, error = parse_promotion_definition(config, "2026-05")
        assert result is None


class TestParseSingleIncentive:
    def test_valid_incentive(self):
        raw = {
            "title": "Incentive Mai",
            "source_file": "incentive.xlsx",
            "month": "2026-05",
            "reward_per_unit": 5.0,
        }
        result, error = _parse_single_incentive(raw)
        assert error is None
        assert result is not None
        assert result["reward_per_unit"] == 5.0

    def test_no_source_file(self):
        raw = {"month": "2026-05"}
        result, error = _parse_single_incentive(raw)
        assert result is None
        assert "source_file" in error

    def test_no_month(self):
        raw = {"source_file": "file.xlsx"}
        result, error = _parse_single_incentive(raw)
        assert result is None
        assert "month" in error

    def test_invalid_reward(self):
        raw = {"source_file": "file.xlsx", "month": "2026-05", "reward_per_unit": "invalid"}
        result, error = _parse_single_incentive(raw)
        assert result is None
        assert "reward_per_unit" in error

    def test_null_reward(self):
        raw = {"source_file": "file.xlsx", "month": "2026-05", "reward_per_unit": None}
        result, error = _parse_single_incentive(raw)
        assert error is None
        assert result is not None
        assert result["reward_per_unit"] is None


class TestParseIncentiveDefinition:
    def test_no_incentives_key(self):
        result, error = parse_incentive_definition({}, "2026-05")
        assert result is None
        assert error is None

    def test_incentives_not_list(self):
        result, error = parse_incentive_definition({"incentives": "not a list"}, "2026-05")
        assert result is None
        assert "array" in error

    def test_incentives_match(self):
        config = {
            "incentives": [
                {"source_file": "file.xlsx", "month": "2026-05"},
            ]
        }
        result, error = parse_incentive_definition(config, "2026-05")
        assert result is not None

    def test_incentives_no_match(self):
        config = {
            "incentives": [
                {"source_file": "file.xlsx", "month": "2026-04"},
            ]
        }
        result, error = parse_incentive_definition(config, "2026-05")
        assert result is None

    def test_backward_compat_single(self):
        config = {
            "incentive": {"source_file": "file.xlsx", "month": "2026-05"},
        }
        result, error = parse_incentive_definition(config, "2026-05")
        assert result is not None

    def test_backward_compat_wrong_month(self):
        config = {
            "incentive": {"source_file": "file.xlsx", "month": "2026-04"},
        }
        result, error = parse_incentive_definition(config, "2026-05")
        assert result is None


class TestBuildPromotionCard:
    def test_no_definition_no_error(self):
        card = build_promotion_card("2026-05", None, None)
        assert card.key == "promotion"
        assert card.status == "missing_config"

    def test_config_error(self):
        card = build_promotion_card("2026-05", None, None, config_error="Config broken")
        assert card.status == "missing_config"

    def test_definition_error(self):
        card = build_promotion_card("2026-05", None, None, definition_error="Bad definition")
        assert card.status == "missing_config"
        assert "Bad definition" in card.description

    def test_with_definition_no_stats(self):
        definition = {
            "title": "Promo", "subtitle": "Sub",
            "description": "Desc", "coverage_note": None,
            "item_codes": ["C1"], "start_date": date(2026, 5, 1),
            "end_date": date(2026, 5, 31),
        }
        card = build_promotion_card("2026-05", definition, None)
        assert card.status == "no_data"
        assert card.title == "Promo"

    def test_with_definition_and_stats(self):
        definition = {
            "title": "Promo", "subtitle": "Sub",
            "description": "Desc", "coverage_note": "Coverage note",
            "item_codes": ["C1"], "start_date": date(2026, 5, 1),
            "end_date": date(2026, 5, 31),
        }
        stats = {
            "qualifying_bons": 80, "discounted_units": 80,
            "active_stores": 10, "active_agents": 5,
        }
        card = build_promotion_card("2026-05", definition, stats)
        assert card.status == "ready"
        assert len(card.metrics) == 3
        assert card.coverage_note == "Coverage note"
        assert card.highlight_value == "80"

    def test_out_of_period(self):
        definition = {
            "title": "Old Promo", "subtitle": "Sub",
            "description": "", "coverage_note": None,
            "item_codes": ["C1"], "start_date": date(2026, 3, 1),
            "end_date": date(2026, 3, 31),
        }
        card = build_promotion_card("2026-05", definition, None)
        assert card.status == "inactive"

    def test_no_description_auto(self):
        definition = {
            "title": "Promo", "subtitle": "Sub",
            "description": "", "coverage_note": None,
            "item_codes": ["C1", "C2"], "start_date": date(2026, 5, 1),
            "end_date": date(2026, 5, 31),
        }
        stats = {"qualifying_bons": 40, "discounted_units": 40, "active_stores": 5, "active_agents": 3}
        card = build_promotion_card("2026-05", definition, stats)
        assert "2" in card.description or "coduri" in card.description.lower()


class TestBuildIncentiveCard:
    def test_no_definition(self):
        card = build_incentive_card("2026-05", None, None)
        assert card.key == "incentive"
        assert card.status == "missing_config"

    def test_config_error(self):
        card = build_incentive_card("2026-05", None, None, config_error="Config broken")
        assert card.status == "missing_config"

    def test_definition_error(self):
        card = build_incentive_card("2026-05", None, None, definition_error="Bad def")
        assert card.status == "missing_config"

    def test_codes_error(self):
        definition = {
            "title": "Inc", "subtitle": "Sub",
            "description": "", "month": "2026-05",
            "reward_per_unit": 5.0, "source_file": "missing.xlsx",
        }
        card = build_incentive_card("2026-05", definition, None, codes_error="File not found")
        assert card.status == "missing_source"

    def test_wrong_month_inactive(self):
        definition = {
            "title": "Inc", "subtitle": "Sub",
            "description": "", "month": "2026-04",
            "reward_per_unit": 5.0,
        }
        card = build_incentive_card("2026-05", definition, None)
        assert card.status == "inactive"
        assert card.highlight_value == "2026-04"

    def test_wrong_month_no_reward_per_unit(self):
        definition = {
            "title": "Inc", "subtitle": "Sub",
            "description": "", "month": "2026-04",
            "reward_per_unit": None,
        }
        card = build_incentive_card("2026-05", definition, None)
        assert card.status == "inactive"
        assert card.metrics == []

    def test_wrong_month_with_reward_per_unit(self):
        definition = {
            "title": "Inc", "subtitle": "Sub",
            "description": "", "month": "2026-04",
            "reward_per_unit": 10.0,
        }
        card = build_incentive_card("2026-05", definition, None)
        assert card.status == "inactive"
        assert len(card.metrics) == 1

    def test_with_definition_no_stats(self):
        definition = {
            "title": "Incentive", "subtitle": "Sub",
            "description": "Desc", "month": "2026-05",
            "reward_per_unit": 5.0,
        }
        card = build_incentive_card("2026-05", definition, None)
        assert card.status == "no_data"

    def test_with_per_product_mode(self):
        definition = {
            "title": "Incentive", "subtitle": "Sub",
            "description": "", "month": "2026-05",
            "reward_per_unit": None,
        }
        stats = {
            "net_quantity": 200, "positive_quantity": 220,
            "return_quantity": 20, "incentive_value": 1000,
            "active_stores": 8, "active_agents": 4,
            "active_codes": 15,
        }
        card = build_incentive_card("2026-05", definition, stats)
        assert card.status == "ready"
        assert any("Coduri active" in m.label for m in card.metrics)

    def test_with_flat_reward_mode(self):
        definition = {
            "title": "Incentive", "subtitle": "Sub",
            "description": "", "month": "2026-05",
            "reward_per_unit": 5.0,
        }
        stats = {
            "net_quantity": 200, "positive_quantity": 220,
            "return_quantity": 20, "incentive_value": 1000,
            "active_stores": 8, "active_agents": 4,
            "active_codes": 15,
        }
        card = build_incentive_card("2026-05", definition, stats)
        assert card.status == "ready"
        assert "1.000 RON" in card.highlight_value
        assert any("Unitati nete" in m.label for m in card.metrics)
