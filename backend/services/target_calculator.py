from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from typing import Any, TypedDict

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from repositories.target_calculator import TargetCalculatorRepository
from services.forecast import get_forecast_factor

MONEY = Decimal("0.01")
DEFAULT_MIN_FLOOR = Decimal("35000")
DEFAULT_PREVIOUS_MONTH_FLOOR_PCT = Decimal("0.90")
CALCULATION_METHOD = "weighted_floor_forecast_v2"


class SourceMetric(TypedDict):
    target: Decimal
    actual_realized: Decimal
    realized: Decimal
    forecast_factor: Decimal
    is_forecast: bool


class PeriodTotals(TypedDict):
    target: Decimal
    realized: Decimal


def money(value: Decimal | int | str | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def realized_for_calculation(actual_realized: Decimal, forecast_factor: Decimal) -> Decimal:
    return money(actual_realized * forecast_factor)


def shift_month(month: str, offset: int) -> str:
    try:
        year, month_number = (int(value) for value in month.split("-"))
        if month_number < 1 or month_number > 12:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Luna trebuie sa fie in format YYYY-MM") from exc
    index = year * 12 + month_number - 1 + offset
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def source_month_configuration(target_month: str) -> list[dict[str, str]]:
    return [
        {
            "month": shift_month(target_month, -13),
            "label": "Luna anterioara anului trecut",
            "role": "previous_year_reference",
        },
        {"month": shift_month(target_month, -12), "label": "Aceeasi luna anul trecut", "role": "year_over_year"},
        {"month": shift_month(target_month, -1), "label": "Luna anterioara / floor", "role": "floor_reference"},
    ]


def allocate_with_floors(
    rows: list[dict[str, Any]],
    requested_total: Decimal,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Allocate a budget proportionally while honoring store minimums."""
    warnings: list[str] = []
    if not rows:
        return rows, warnings

    requested_total = money(requested_total)
    floor_total = sum((row["floor_target"] for row in rows), Decimal("0"))
    if floor_total > requested_total:
        for row in rows:
            row["proposed_target"] = money(row["floor_target"])
            row["is_floor_limited"] = True
        warnings.append(
            "Bugetul total este mai mic decat suma pragurilor minime; propunerea depaseste bugetul pentru a respecta floor-ul."
        )
        return rows, warnings

    remaining = set(range(len(rows)))
    assigned: dict[int, Decimal] = {}
    remaining_budget = requested_total

    while remaining:
        weight_total = sum((rows[index]["calculated_weight"] for index in remaining), Decimal("0"))
        allocations: dict[int, Decimal] = {}
        for index in remaining:
            if weight_total > 0:
                allocations[index] = remaining_budget * rows[index]["calculated_weight"] / weight_total
            else:
                allocations[index] = remaining_budget / Decimal(len(remaining))

        below_floor = {
            index for index in remaining
            if allocations[index] < rows[index]["floor_target"]
        }
        if not below_floor:
            assigned.update(allocations)
            break

        for index in below_floor:
            assigned[index] = rows[index]["floor_target"]
            remaining_budget -= rows[index]["floor_target"]
            rows[index]["is_floor_limited"] = True
        remaining -= below_floor

    for index, row in enumerate(rows):
        row["proposed_target"] = money(assigned[index])

    rounded_total = sum((row["proposed_target"] for row in rows), Decimal("0"))
    difference = requested_total - rounded_total
    if difference:
        adjustable = [
            row for row in rows
            if row["proposed_target"] + difference >= row["floor_target"]
        ]
        target_row = max(adjustable or rows, key=lambda row: row["proposed_target"])
        target_row["proposed_target"] = money(target_row["proposed_target"] + difference)

    return rows, warnings


class TargetCalculatorService:
    def __init__(self, repo: TargetCalculatorRepository):
        self.repo = repo

    async def get_context(self) -> dict[str, Any]:
        latest_month = await self.repo.get_latest_sales_month()
        if not latest_month:
            raise HTTPException(status_code=404, detail="Nu exista date de vanzari pentru calculator.")
        suggested_month = shift_month(latest_month, 1)
        target_total = await self.repo.get_target_total(suggested_month)
        if target_total == 0:
            target_total = await self.repo.get_target_total(latest_month)
        cohort = await self.repo.get_active_cohort(latest_month)
        return {
            "latest_sales_month": latest_month,
            "suggested_target_month": suggested_month,
            "suggested_cohort_month": latest_month,
            "suggested_total_target": float(target_total),
            "default_min_floor": float(DEFAULT_MIN_FLOOR),
            "default_previous_month_floor_pct": float(DEFAULT_PREVIOUS_MONTH_FLOOR_PCT),
            "active_store_count": len(cohort),
            "regionals": sorted({row["regional"] for row in cohort}),
        }

    async def calculate(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_month = payload["target_month"]
        source_months = source_month_configuration(target_month)
        latest_before_target = await self.repo.get_latest_sales_month(before_month=target_month)
        cohort_month = payload.get("cohort_month") or latest_before_target
        if not cohort_month:
            raise HTTPException(
                status_code=400,
                detail="Nu exista o luna cu vanzari anterioara lunii pentru care se calculeaza targetul.",
            )
        if cohort_month >= target_month:
            raise HTTPException(
                status_code=400,
                detail="Cohorta activa trebuie sa provina dintr-o luna anterioara lunii de target.",
            )

        cohort = await self.repo.get_active_cohort(cohort_month)
        if not cohort:
            raise HTTPException(status_code=400, detail="Luna de cohorta nu are magazine active.")

        total_target = money(payload["total_target"])
        min_floor = money(payload.get("min_floor", DEFAULT_MIN_FLOOR))
        floor_pct = Decimal(str(payload.get("previous_month_floor_pct", DEFAULT_PREVIOUS_MONTH_FLOOR_PCT)))
        if total_target <= 0 or min_floor < 0 or floor_pct < 0:
            raise HTTPException(status_code=400, detail="Parametrii de calcul nu sunt valizi.")

        months = [item["month"] for item in source_months]
        site_codes = [row["site_code"] for row in cohort]
        metrics = await self.repo.get_source_metrics(site_codes, months)
        async with self.repo.pool.acquire() as conn:
            forecast_factors = {
                month: Decimal(str(await get_forecast_factor(conn, month)))
                for month in months
            }
        metric_map: dict[tuple[str, str], SourceMetric] = {
            (row["site_code"], row["import_month"]): {
                "target": Decimal(row["target"] or 0),
                "actual_realized": money(Decimal(row["realized"] or 0)),
                "realized": realized_for_calculation(
                    Decimal(row["realized"] or 0),
                    forecast_factors[row["import_month"]],
                ),
                "forecast_factor": forecast_factors[row["import_month"]],
                "is_forecast": forecast_factors[row["import_month"]] > Decimal("1"),
            }
            for row in metrics
        }
        totals: dict[str, PeriodTotals] = {
            month: {
                "target": sum((metric_map[(site_code, month)]["target"] for site_code in site_codes), Decimal("0")),
                "realized": sum((metric_map[(site_code, month)]["realized"] for site_code in site_codes), Decimal("0")),
            }
            for month in months
        }

        warnings: list[str] = []
        for item in source_months:
            total = totals[item["month"]]
            if total["target"] == 0 and total["realized"] == 0:
                warnings.append(f"Nu exista date pentru perioada de referinta {item['month']}.")
            if forecast_factors[item["month"]] > Decimal("1"):
                warnings.append(
                    f"Perioada {item['month']} este partiala; vanzarile folosite in calcul sunt forecastate "
                    f"cu factor {forecast_factors[item['month']]:.4f}x pe baza importului disponibil."
                )

        calculated_rows: list[dict[str, Any]] = []
        floor_month = source_months[-1]["month"]
        for cohort_row in cohort:
            site_code = cohort_row["site_code"]
            period_weights: list[Decimal] = []
            history: list[dict[str, Any]] = []
            for item in source_months:
                metric = metric_map[(site_code, item["month"])]
                total = totals[item["month"]]
                shares: list[Decimal] = []
                if total["target"] > 0:
                    shares.append(metric["target"] / total["target"])
                if total["realized"] > 0:
                    shares.append(metric["realized"] / total["realized"])
                period_weight = sum(shares, Decimal("0")) / Decimal(len(shares)) if shares else Decimal("0")
                if shares:
                    period_weights.append(period_weight)
                attainment = (
                    metric["realized"] / metric["target"] * Decimal("100")
                    if metric["target"] > 0 else None
                )
                history.append({
                    "month": item["month"],
                    "label": item["label"],
                    "role": item["role"],
                    "target": float(money(metric["target"])),
                    "realized": float(money(metric["realized"])),
                    "actual_realized": float(money(metric["actual_realized"])),
                    "is_forecast": metric["is_forecast"],
                    "forecast_factor": float(metric["forecast_factor"]),
                    "attainment_pct": float(attainment.quantize(MONEY)) if attainment is not None else None,
                    "weight": float(period_weight),
                })
            average_weight = (
                sum(period_weights, Decimal("0")) / Decimal(len(period_weights))
                if period_weights else Decimal("0")
            )
            previous_target = metric_map[(site_code, floor_month)]["target"]
            floor_target = max(min_floor, money(previous_target * floor_pct))
            calculated_rows.append({
                "site_code": site_code,
                "locatie": cohort_row["locatie"],
                "firma": cohort_row["firma"],
                "regional": cohort_row["regional"],
                "asm": cohort_row["asm"],
                "calculated_weight": average_weight,
                "floor_target": floor_target,
                "proposed_target": Decimal("0"),
                "is_floor_limited": False,
                "history": history,
            })

        if sum((row["calculated_weight"] for row in calculated_rows), Decimal("0")) == 0:
            equal_weight = Decimal("1") / Decimal(len(calculated_rows))
            for row in calculated_rows:
                row["calculated_weight"] = equal_weight
            warnings.append("Datele istorice nu contin ponderi utilizabile; targetul a fost distribuit uniform.")

        calculated_rows, allocation_warnings = allocate_with_floors(calculated_rows, total_target)
        warnings.extend(allocation_warnings)
        scenario_id = await self.repo.save_draft_scenario(
            {
                "target_month": target_month,
                "cohort_month": cohort_month,
                "total_target": total_target,
                "min_floor": min_floor,
                "previous_month_floor_pct": floor_pct,
                "calculation_method": CALCULATION_METHOD,
                "source_months": source_months,
                "warnings": warnings,
            },
            calculated_rows,
        )
        if scenario_id is None:
            raise HTTPException(
                status_code=409,
                detail="Targetul acestei luni a fost deja finalizat si nu mai poate fi recalculat.",
            )
        return await self.get_scenario_detail(scenario_id)

    async def list_scenarios(self) -> list[dict[str, Any]]:
        rows = await self.repo.list_scenarios()
        return [self._serialize_header(dict(row)) for row in rows]

    async def get_scenario_detail(self, scenario_id: int) -> dict[str, Any]:
        scenario = await self.repo.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenariul de target nu exista.")
        rows = await self.repo.get_scenario_rows(scenario_id)
        header = self._serialize_header(dict(scenario))
        serialized_rows = [self._serialize_row(dict(row)) for row in rows]
        proposed_total = sum(row["proposed_target"] for row in serialized_rows)
        final_total = sum((row["final_target"] or 0) for row in serialized_rows)
        pending_final_count = sum(1 for row in serialized_rows if row["final_target"] is None)
        return {
            **header,
            "store_count": len(serialized_rows),
            "proposed_total": proposed_total,
            "final_total": final_total,
            "remaining_difference": header["total_target"] - final_total,
            "pending_final_count": pending_final_count,
            "floor_limited_count": sum(1 for row in serialized_rows if row["is_floor_limited"]),
            "manual_adjustments_count": sum(
                1 for row in serialized_rows
                if row["final_target"] is not None and abs(row["final_target"] - row["proposed_target"]) > 0.01
            ),
            "rows": serialized_rows,
            "regional_summary": self._regional_summary(serialized_rows),
            "source_summary": self._source_summary(serialized_rows),
        }

    async def save_final_targets(
        self,
        scenario_id: int,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if len({row["site_code"] for row in rows}) != len(rows):
            raise HTTPException(status_code=400, detail="Aceeasi locatie apare de mai multe ori in salvare.")
        updated = await self.repo.update_final_targets(scenario_id, rows)
        if updated != len(rows):
            scenario = await self.repo.get_scenario(scenario_id)
            if not scenario:
                raise HTTPException(status_code=404, detail="Scenariul de target nu exista.")
            if scenario["status"] != "draft":
                raise HTTPException(status_code=409, detail="Un scenariu finalizat nu mai poate fi editat.")
            raise HTTPException(status_code=400, detail="Una sau mai multe locatii nu apartin scenariului.")
        return await self.get_scenario_detail(scenario_id)

    async def finalize(self, scenario_id: int) -> dict[str, Any]:
        scenario = await self.get_scenario_detail(scenario_id)
        if scenario["calculation_method"] != CALCULATION_METHOD:
            raise HTTPException(
                status_code=409,
                detail="Scenariul a fost calculat cu o formula veche. Genereaza o propunere noua inainte de finalizare.",
            )
        if scenario["pending_final_count"] > 0:
            raise HTTPException(
                status_code=400,
                detail="Toate locatiile trebuie sa aiba target final completat inainte de finalizare.",
            )
        if money(scenario["final_total"]) != money(scenario["total_target"]):
            raise HTTPException(
                status_code=400,
                detail="Totalul targetelor finale trebuie sa fie egal cu bugetul scenariului inainte de finalizare.",
            )
        finalized = await self.repo.finalize_scenario(scenario_id)
        if not finalized:
            raise HTTPException(status_code=409, detail="Scenariul nu poate fi finalizat.")
        return await self.get_scenario_detail(scenario_id)

    async def export_excel(self, scenario_id: int) -> tuple[BytesIO, str]:
        scenario = await self.get_scenario_detail(scenario_id)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Targete finale"
        source_months = scenario["source_months"]
        forecast_by_month = {
            period["month"]: any(
                history["month"] == period["month"] and history.get("is_forecast", False)
                for row in scenario["rows"]
                for history in row["history"]
            )
            for period in source_months
        }
        headers = ["Firma", "Regional", "ASM", "Nume locatie", "Cod locatie"]
        for period in source_months:
            headers.extend([
                f"Target {period['month']}",
                f"{'Forecast folosit' if forecast_by_month[period['month']] else 'Realizat folosit'} {period['month']}",
                f"Realizat importat {period['month']}",
                f"% Realizare {period['month']}",
            ])
        headers.extend([
            "Floor", "Pondere calcul", "Target propus", "Target final",
            "Diferenta final-propus", "Ajustat manual", "Observatii",
        ])
        sheet.append(headers)
        history_by_month: dict[str, dict[str, Any]]
        for row in scenario["rows"]:
            history_by_month = {period["month"]: period for period in row["history"]}
            values: list[Any] = [
                row["firma"], row["regional"], row["asm"], row["locatie"], row["site_code"],
            ]
            for period in source_months:
                history = history_by_month[period["month"]]
                values.extend([
                    history["target"],
                    history["realized"],
                    history.get("actual_realized", history["realized"]),
                    history["attainment_pct"],
                ])
            values.extend([
                row["floor_target"], row["calculated_weight"], row["proposed_target"],
                row["final_target"],
                None if row["final_target"] is None else row["final_target"] - row["proposed_target"],
                "Necompletat" if row["final_target"] is None
                else "Da" if abs(row["final_target"] - row["proposed_target"]) > 0.01 else "Nu",
                row["note"] or "",
            ])
            sheet.append(values)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

        summary = workbook.create_sheet("Rezumat manageri")
        summary.append(["Regional", "Magazine", "Floor", "Target propus", "Target final", "Diferenta"])
        for row in scenario["regional_summary"]:
            summary.append([
                row["regional"], row["store_count"], row["floor_total"],
                row["proposed_total"], row["final_total"], row["final_total"] - row["proposed_total"],
            ])

        parameters = workbook.create_sheet("Parametri")
        parameters.append(["Parametru", "Valoare"])
        parameters.append(["Scenariu", scenario["id"]])
        parameters.append(["Status", scenario["status"]])
        parameters.append(["Luna target", scenario["target_month"]])
        parameters.append(["Luna cohorta magazine active", scenario["cohort_month"]])
        parameters.append(["Target total", scenario["total_target"]])
        parameters.append(["Prag minim absolut", scenario["min_floor"]])
        parameters.append(["Floor fata de luna precedenta", scenario["previous_month_floor_pct"]])
        parameters.append(["Metoda", scenario["calculation_method"]])
        for item in scenario["source_months"]:
            parameters.append([item["label"], item["month"]])
        for item in scenario["source_summary"]:
            if item["is_forecast"]:
                parameters.append([
                    f"Forecast {item['month']}",
                    f"{item['forecast_factor']:.4f}x; importat {item['actual_realized']:.2f}; folosit {item['realized']:.2f}",
                ])
        for warning in scenario["warnings"]:
            parameters.append(["Atentionare", warning])

        for worksheet in workbook.worksheets:
            header_fill = PatternFill("solid", fgColor="4F46E5")
            for cell in worksheet[1]:
                cell.font = Font(color="FFFFFF", bold=True)
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")
            for column in worksheet.columns:
                letter = get_column_letter(column[0].column)
                max_length = max(len(str(cell.value or "")) for cell in column)
                worksheet.column_dimensions[letter].width = min(max(max_length + 2, 12), 34)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        stamp = datetime.now().strftime("%Y%m%d")
        return output, f"targete_{scenario['target_month']}_scenariu_{scenario_id}_{stamp}.xlsx"

    async def get_store_detail(self, scenario_id: int, site_code: str) -> dict[str, Any]:
        data = await self.repo.get_store_detail(scenario_id, site_code)
        if not data:
            raise HTTPException(status_code=404, detail="Locatia nu exista in documentul de target.")

        scenario = dict(data["scenario"])
        history = [self._serialize_store_history(dict(row)) for row in data["history"]]
        agents = [self._serialize_store_agent(dict(row)) for row in data["agents"]]
        latest = next((row for row in reversed(history) if row["total_sales"] > 0 or row["target_value"] > 0), None)
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
            "final_target": float(scenario["final_target"]) if scenario["final_target"] is not None else None,
            "history": history,
            "latest": latest,
            "best_month": best_month,
            "avg_sales_16m": round(avg_sales, 2),
            "agents": agents,
        }

    def _serialize_header(self, row: dict[str, Any]) -> dict[str, Any]:
        for key in ("total_target", "min_floor", "previous_month_floor_pct", "proposed_total", "final_total"):
            if key in row:
                row[key] = float(row[key] or 0)
        for key in ("source_months", "warnings"):
            if key in row and isinstance(row[key], str):
                row[key] = json.loads(row[key])
        row.setdefault("source_months", [])
        row.setdefault("warnings", [])
        if "store_count" in row:
            row["store_count"] = int(row["store_count"])
        row["pending_final_count"] = int(row.get("pending_final_count") or 0)
        return row

    def _serialize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        for key in ("calculated_weight", "floor_target", "proposed_target"):
            row[key] = float(row[key] or 0)
        row["final_target"] = float(row["final_target"]) if row.get("final_target") is not None else None
        if isinstance(row.get("history"), str):
            row["history"] = json.loads(row["history"])
        return row

    def _regional_summary(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summary: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"store_count": 0, "floor_total": 0.0, "proposed_total": 0.0, "final_total": 0.0}
        )
        for row in rows:
            data = summary[row["regional"]]
            data["store_count"] += 1
            data["floor_total"] += row["floor_target"]
            data["proposed_total"] += row["proposed_target"]
            data["final_total"] += row["final_target"] or 0
        return [
            {"regional": regional, **values}
            for regional, values in sorted(summary.items())
        ]

    def _source_summary(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summary: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "target": 0.0,
                "realized": 0.0,
                "actual_realized": 0.0,
                "is_forecast": False,
                "forecast_factor": 1.0,
                "label": "",
            }
        )
        for row in rows:
            for period in row["history"]:
                values = summary[period["month"]]
                values["label"] = period["label"]
                values["target"] += period["target"]
                values["realized"] += period["realized"]
                values["actual_realized"] += period.get("actual_realized", period["realized"])
                if period.get("is_forecast", False):
                    values["is_forecast"] = True
                    values["forecast_factor"] = period.get("forecast_factor", 1.0)
        return [
            {
                "month": month,
                **values,
                "attainment_pct": values["realized"] / values["target"] * 100 if values["target"] else None,
            }
            for month, values in summary.items()
        ]

    def _serialize_store_history(self, row: dict[str, Any]) -> dict[str, Any]:
        total_sales = float(row["total_sales"] or 0)
        target = float(row["target_value"] or 0)
        total_quantity = int(row["total_quantity"] or 0)
        receipt_count = int(row["receipt_count"] or 0)
        receipt_2plus = int(row["receipt_2plus_count"] or 0)
        focus_quantity = int(row["focus_quantity"] or 0)
        return {
            "month": row["import_month"],
            "total_sales": total_sales,
            "target_value": target,
            "target_pct": total_sales / target * 100 if target else None,
            "total_quantity": total_quantity,
            "receipt_count": receipt_count,
            "cartele_qty": int(row["cartele_qty"] or 0),
            "avg_receipt": total_sales / receipt_count if receipt_count else None,
            "bon2acc_pct": receipt_2plus / receipt_count * 100 if receipt_count else None,
            "focus_pct": focus_quantity / total_quantity * 100 if total_quantity else None,
            "active_agents": int(row["active_agents"] or 0),
            "working_days": int(row["working_days"] or 0),
        }

    def _serialize_store_agent(self, row: dict[str, Any]) -> dict[str, Any]:
        total_sales = float(row["total_sales"] or 0)
        total_quantity = int(row["total_quantity"] or 0)
        receipt_count = int(row["receipt_count"] or 0)
        receipt_2plus = int(row["receipt_2plus_count"] or 0)
        focus_quantity = int(row["focus_quantity"] or 0)
        return {
            "agent": row["agent"],
            "total_sales": total_sales,
            "sales_share_pct": float(row["sales_share_pct"] or 0),
            "total_quantity": total_quantity,
            "receipt_count": receipt_count,
            "avg_receipt": total_sales / receipt_count if receipt_count else None,
            "bon2acc_pct": receipt_2plus / receipt_count * 100 if receipt_count else None,
            "focus_pct": focus_quantity / total_quantity * 100 if total_quantity else None,
            "active_months_16": int(row["active_months_16"] or 0),
            "sales_16m": float(row["sales_16m"] or 0),
        }
