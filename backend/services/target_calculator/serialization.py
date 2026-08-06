"""JSON boundary helpers for Target Calculator persistence projections."""

from __future__ import annotations

import json
from typing import Any


def serialize_header(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("total_target", "min_floor", "previous_month_floor_pct", "proposed_total", "final_total"):
        if key in row:
            row[key] = float(row[key] or 0)
    for key in ("source_months", "warnings", "calculation_params", "rule_set_snapshot"):
        if key in row and isinstance(row[key], str):
            row[key] = json.loads(row[key])
    row.setdefault("source_months", [])
    row.setdefault("warnings", [])
    row.setdefault("calculation_params", {})
    row.setdefault("rule_set_snapshot", None)
    if "store_count" in row:
        row["store_count"] = int(row["store_count"])
    row["pending_final_count"] = int(row.get("pending_final_count") or 0)
    return row


def serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("calculated_weight", "floor_target", "cap_target", "proposed_target"):
        if key in row:
            row[key] = float(row[key] or 0)
    for key in ("final_target", "manager_override_target"):
        row[key] = float(row[key]) if row.get(key) is not None else None
    for key in ("profitability_snapshot", "history", "calculation_details"):
        if isinstance(row.get(key), str):
            row[key] = json.loads(row[key])
    row.setdefault("calculation_details", {})
    return row
