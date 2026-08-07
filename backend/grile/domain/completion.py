from __future__ import annotations

import calendar
from datetime import date, datetime

from business_clock import business_today


COMPLETION_ALGORITHM_VERSION = 2


def coerce_business_date(value: date | datetime | None) -> date:
    if value is None:
        return business_today()
    if isinstance(value, datetime):
        return value.date()
    return value


def parse_month(month: str) -> tuple[int, int]:
    try:
        year_text, month_text = month.split("-", 1)
        year = int(year_text)
        month_number = int(month_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("month must use YYYY-MM") from exc
    if len(month) != 7 or len(year_text) != 4 or len(month_text) != 2 or not 1 <= month_number <= 12:
        raise ValueError("month must use YYYY-MM")
    return year, month_number


def completed_days_for_month(
    run_month: str,
    *,
    as_of: date | datetime | None = None,
    explicit_cutoff: date | None = None,
) -> int:
    """Return the deterministic completion window for one requested month.

    Past month: every calendar day. Current month: through yesterday. Future
    month: zero. An explicit cutoff is bounded to the requested month and is
    useful only for replaying an audited historical observation.
    """

    year, month_number = parse_month(run_month)
    current = coerce_business_date(as_of)
    last_day = calendar.monthrange(year, month_number)[1]

    if explicit_cutoff is not None:
        if (explicit_cutoff.year, explicit_cutoff.month) != (year, month_number):
            raise ValueError("completion cutoff must belong to run_month")
        return min(explicit_cutoff.day, last_day)

    requested = (year, month_number)
    current_month = (current.year, current.month)
    if requested < current_month:
        return last_day
    if requested > current_month:
        return 0
    return max(min(current.day - 1, last_day), 0)
