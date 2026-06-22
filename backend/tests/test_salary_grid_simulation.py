import pytest

from scripts.generate_salary_grid_simulation import (
    COMMISSION_SCENARIOS,
    _old_grid_comparable_salary,
    _old_grid_target_bonus,
    _qualitative_bonus,
    _qualitative_points,
    _target_bonus,
)


def test_commission_scenarios_are_ordered() -> None:
    assert COMMISSION_SCENARIOS == (
        ("2,5%", 0.025),
        ("2,7%", 0.027),
        ("3,0%", 0.030),
    )


def test_target_bonus_is_cumulative() -> None:
    assert _target_bonus(99.99) == 0
    assert _target_bonus(100) == 200
    assert _target_bonus(110) == 300
    assert _target_bonus(120) == 400


def test_old_grid_target_bonus_has_no_110_tier() -> None:
    assert _old_grid_target_bonus(99.99) == 0
    assert _old_grid_target_bonus(100) == 200
    assert _old_grid_target_bonus(119.99) == 200
    assert _old_grid_target_bonus(120) == 400


def test_old_grid_comparable_excludes_meals_and_overtime() -> None:
    assert _old_grid_comparable_salary(4239.22, 480, 0) == pytest.approx(3759.22)
    assert _old_grid_comparable_salary(3386, 480, 300) == 2606


def test_daily_average_has_no_two_point_band() -> None:
    low = _qualitative_points(
        daily_vs_colleague_pct=89.99,
        receipt_2plus_pct=35,
        focus_pct=8,
        average_item_value=100,
        premium_glass_pct=51,
    )
    equal = _qualitative_points(
        daily_vs_colleague_pct=100,
        receipt_2plus_pct=35,
        focus_pct=8,
        average_item_value=100,
        premium_glass_pct=51,
    )
    high = _qualitative_points(
        daily_vs_colleague_pct=110.01,
        receipt_2plus_pct=35,
        focus_pct=8,
        average_item_value=100,
        premium_glass_pct=51,
    )
    assert low[0] == 0
    assert equal[0] == 1
    assert high[0] == 3


def test_qualitative_bonus_is_eliminated_by_any_zero() -> None:
    assert _qualitative_bonus((3, 3, 3, 3, 3)) == 300
    assert _qualitative_bonus((3, 3, 3, 3, 2)) == 200
    assert _qualitative_bonus((3, 2, 2, 2, 2)) == 100
    assert _qualitative_bonus((3, 3, 3, 3, 0)) == 0
