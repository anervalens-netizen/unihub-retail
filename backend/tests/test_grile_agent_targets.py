from __future__ import annotations

from decimal import Decimal

import pytest

from services.grile_agent_targets import (
    build_resolved_rows,
    extract_agent_targets,
    manager_is_enabled,
)


def _range(value: object) -> dict[str, list[list[object]]]:
    return {"values": [[value]]}


def test_manager_disabled_keeps_zone_on_fallback() -> None:
    assert not manager_is_enabled(
        "Bogdan Radu",
        enabled_managers=("*",),
        disabled_managers=("Bogdan Radu", "Bogdana Costan"),
    )
    assert manager_is_enabled(
        "Andrei Stancu",
        enabled_managers=("*",),
        disabled_managers=("Bogdan Radu", "Bogdana Costan"),
    )


def test_extract_agent_targets_marks_missing_target_for_fallback() -> None:
    candidates = extract_agent_targets(
        month="2026-06",
        site_code="TEST",
        manager="Andrei Stancu",
        source_store_key="Mobiup/Test",
        value_ranges=[
            _range("Popescu Ana"),
            {"values": []},
            _range(""),
            {"values": []},
        ],
    )

    assert len(candidates) == 1
    assert candidates[0].status == "missing_agent_target"
    assert candidates[0].target_value is None


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", Decimal("NaN")])
def test_extract_agent_targets_rejects_non_finite_or_negative_targets(
    value: object,
) -> None:
    candidates = extract_agent_targets(
        month="2098-01",
        site_code="SYNTHETIC-SITE",
        manager="Synthetic manager",
        source_store_key="synthetic/store",
        value_ranges=[
            _range("Synthetic Alpha"),
            _range(value),
            _range(""),
            {"values": []},
        ],
    )

    assert len(candidates) == 1
    assert candidates[0].status == "missing_agent_target"
    assert candidates[0].target_value is None


def test_build_resolved_rows_uses_safe_matches_without_sum_validation() -> None:
    candidates = extract_agent_targets(
        month="2026-06",
        site_code="TEST",
        manager="Andrei Stancu",
        source_store_key="Mobiup/Test",
        value_ranges=[
            _range("Popescu Ana"),
            _range(10000),
            _range("Ionescu Maria"),
            _range(50000),
        ],
    )

    resolved, unresolved = build_resolved_rows(
        candidates,
        {"TEST": {"POPESCUANA", "IONESCUM"}},
    )

    assert unresolved == []
    assert [(row.agent, row.target_value) for row in resolved] == [
        ("POPESCUANA", Decimal("10000.00")),
        ("IONESCUM", Decimal("50000.00")),
    ]


def test_extract_agent_targets_supports_third_agent_slot() -> None:
    candidates = extract_agent_targets(
        month="2026-08",
        site_code="SUNPLZ",
        manager="Manager",
        source_store_key="Mobiup/SUNPLAZA BUCURESTI",
        value_ranges=[
            _range("Agent Unu"), _range(100),
            _range("Agent Doi"), _range(200),
            _range("Agent Trei"), _range(300),
        ],
    )

    assert [(item.slot, item.target_value) for item in candidates] == [
        (1, Decimal("100.00")),
        (2, Decimal("200.00")),
        (3, Decimal("300.00")),
    ]
