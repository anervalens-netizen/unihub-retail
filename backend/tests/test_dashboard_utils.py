"""Tests for dashboard specials and utility functions."""
from __future__ import annotations

import pytest
from datetime import date, timedelta


def test_format_currency():
    from services.dashboard_specials import format_currency

    assert format_currency(1500) == "1.500 RON"
    assert format_currency(1000000) == "1.000.000 RON"
    assert format_currency(0) == "0 RON"
    assert format_currency(99.9) == "100 RON"


def test_format_int():
    from services.dashboard_specials import format_int

    assert format_int(1234) == "1.234"
    assert format_int(0) == "0"
    assert format_int(1000000) == "1.000.000"


def test_format_percent():
    from services.dashboard_specials import format_percent

    assert format_percent(75.5) == "75.50%"
    assert format_percent(0) == "0.00%"
    assert format_percent(None) == "-"
    assert format_percent(100) == "100.00%"


def test_month_overlaps_period_full_overlap():
    from services.dashboard_specials import month_overlaps_period

    assert month_overlaps_period(
        "2026-03",
        date(2026, 3, 1),
        date(2026, 3, 31),
    ) is True


def test_month_overlaps_period_partial():
    from services.dashboard_specials import month_overlaps_period

    assert month_overlaps_period(
        "2026-03",
        date(2026, 2, 15),
        date(2026, 4, 15),
    ) is True


def test_month_overlaps_period_no_overlap():
    from services.dashboard_specials import month_overlaps_period

    assert month_overlaps_period(
        "2026-01",
        date(2026, 3, 1),
        date(2026, 3, 31),
    ) is False


def test_month_overlaps_period_before():
    from services.dashboard_specials import month_overlaps_period

    assert month_overlaps_period(
        "2026-05",
        date(2026, 1, 1),
        date(2026, 2, 28),
    ) is False


def test_month_overlaps_period_invalid_month():
    from services.dashboard_specials import month_overlaps_period

    assert month_overlaps_period(
        "invalid",
        date(2026, 1, 1),
        date(2026, 12, 31),
    ) is False


def test_month_overlaps_period_boundary():
    from services.dashboard_specials import month_overlaps_period

    assert month_overlaps_period(
        "2026-03",
        date(2026, 3, 15),
        date(2026, 3, 31),
    ) is True


def test_load_special_cards_config_no_env():
    from services.dashboard_specials import load_special_cards_config
    import os

    old = os.environ.pop("UNIHUB_HUB_SPECIALS_CONFIG", None)
    try:
        result, error = load_special_cards_config()
        assert isinstance(result, dict)
        assert "incentives" in result
    finally:
        if old:
            os.environ["UNIHUB_HUB_SPECIALS_CONFIG"] = old


def test_prewarm_special_cards_cache():
    from services.dashboard_specials import prewarm_special_cards_cache
    from services.dashboard_specials import _special_config_cache

    prewarm_special_cards_cache()
    # Prewarming should not raise exceptions even if config is missing
    assert isinstance(_special_config_cache, dict)
