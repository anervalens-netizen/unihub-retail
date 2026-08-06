"""Public Target Calculator facade with explicit, acyclic imports."""

from services.target_calculator.allocation import (
    TargetBudgetInfeasibleError,
    allocate_with_bounds,
    allocate_with_floors,
    money,
)
from services.target_calculator.calculations import _apply_rounding_difference, _normalize_bounds
from services.forecast import get_forecast_factor
from services.target_calculator.rules import percent_change, realized_for_calculation, weighted_available
from services.target_calculator.seasonality import (
    build_source_month_configuration,
    month_label_ro,
    seasonality_pair_configuration,
    seasonal_year_weights,
    shift_month,
    source_month_configuration,
    weighted_ratio,
)
from services.target_calculator.service import CALCULATION_METHOD, TargetCalculatorService

__all__ = [
    "TargetBudgetInfeasibleError",
    "TargetCalculatorService",
    "CALCULATION_METHOD",
    "allocate_with_bounds",
    "allocate_with_floors",
    "build_source_month_configuration",
    "money",
    "month_label_ro",
    "seasonality_pair_configuration",
    "seasonal_year_weights",
    "shift_month",
    "source_month_configuration",
    "weighted_ratio",
    "percent_change",
    "realized_for_calculation",
    "weighted_available",
    "_apply_rounding_difference",
    "_normalize_bounds",
    "get_forecast_factor",
]
