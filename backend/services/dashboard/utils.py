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
    for key, value in [
        ("firma", normalize_filter(firma)),
        ("regional", normalize_filter(regional)),
        ("asm", normalize_filter(asm)),
        ("site_code", normalize_filter(site_code)),
        ("agent", normalize_filter(agent)),
    ]:
        if value is not None:
            params.append(value)
            positions[key] = len(params)
    return params, positions
