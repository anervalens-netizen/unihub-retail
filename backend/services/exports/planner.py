"""Planning helpers kept free of openpyxl and repository imports."""
from decimal import Decimal
from typing import Any

from .calculations import pct, ratio
from .catalog import COMPARISON_LEVELS, DAILY_EVOLUTION_METRICS, DIMENSIONS, EVOLUTION_METRICS, METRICS, ColumnDef
from .validation import (
    ExportValidationError,
    max_days_for_months,
    normalize_filters,
    preview_limit,
    selected_days,
    valid_keys,
    validate_budget,
)


class ExportPlanner:
    """Pure export request, table and daily-comparison planning."""

    def _base_row(self, record: Any, dimensions: list[str], metrics: list[str]) -> dict[str, Any]:
        row = {dimension: record[dimension] for dimension in dimensions}
        computed = self._compute_metrics(record)
        for metric in metrics:
            row[metric] = computed.get(metric)
        return row

    def _attach_period_metrics(
        self,
        rows_by_key: dict[tuple[Any, ...], dict[str, Any]],
        records: list[Any],
        dataset: str,
        metrics: list[str],
        *,
        period_prefix: str,
    ) -> None:
        for record in records:
            row = rows_by_key.get(self._row_key(record, dataset))
            if row is None:
                continue
            period_key = str(record["period_key"])
            computed = self._compute_metrics(record)
            for metric in metrics:
                row[f"{period_prefix}:{period_key}:{metric}"] = computed.get(metric)

    def _build_columns(
        self,
        dataset: str,
        dimensions: list[str],
        metrics: list[str],
        months: list[str],
        monthly_metrics: list[str],
        rows_by_key: dict[tuple[Any, ...], dict[str, Any]],
        daily_metrics: list[str],
    ) -> list[dict[str, str]]:
        columns: list[dict[str, str]] = []
        for key in dimensions:
            columns.append(self._column_payload(DIMENSIONS[key]))
        for key in metrics:
            columns.append(self._column_payload(METRICS[key]))
        for month in months:
            for metric in monthly_metrics:
                definition = EVOLUTION_METRICS[metric]
                columns.append({
                    "key": f"month:{month}:{metric}",
                    "label": f"{month} {definition.label}",
                    "type": definition.type,
                    "group": "Evolutie lunara",
                })
        day_keys = sorted({
            key.split(":")[1]
            for row in rows_by_key.values()
            for key in row
            if key.startswith("day:")
        })
        for day in day_keys:
            for metric in daily_metrics:
                definition = DAILY_EVOLUTION_METRICS[metric]
                columns.append({
                    "key": f"day:{day}:{metric}",
                    "label": f"{day} {definition.label}",
                    "type": definition.type,
                    "group": "Evolutie zilnica",
                })
        return columns

    def _compute_metrics(self, row: Any) -> dict[str, Any]:
        total_sales = Decimal(row["total_sales"] or 0)
        total_quantity = int(row["total_quantity"] or 0)
        total_receipts = int(row["total_receipts"] or 0)
        receipt_2plus_count = int(row["receipt_2plus_count"] or 0)
        focus_quantity = int(row["focus_quantity"] or 0)
        target = Decimal(row["target"] or 0)
        working_days = int(row["working_days"] or 0)
        return {
            "total_sales": total_sales,
            "total_quantity": total_quantity,
            "total_receipts": total_receipts,
            "avg_receipt_value": ratio(total_sales, total_receipts),
            "proc_bon2acc": pct(Decimal(receipt_2plus_count), Decimal(total_receipts)),
            "prc_focus_acc_qty": pct(Decimal(focus_quantity), Decimal(total_quantity)),
            "target": target,
            "target_progress_pct": pct(total_sales, target),
            "working_days": working_days,
            "daily_average": ratio(total_sales, working_days),
            "store_count": int(row["store_count"] or 0),
            "agent_count": int(row["agent_count"] or 0),
            "incentive_sales": Decimal(row["incentive_sales"] or 0),
            "incentive_quantity": int(row["incentive_quantity"] or 0),
            "incentive_bonus": Decimal(row["incentive_bonus"] or 0),
            "promo_sales": Decimal(row["promo_sales"] or 0),
            "promo_quantity": int(row["promo_quantity"] or 0),
        }

    def _row_key(self, row: Any, dataset: str) -> tuple[Any, ...]:
        key_fields = {
            "agents": ["agent", "site_code"],
            "stores": ["site_code"],
            "regionals": ["regional"],
            "asms": ["regional", "asm"],
        }[dataset]
        return tuple(row[field] for field in key_fields)

    _preview_limit = staticmethod(preview_limit)

    @staticmethod
    def _record_total_count(records: list[Any]) -> int | None:
        if not records:
            return None
        try:
            value = records[0]["total_count"]
        except (KeyError, IndexError, TypeError):
            return None
        try:
            return max(0, int(value)) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _record_total_dimensions(records: list[Any]) -> int | None:
        if not records:
            return None
        try:
            value = records[0]["total_dimensions"]
        except (KeyError, IndexError, TypeError):
            return None
        try:
            return max(0, int(value)) if value is not None else None
        except (TypeError, ValueError):
            return None

    _validate_export_budget = staticmethod(validate_budget)

    def _public_row(self, row: dict[str, Any], columns: list[dict[str, str]]) -> dict[str, Any]:
        return {column["key"]: self._json_value(row.get(column["key"])) for column in columns}

    def _daily_comparison_params(
        self,
        request: dict[str, Any],
    ) -> tuple[list[str], list[str], list[str], dict[str, list[str]], bool, list[int] | None]:
        months = sorted({str(item) for item in request.get("months", []) if item})
        if not months:
            raise ExportValidationError("Selecteaza cel putin o luna.")
        if len(months) > 6:
            raise ExportValidationError("Comparatia zilnica este limitata la maxim 6 luni.")

        metrics = self._valid_keys(
            request.get("daily_metrics"),
            set(DAILY_EVOLUTION_METRICS),
            ["total_sales"],
            "metrici zilnice",
        )
        if len(metrics) > 4:
            raise ExportValidationError("Comparatia zilnica poate contine maxim 4 metrici.")

        levels = self._valid_keys(
            request.get("comparison_levels"),
            set(COMPARISON_LEVELS),
            ["general", "asms", "stores", "agents"],
            "niveluri de comparatie",
        )
        filters = self._normalize_filters(request.get("filters") or {})
        include_closed_stores = bool(request.get("include_closed_stores", False))
        return months, metrics, levels, filters, include_closed_stores, self._selected_days(request)

    def _daily_comparison_table(
        self,
        *,
        level: str,
        months: list[str],
        metrics: list[str],
        records: list[Any],
        selected_days: list[int] | None = None,
        row_limit: int | None = None,
    ) -> dict[str, Any]:
        dimensions = list(COMPARISON_LEVELS[level]["dimensions"])
        columns: list[dict[str, str]] = [
            self._column_payload(DIMENSIONS[dimension]) for dimension in dimensions
        ]
        columns.append({"key": "day_of_month", "label": "Zi", "type": "integer", "group": "Perioada"})

        for metric in metrics:
            definition = DAILY_EVOLUTION_METRICS[metric]
            for month in months:
                columns.append({
                    "key": f"{month}:{metric}",
                    "label": f"{month} {definition.label}",
                    "type": definition.type,
                    "group": "Evolutie zilnica",
                })
            if len(months) == 2:
                if definition.type == "percent":
                    columns.append({
                        "key": f"delta_pp:{metric}",
                        "label": f"Delta pp {months[1]} vs {months[0]} {definition.label}",
                        "type": "percent",
                        "group": "Comparatie",
                    })
                else:
                    columns.append({
                        "key": f"delta:{metric}",
                        "label": f"Delta {months[1]} vs {months[0]} {definition.label}",
                        "type": definition.type,
                        "group": "Comparatie",
                    })
                    columns.append({
                        "key": f"delta_pct:{metric}",
                        "label": f"Delta % {months[1]} vs {months[0]} {definition.label}",
                        "type": "percent",
                        "group": "Comparatie",
                    })

        values: dict[tuple[tuple[Any, ...], int, str], dict[str, Any]] = {}
        dimension_labels: dict[tuple[Any, ...], dict[str, Any]] = {}
        for record in records:
            dim_key = tuple(record[dimension] for dimension in dimensions)
            dimension_labels[dim_key] = {dimension: record[dimension] for dimension in dimensions}
            day = int(record["day_of_month"] or 0)
            if day <= 0:
                continue
            values[(dim_key, day, str(record["import_month"]))] = self._compute_metrics(record)

        if level == "general" and not dimension_labels:
            dimension_labels[()] = {}
        max_day = self._max_days_for_months(months)
        days = selected_days or list(range(1, max_day + 1))
        total_dimensions = self._record_total_dimensions(records)
        if total_dimensions is None:
            total_dimensions = max(1, len(dimension_labels)) if level == "general" else len(dimension_labels)
        elif level == "general":
            total_dimensions = max(1, total_dimensions)
        total_rows = total_dimensions * len(days)
        self._validate_export_budget(
            min(total_rows, row_limit) if row_limit is not None else total_rows,
            len(columns),
            operation="Preview-ul comparatiei" if row_limit is not None else "Comparatia zilnica",
        )
        rows: list[dict[str, Any]] = []

        for dim_key in sorted(dimension_labels, key=lambda item: tuple(str(value or "") for value in item)):
            dim_values = dimension_labels[dim_key]
            for day in days:
                row: dict[str, Any] = {dimension: dim_values.get(dimension) for dimension in dimensions}
                row["day_of_month"] = day
                for metric in metrics:
                    month_values: list[Any] = []
                    for month in months:
                        value = values.get((dim_key, day, month), {}).get(metric)
                        month_values.append(value)
                        row[f"{month}:{metric}"] = self._json_value(value)
                    if len(months) == 2:
                        left, right = month_values
                        if left is not None and right is not None:
                            delta = Decimal(str(right)) - Decimal(str(left))
                            if DAILY_EVOLUTION_METRICS[metric].type == "percent":
                                row[f"delta_pp:{metric}"] = self._json_value(delta)
                            else:
                                row[f"delta:{metric}"] = self._json_value(delta)
                                row[f"delta_pct:{metric}"] = self._json_value(
                                    pct(delta, Decimal(str(left))) if Decimal(str(left)) != 0 else None
                                )
                        else:
                            if DAILY_EVOLUTION_METRICS[metric].type == "percent":
                                row[f"delta_pp:{metric}"] = None
                            else:
                                row[f"delta:{metric}"] = None
                                row[f"delta_pct:{metric}"] = None
                rows.append(row)
                if row_limit is not None and len(rows) >= row_limit:
                    break
            if row_limit is not None and len(rows) >= row_limit:
                break

        return {
            "columns": columns,
            "rows": [self._public_row(row, columns) for row in rows],
            "max_day": max_day,
            "total_rows": total_rows,
        }

    _selected_days = staticmethod(selected_days)

    def _days_filename_suffix(self, selected_days: list[int] | None) -> str:
        if not selected_days:
            return ""
        value = "-".join(str(day) for day in selected_days) if len(selected_days) <= 10 else f"{len(selected_days)}selectate"
        return f"_zile_{value}"

    _max_days_for_months = staticmethod(max_days_for_months)

    _normalize_filters = staticmethod(normalize_filters)

    _valid_keys = staticmethod(valid_keys)

    def _column_payload(self, definition: ColumnDef) -> dict[str, str]:
        return {
            "key": definition.key,
            "label": definition.label,
            "type": definition.type,
            "group": definition.group,
        }

    def _json_value(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        return value
