from __future__ import annotations

from services.dashboard_specials import (
    build_incentive_card,
    extract_phone_model_keys,
    load_incentive_codes,
    parse_incentive_definition,
    parse_promotion_definitions,
    parse_promotion_definition,
)
from services.product_lists import normalize_column_name


def test_normalize_column_name_strips_diacritics() -> None:
    assert normalize_column_name("Site Code") == "site_code"
    assert normalize_column_name("Realizat bonus (%)") == "realizat_bonus"
    assert normalize_column_name("Regiune / zona") == "regiune_zona"


def test_parse_promotion_definition_requires_codes_and_valid_dates() -> None:
    definition, error = parse_promotion_definition(
        {
            "promotions": [
                {
                    "title": "Promo",
                    "item_codes": ["AA-01", "BB-02"],
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-31",
                }
            ]
        },
        "2026-03",
    )

    assert error is None
    assert definition is not None
    assert definition["item_codes"] == ["AA-01", "BB-02"]


def test_parse_promotion_definition_returns_none_for_wrong_month() -> None:
    definition, error = parse_promotion_definition(
        {
            "promotions": [
                {
                    "title": "Promo",
                    "item_codes": ["AA-01"],
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-31",
                }
            ]
        },
        "2026-04",
    )

    assert error is None
    assert definition is None


def test_parse_promotion_definitions_supports_selectable_rules() -> None:
    definitions, error = parse_promotion_definitions(
        {
            "promotions": [
                {
                    "key": "actuala",
                    "title": "Promo actuala",
                    "item_codes": ["AA-01"],
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                },
                {
                    "key": "folii",
                    "title": "Folii",
                    "rule_type": "same_model_screen_camera",
                    "source_file": "docs/Campanii-promo/folii.xlsx",
                    "trigger_sheet": "Folii ecran",
                    "discounted_sheet": "Folii Camera",
                    "start_date": "2026-06-10",
                    "end_date": "2026-06-30",
                },
            ]
        },
        "2026-06",
    )

    assert error is None
    assert [definition["key"] for definition in definitions] == ["actuala", "folii"]
    assert definitions[1]["rule_type"] == "same_model_screen_camera"


def test_parse_promotion_definitions_keeps_optional_actuals_report() -> None:
    definitions, error = parse_promotion_definitions(
        {
            "promotions": [
                {
                    "key": "actuala",
                    "title": "Promo actuala",
                    "item_codes": ["AA-01"],
                    "actuals_source_file": "/opt/Mobiup/docs/raport-promo-sursa.xls",
                    "actuals_sheet": "AccesoriPromoLunar",
                    "actuals_cutoff_date": "2026-06-21",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                },
            ]
        },
        "2026-06",
    )

    assert error is None
    assert definitions[0]["actuals_source_file"] == "/opt/Mobiup/docs/raport-promo-sursa.xls"
    assert definitions[0]["actuals_sheet"] == "AccesoriPromoLunar"
    assert definitions[0]["actuals_cutoff_date"] == "2026-06-21"


def test_parse_promotion_definition_can_select_by_key() -> None:
    definition, error = parse_promotion_definition(
        {
            "promotions": [
                {
                    "key": "actuala",
                    "item_codes": ["AA-01"],
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                },
                {
                    "key": "huse",
                    "rule_type": "trigger_discounted",
                    "source_file": "docs/Campanii-promo/huse.xlsx",
                    "trigger_sheet": "Capac protectie",
                    "discounted_sheet": "Husa Universala",
                    "start_date": "2026-06-10",
                    "end_date": "2026-06-30",
                },
            ]
        },
        "2026-06",
        promotion_key="huse",
    )

    assert error is None
    assert definition is not None
    assert definition["key"] == "huse"
    assert definition["rule_type"] == "trigger_discounted"


def test_extract_phone_model_keys_expands_slash_compatibility() -> None:
    assert extract_phone_model_keys(
        "FOLIE PROTECTIE CAMERA CELLARA PENTRU IPHONE 14 PRO/14 PRO MAX - TRANSPARENT"
    ) == {"IPHONE 14 PRO", "IPHONE 14 PRO MAX"}
    assert extract_phone_model_keys(
        "SET FOLII CAMERA CELLARA SAPPHIRE PENTRU SAMSUNG GALAXY S26 5G/S26 PLUS 5G - NEGRU"
    ) == {"SAMSUNG GALAXY S26 5G", "SAMSUNG GALAXY S26 PLUS 5G"}


def test_parse_incentive_definition_requires_month_and_file() -> None:
    definition, error = parse_incentive_definition(
        {
            "incentives": [
                {
                    "title": "Martie",
                    "month": "2026-03",
                    "source_file": "Martie 2026/Coduri incentive Martie.xlsx",
                    "reward_per_unit": 5,
                }
            ]
        },
        "2026-03",
    )

    assert error is None
    assert definition is not None
    assert definition["month"] == "2026-03"
    assert definition["reward_per_unit"] == 5


def test_parse_incentive_definition_returns_none_for_wrong_month() -> None:
    definition, error = parse_incentive_definition(
        {
            "incentives": [
                {
                    "title": "Martie",
                    "month": "2026-03",
                    "source_file": "Martie 2026/Coduri incentive Martie.xlsx",
                    "reward_per_unit": 5,
                }
            ]
        },
        "2026-04",
    )

    assert error is None
    assert definition is None


def test_load_incentive_codes_reads_real_file() -> None:
    from services.product_lists import get_data_dir

    source = get_data_dir() / "Incentiv Mobiup-Mobicell Aprilie 2026.xlsx"
    if not source.exists():
        import pytest

        pytest.skip(f"External fixture not present: {source}")
    codes, error = load_incentive_codes(
        {"source_file": "Incentiv Mobiup-Mobicell Aprilie 2026.xlsx"}
    )

    assert error is None
    assert codes is not None
    assert len(codes) > 0


def test_build_incentive_card_uses_net_quantity_bonus() -> None:
    card = build_incentive_card(
        "2026-03",
        {
            "title": "Incentive martie",
            "subtitle": "Bonus pe coduri eligibile",
            "description": "",
            "source_file": "Martie 2026/Coduri incentive Martie.xlsx",
            "month": "2026-03",
            "reward_per_unit": 5,
        },
        {
            "net_quantity": 21,
            "positive_quantity": 24,
            "return_quantity": -3,
            "active_stores": 5,
            "active_agents": 7,
            "active_codes": 9,
        },
    )

    assert card.status == "ready"
    assert card.highlight_value == "105 RON"
    assert card.metrics[0].value == "21"
    assert card.metrics[1].value == "3"
