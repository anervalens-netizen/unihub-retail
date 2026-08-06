"""Canonical SQL scope helpers for Campaigns-owned reporting queries."""
from __future__ import annotations

from services.filters import scoped_clauses


def campaign_scope_join(current_scope: bool, source_alias: str = "agg") -> str:
    return (
        f"JOIN stores s ON s.site_code = {source_alias}.site_code"
        if current_scope
        else ""
    )


def _expand_current_manager_scope(
    clauses: list[str],
    positions: dict[str, int],
    *,
    store_alias: str = "s",
) -> list[str]:
    regional_position = positions.get("regional")
    if not regional_position or "asm" in positions or "site_code" in positions:
        return clauses
    regional_clause = (
        f"{store_alias}.regional = ANY("
        f"string_to_array(${regional_position}::TEXT, ','))"
    )
    manager_clause = (
        f"({store_alias}.regional = ANY("
        f"string_to_array(${regional_position}::TEXT, ',')) "
        f"OR {store_alias}.asm = ANY("
        f"string_to_array(${regional_position}::TEXT, ',')))"
    )
    return [manager_clause if clause == regional_clause else clause for clause in clauses]


def campaign_scope_clauses(
    positions: dict[str, int],
    *,
    current_scope: bool,
    include_closed_stores: bool,
    source_alias: str = "agg",
    month_alias: str | None = None,
    month_position: int | None = None,
) -> list[str]:
    clauses = scoped_clauses(
        positions,
        site_alias=source_alias,
        store_alias="s" if current_scope else source_alias,
        agent_alias=source_alias,
        month_alias=month_alias,
        month_position=month_position,
    )
    if current_scope:
        clauses = _expand_current_manager_scope(clauses, positions)
    if current_scope and not include_closed_stores:
        clauses.append("s.is_active = true")
    return clauses
