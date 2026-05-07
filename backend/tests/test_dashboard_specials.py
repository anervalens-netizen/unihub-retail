from __future__ import annotations

from services.dashboard_specials import (
    build_incentive_card,
    load_incentive_codes,
    parse_incentive_definition,
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
