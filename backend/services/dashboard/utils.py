"""Pure utilities for dashboard queries: month arithmetic and scoped-params builder."""
from __future__ import annotations

import calendar
from datetime import date

from services.filters import build_scoped_params as _build_scoped_params


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


def _expand_current_manager_scope(
    clauses: list[str],
    positions: dict[str, int],
    *,
    store_alias: str = "s",
) -> list[str]:
    """Treat a current-scope Regional selection as a current manager selection.

    In the Hub history filters, users may select a manager from the Regional field
    even when that person currently owns stores through the ASM column. When ASM
    is not explicitly selected, match either current regional or current ASM.

    The store_alias parameter controls which table alias is used in the emitted
    clauses (default "s" for the main stores join; "cs" for the cartela CTE).
    """
    regional_position = positions.get("regional")
    if not regional_position or "asm" in positions or "site_code" in positions:
        return clauses

    regional_clause = f"{store_alias}.regional = ANY(${regional_position}::TEXT[])"
    manager_clause = (
        f"({store_alias}.regional = ANY(${regional_position}::TEXT[]) "
        f"OR {store_alias}.asm = ANY(${regional_position}::TEXT[]))"
    )
    return [manager_clause if clause == regional_clause else clause for clause in clauses]
