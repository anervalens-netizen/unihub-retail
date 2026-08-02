"""Tests for dashboard specials and utility functions."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest


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


def test_generated_promo_config_rejects_tampered_actuals(tmp_path: Path) -> None:
    from services.dashboard_specials import _generated_config_path

    generation_root = tmp_path / "promo_generations"
    generation_dir = generation_root / ("a" * 32)
    generation_dir.mkdir(parents=True)
    actuals_path = generation_dir / "promo_actuals.xlsx"
    actuals_path.write_bytes(b"approved")
    config_path = generation_dir / "hub_specials.json"
    config_bytes = json.dumps(
        {
            "promotions": [
                {
                    "key": "active",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                    "item_codes": ["I1"],
                    "actuals_source_file": str(actuals_path),
                }
            ]
        },
        sort_keys=True,
    ).encode()
    config_path.write_bytes(config_bytes)
    pointer = {
        "version": 1,
        "generation_id": "a" * 32,
        "config_file": f"{'a' * 32}/hub_specials.json",
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "actuals": [
            {
                "file": str(actuals_path),
                "sha256": hashlib.sha256(b"approved").hexdigest(),
            }
        ],
    }
    (generation_root / "current.json").write_text(
        json.dumps(pointer),
        encoding="utf-8",
    )

    assert _generated_config_path(tmp_path) == config_path
    actuals_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hashului aprobat"):
        _generated_config_path(tmp_path)


@pytest.mark.parametrize(
    ("promotions", "error"),
    [
        (
            [
                {
                    "key": "same",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-10",
                    "item_codes": ["I1"],
                },
                {
                    "key": "same",
                    "start_date": "2026-06-11",
                    "end_date": "2026-06-20",
                    "item_codes": ["I2"],
                },
            ],
            "duplicată",
        ),
        (
            [
                {
                    "key": "left",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-20",
                    "item_codes": ["I1"],
                },
                {
                    "key": "right",
                    "start_date": "2026-06-10",
                    "end_date": "2026-06-30",
                    "item_codes": ["I1"],
                },
            ],
            "suprapuse",
        ),
        (
            [
                {
                    "key": "cutoff",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                    "item_codes": ["I1"],
                    "actuals_source_file": "unused.xlsx",
                    "actuals_cutoff_date": "2026-07-01",
                }
            ],
            "Cutoff",
        ),
    ],
)
def test_validate_special_cards_config_is_all_or_nothing(
    promotions: list[dict[str, object]],
    error: str,
) -> None:
    from services.dashboard_specials import validate_special_cards_config

    with pytest.raises(ValueError, match=error):
        validate_special_cards_config({"promotions": promotions})
