from __future__ import annotations

from decimal import Decimal

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
