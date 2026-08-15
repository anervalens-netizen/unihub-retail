"""Regression coverage for Romanian calendar cutoff event timestamps."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from services.sales_generation import SalesGenerationValidationError
from services.sales_generation_flow import _sales_event_cutoff


def test_calendar_cutoff_uses_bucharest_summer_midnight_before_utc() -> None:
    assert _sales_event_cutoff(date(2026, 8, 12)) == datetime(
        2026,
        8,
        11,
        21,
        0,
        tzinfo=timezone.utc,
    )


def test_calendar_cutoff_uses_bucharest_winter_midnight_before_utc() -> None:
    assert _sales_event_cutoff(date(2026, 1, 15)) == datetime(
        2026,
        1,
        14,
        22,
        0,
        tzinfo=timezone.utc,
    )


def test_aware_datetime_cutoff_preserves_the_absolute_instant() -> None:
    value = datetime.fromisoformat("2026-08-12T03:30:00+03:00")
    assert _sales_event_cutoff(value) == datetime(
        2026,
        8,
        12,
        0,
        30,
        tzinfo=timezone.utc,
    )


def test_naive_datetime_cutoff_is_rejected() -> None:
    with pytest.raises(
        SalesGenerationValidationError,
        match="timezone-aware",
    ):
        _sales_event_cutoff(datetime(2026, 8, 12, 0, 0))
