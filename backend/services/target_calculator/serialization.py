"""Response mapping for Target Calculator persistence projections."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from typing import Any

from services.target_calculator.rules import percent_change


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _percent_change_float(new_value: float, base_value: float) -> float | None:
    result = percent_change(new_value, base_value)
    return float(result) if result is not None else None


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


def strip_legacy_rule_fields(
    header: dict[str, Any], rows: list[dict[str, Any]]
) -> bool:
    """Keep the public projection of pre-rule-set scenarios unchanged."""
    legacy_unversioned = header.get("rule_set_snapshot") is None
    if not legacy_unversioned:
        for row in rows:
            row.pop("manager_override_actor", None)
        return False

    for key in (
        "rule_set_id",
        "rule_set_hash",
        "rule_set_snapshot",
        "calculation_input_sha256",
        "profitability_input_sha256",
    ):
        header.pop(key, None)
    for row in rows:
        for key in (
            "cap_target",
            "is_cap_limited",
            "manager_override_target",
            "manager_override_reason",
            "manager_override_actor",
            "manager_override_at",
            "manager_override_revision",
            "profitability_snapshot",
        ):
            row.pop(key, None)
    return True


def regional_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "store_count": 0,
            "floor_total": Decimal("0"),
            "proposed_total": Decimal("0"),
            "final_total": Decimal("0"),
            "current_month": None,
            "current_forecast_total": Decimal("0"),
            "last_year_base_month": None,
            "last_year_target_month": None,
            "last_year_base_total": Decimal("0"),
            "last_year_target_total": Decimal("0"),
        }
    )
    for row in rows:
        data = summary[row["regional"]]
        data["store_count"] += 1
        data["floor_total"] += _money(row["floor_target"])
        data["proposed_total"] += _money(row["proposed_target"])
        data["final_total"] += _money(row["final_target"])
        details = row.get("calculation_details") or {}
        if isinstance(details, str):
            details = json.loads(details)
        history = row.get("history") or []
        if isinstance(history, str):
            history = json.loads(history)

        current_month = details.get("current_month")
        current_forecast = details.get("current_forecast")
        if current_forecast is None:
            current_period = next(
                (item for item in history if item.get("role") == "floor_reference"),
                None,
            )
            current_month = current_month or (current_period or {}).get("month")
            current_forecast = (current_period or {}).get("realized")
        if current_month:
            data["current_month"] = current_month
        data["current_forecast_total"] += _money(current_forecast)

        seasonality = details.get("seasonality") or {}
        last_year = next(
            (
                item
                for item in seasonality.get("store_years") or []
                if item.get("year_offset") == 1
            ),
            None,
        )
        if last_year is None:
            base_period = next(
                (item for item in history if item.get("role") == "seasonality_base_y1"),
                None,
            )
            target_period = next(
                (item for item in history if item.get("role") == "seasonality_target_y1"),
                None,
            )
            last_year = {
                "base_month": (base_period or {}).get("month"),
                "target_month": (target_period or {}).get("month"),
                "base_value": (base_period or {}).get("realized"),
                "target_value": (target_period or {}).get("realized"),
            }
        if last_year.get("base_month"):
            data["last_year_base_month"] = last_year["base_month"]
        if last_year.get("target_month"):
            data["last_year_target_month"] = last_year["target_month"]
        data["last_year_base_total"] += _money(last_year.get("base_value"))
        data["last_year_target_total"] += _money(last_year.get("target_value"))
    return [
        {
            "regional": regional,
            **values,
            "floor_total": float(values["floor_total"]),
            "proposed_total": float(values["proposed_total"]),
            "final_total": float(values["final_total"]),
            "current_forecast_total": float(values["current_forecast_total"]),
            "last_year_base_total": float(values["last_year_base_total"]),
            "last_year_target_total": float(values["last_year_target_total"]),
            "proposed_growth_vs_current_pct": _percent_change_float(
                values["proposed_total"], values["current_forecast_total"]
            ) if values["current_forecast_total"] > 0 else None,
            "final_growth_vs_current_pct": _percent_change_float(
                values["final_total"], values["current_forecast_total"]
            ) if values["current_forecast_total"] > 0 else None,
            "last_year_growth_pct": _percent_change_float(
                values["last_year_target_total"], values["last_year_base_total"]
            ) if values["last_year_base_total"] > 0 else None,
        }
        for regional, values in sorted(summary.items())
    ]


def source_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "target": Decimal("0"),
            "realized": Decimal("0"),
            "actual_realized": Decimal("0"),
            "is_forecast": False,
            "forecast_factor": 1.0,
            "label": "",
        }
    )
    for row in rows:
        for period in row["history"]:
            values = summary[period["month"]]
            values["label"] = period["label"]
            values["target"] += _money(period["target"])
            values["realized"] += _money(period["realized"])
            values["actual_realized"] += _money(period.get("actual_realized", period["realized"]))
            if period.get("is_forecast", False):
                values["is_forecast"] = True
                values["forecast_factor"] = period.get("forecast_factor", 1.0)
    return [
        {
            "month": month,
            **values,
            "target": float(values["target"]),
            "realized": float(values["realized"]),
            "actual_realized": float(values["actual_realized"]),
            "attainment_pct": (
                float(values["realized"] / values["target"] * 100)
                if values["target"]
                else None
            ),
        }
        for month, values in summary.items()
    ]


def build_scenario_detail(
    header: dict[str, Any],
    rows: list[dict[str, Any]],
    profitability_summary: dict[str, Any],
) -> dict[str, Any]:
    legacy_unversioned = strip_legacy_rule_fields(header, rows)
    proposed_total = sum((_money(row["proposed_target"]) for row in rows), Decimal("0"))
    final_total = sum((_money(row["final_target"]) for row in rows), Decimal("0"))
    detail = {
        **header,
        "store_count": len(rows),
        "proposed_total": float(proposed_total),
        "final_total": float(final_total),
        "remaining_difference": float(_money(header["total_target"]) - final_total),
        "pending_final_count": sum(1 for row in rows if row["final_target"] is None),
        "floor_limited_count": sum(1 for row in rows if row["is_floor_limited"]),
        "manual_adjustments_count": sum(
            1
            for row in rows
            if row["final_target"] is not None
            and abs(_money(row["final_target"]) - _money(row["proposed_target"])) > Decimal("0.01")
        ),
        "rows": rows,
        "regional_summary": regional_summary(rows),
        "source_summary": source_summary(rows),
        "profitability_summary": profitability_summary,
    }
    if not legacy_unversioned:
        detail["cap_limited_count"] = sum(
            1 for row in rows if row.get("is_cap_limited")
        )
        detail["manager_overrides_count"] = sum(
            1 for row in rows if row.get("manager_override_target") is not None
        )
    return detail


def serialize_store_history(row: dict[str, Any]) -> dict[str, Any]:
    total_sales = _money(row["total_sales"])
    target = _money(row["target_value"])
    total_quantity = int(row["total_quantity"] or 0)
    receipt_count = int(row["receipt_count"] or 0)
    receipt_2plus = int(row["receipt_2plus_count"] or 0)
    focus_quantity = int(row["focus_quantity"] or 0)
    return {
        "month": row["import_month"],
        "total_sales": float(total_sales),
        "target_value": float(target),
        "target_pct": float(total_sales / target * 100) if target else None,
        "total_quantity": total_quantity,
        "receipt_count": receipt_count,
        "cartele_qty": int(row["cartele_qty"] or 0),
        "avg_receipt": float(total_sales / receipt_count) if receipt_count else None,
        "bon2acc_pct": receipt_2plus / receipt_count * 100 if receipt_count else None,
        "focus_pct": focus_quantity / total_quantity * 100 if total_quantity else None,
        "active_agents": int(row["active_agents"] or 0),
        "working_days": int(row["working_days"] or 0),
    }


def serialize_store_agent(row: dict[str, Any]) -> dict[str, Any]:
    total_sales = _money(row["total_sales"])
    total_quantity = int(row["total_quantity"] or 0)
    receipt_count = int(row["receipt_count"] or 0)
    receipt_2plus = int(row["receipt_2plus_count"] or 0)
    focus_quantity = int(row["focus_quantity"] or 0)
    return {
        "agent": row["agent"],
        "total_sales": float(total_sales),
        "sales_share_pct": float(row["sales_share_pct"] or 0),
        "total_quantity": total_quantity,
        "receipt_count": receipt_count,
        "avg_receipt": float(total_sales / receipt_count) if receipt_count else None,
        "bon2acc_pct": receipt_2plus / receipt_count * 100 if receipt_count else None,
        "focus_pct": focus_quantity / total_quantity * 100 if total_quantity else None,
        "active_months_16": int(row["active_months_16"] or 0),
        "sales_16m": float(row["sales_16m"] or 0),
    }


def build_store_detail(data: dict[str, Any]) -> dict[str, Any]:
    scenario = dict(data["scenario"])
    history = [serialize_store_history(dict(row)) for row in data["history"]]
    agents = [serialize_store_agent(dict(row)) for row in data["agents"]]
    latest = next(
        (
            row
            for row in reversed(history)
            if row["total_sales"] > 0 or row["target_value"] > 0
        ),
        None,
    )
    sales_values = [row["total_sales"] for row in history]
    best_month = max(history, key=lambda row: row["total_sales"]) if history else None
    avg_sales = sum(sales_values) / len(sales_values) if sales_values else 0
    return {
        "site_code": scenario["site_code"],
        "locatie": scenario["locatie"],
        "firma": scenario["firma"],
        "regional": scenario["regional"],
        "asm": scenario["asm"],
        "target_month": scenario["target_month"],
        "cohort_month": scenario["cohort_month"],
        "proposed_target": float(scenario["proposed_target"] or 0),
        "final_target": (
            float(scenario["final_target"])
            if scenario["final_target"] is not None
            else None
        ),
        "history": history,
        "latest": latest,
        "best_month": best_month,
        "avg_sales_16m": round(avg_sales, 2),
        "agents": agents,
    }
