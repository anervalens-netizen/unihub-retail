"""Pure utilities for dashboard queries: month arithmetic and scoped-params builder."""
from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from services.filters import normalize_filter


def _shift_month(month: str, offset: int) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    absolute = year * 12 + (month_number - 1) + offset
    shifted_year, shifted_month_index = divmod(absolute, 12)
    return f"{shifted_year:04d}-{shifted_month_index + 1:02d}"


def _month_day_range(month: str, cutoff_day: int) -> tuple[date, date, str]:
    year, month_number = (int(part) for part in month.split("-"))
    _, last_day = calendar.monthrange(year, month_number)
    final_day = max(1, min(cutoff_day, last_day))
    start = date(year, month_number, 1)
    end = date(year, month_number, final_day)
    return start, end, f"01-{final_day:02d}"


def _build_scoped_params(
    initial_params: list[Any],
    *,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[list[Any], dict[str, int]]:
    params = list(initial_params)
    positions: dict[str, int] = {}
    normalized_site_code = normalize_filter(site_code)
    for key, value in [
        ("firma", None if normalized_site_code else normalize_filter(firma)),
        ("regional", None if normalized_site_code else normalize_filter(regional)),
        ("asm", None if normalized_site_code else normalize_filter(asm)),
        ("site_code", normalized_site_code),
        ("agent", normalize_filter(agent)),
    ]:
        if value is not None:
            params.append(value)
            positions[key] = len(params)
    return params, positions


def _expand_current_manager_scope(clauses: list[str], positions: dict[str, int]) -> list[str]:
    """Treat a current-scope Regional selection as a current manager selection.

    In the Hub history filters, users may select a manager from the Regional field
    even when that person currently owns stores through the ASM column. When ASM
    is not explicitly selected, match either current regional or current ASM.
    """
    regional_position = positions.get("regional")
    if not regional_position or "asm" in positions or "site_code" in positions:
        return clauses

    regional_clause = f"s.regional = ANY(string_to_array(${regional_position}::TEXT, ','))"
    manager_clause = (
        f"(s.regional = ANY(string_to_array(${regional_position}::TEXT, ',')) "
        f"OR s.asm = ANY(string_to_array(${regional_position}::TEXT, ',')))"
    )
    return [manager_clause if clause == regional_clause else clause for clause in clauses]
