"""Scenario status and revision policy helpers."""

from __future__ import annotations

from typing import Any


def is_editable_scenario(scenario: dict[str, Any]) -> bool:
    return scenario.get("status") == "draft"


def has_pending_final_targets(scenario: dict[str, Any]) -> bool:
    return int(scenario.get("pending_final_count") or 0) > 0
