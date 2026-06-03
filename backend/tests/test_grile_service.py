from __future__ import annotations

from datetime import date

from services.grile import _completed_days_for_month, _normalize_completion_window


def test_normalize_completion_window_removes_current_day_from_existing_run() -> None:
    completion_pct, missing_days, days_elapsed = _normalize_completion_window(
        month="2026-06",
        completion_pct=66.7,
        missing_days=[3],
        days_elapsed=3,
        today=date(2026, 6, 3),
    )

    assert completion_pct == 100.0
    assert missing_days == []
    assert days_elapsed == 2


def test_normalize_completion_window_keeps_yesterday_missing() -> None:
    completion_pct, missing_days, days_elapsed = _normalize_completion_window(
        month="2026-06",
        completion_pct=33.3,
        missing_days=[2, 3],
        days_elapsed=3,
        today=date(2026, 6, 3),
    )

    assert completion_pct == 50.0
    assert missing_days == [2]
    assert days_elapsed == 2


def test_completed_days_for_current_month_excludes_today() -> None:
    assert _completed_days_for_month("2026-06", today=date(2026, 6, 3)) == 2


def test_completed_days_for_past_month_uses_full_month() -> None:
    assert _completed_days_for_month("2026-05", today=date(2026, 6, 3)) == 31
