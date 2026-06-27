"""Extended tests for dashboard utility functions."""
from __future__ import annotations

from datetime import date

from services.dashboard.utils import _shift_month, _month_day_range
from services.filters import build_scoped_params


class TestShiftMonth:
    def test_forward_one(self):
        assert _shift_month("2026-05", 1) == "2026-06"

    def test_backward_one(self):
        assert _shift_month("2026-01", -1) == "2025-12"

    def test_forward_twelve(self):
        assert _shift_month("2025-06", 12) == "2026-06"

    def test_backward_twelve(self):
        assert _shift_month("2026-06", -12) == "2025-06"

    def test_zero_offset(self):
        assert _shift_month("2026-05", 0) == "2026-05"

    def test_cross_year_boundary(self):
        assert _shift_month("2025-11", 3) == "2026-02"

    def test_backward_cross_year(self):
        assert _shift_month("2026-02", -3) == "2025-11"


class TestMonthDayRange:
    def test_normal_month(self):
        start, end, label = _month_day_range("2026-05", 15)
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 15)
        assert label == "01-15"

    def test_cutoff_beyond_month(self):
        start, end, label = _month_day_range("2026-02", 31)
        assert end == date(2026, 2, 28)
        assert label == "01-28"

    def test_cutoff_zero_clamps_to_one(self):
        start, end, label = _month_day_range("2026-05", 0)
        assert end == date(2026, 5, 1)

    def test_leap_year_february(self):
        start, end, label = _month_day_range("2028-02", 31)
        assert end == date(2028, 2, 29)

    def test_full_month(self):
        start, end, label = _month_day_range("2026-12", 31)
        assert end == date(2026, 12, 31)


class TestBuildScopedParams:
    def test_no_filters(self):
        params, positions = build_scoped_params(["2026-05"], firma=None, regional=None, asm=None, site_code=None, agent=None)
        assert params == ["2026-05"]
        assert positions == {}

    def test_all_filters(self):
        params, positions = build_scoped_params(
            ["2026-05"], firma="F1", regional="R1", asm="A1", site_code="SITE01", agent="Agent1"
        )
        assert params == ["2026-05", "SITE01", "Agent1"]
        assert "firma" not in positions
        assert "regional" not in positions
        assert "asm" not in positions
        assert positions["site_code"] == 2
        assert positions["agent"] == 3

    def test_sentinels_skipped(self):
        params, positions = build_scoped_params(
            ["2026-05"], firma="Toate", regional="Toti", asm=None, site_code="SITE01", agent=None
        )
        assert len(params) == 2
        assert "firma" not in positions
        assert "site_code" in positions

    def test_initial_params_preserved(self):
        params, positions = build_scoped_params(
            ["2026-05", 12], firma="F1", regional=None, asm=None, site_code=None, agent=None
        )
        assert params[0] == "2026-05"
        assert params[1] == 12
        assert params[2] == "F1"
        assert positions["firma"] == 3
