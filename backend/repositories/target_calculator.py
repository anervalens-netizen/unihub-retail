from __future__ import annotations

import asyncpg

from .target_calculator_detail import TargetCalculatorDetailRepositoryMixin
from .target_calculator_scenarios import (
    TargetCalculatorScenariosRepositoryMixin,
    TargetScenarioAlgorithmMismatch,
    TargetScenarioFinalizedError,
    TargetScenarioVersionConflict,
)
from .target_calculator_sources import TargetCalculatorSourcesRepositoryMixin


class TargetCalculatorRepository(
    TargetCalculatorSourcesRepositoryMixin,
    TargetCalculatorScenariosRepositoryMixin,
    TargetCalculatorDetailRepositoryMixin,
):
    """Compatibility facade for Target Calculator persistence/query concerns."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool


__all__ = [
    "TargetCalculatorRepository",
    "TargetScenarioAlgorithmMismatch",
    "TargetScenarioFinalizedError",
    "TargetScenarioVersionConflict",
]
