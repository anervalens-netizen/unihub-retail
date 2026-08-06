"""Pure finalization precondition checks."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def finalization_error(scenario: dict[str, Any], calculation_method: str) -> str | None:
    if scenario.get("calculation_method") != calculation_method:
        return "formula_veche"
    if int(scenario.get("pending_final_count") or 0) > 0:
        return "targete_incomplete"
    if Decimal(str(scenario.get("final_total") or 0)).quantize(Decimal("0.01")) != Decimal(str(scenario.get("total_target") or 0)).quantize(Decimal("0.01")):
        return "total_nealiniat"
    return None
