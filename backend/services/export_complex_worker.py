"""Process-isolated XLSX renderer for the complex daily comparison export."""

from __future__ import annotations

import os
import resource
import tempfile
import time
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from services.spreadsheet_safety import append_openpyxl_row


def _safe_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value).strip("._")
    if not safe:
        safe = "export_retail"
    if not safe.lower().endswith(".xlsx"):
        safe += ".xlsx"
    return safe[:140]


def _days_filename_suffix(selected_days: list[int] | None) -> str:
    if not selected_days:
        return ""
    value = (
        "-".join(str(day) for day in selected_days)
        if len(selected_days) <= 10
        else f"{len(selected_days)}selectate"
    )
    return f"_zile_{value}"


def _configure_day_axis(chart: LineChart) -> None:
    chart.x_axis.title = "Zi"
    chart.x_axis.delete = False
    chart.x_axis.axPos = "b"
    chart.x_axis.tickLblPos = "nextTo"
    chart.x_axis.tickLblSkip = 1
    chart.x_axis.tickMarkSkip = 1
    chart.x_axis.majorTickMark = "out"
    chart.x_axis.noMultiLvlLbl = True


def _write_table_sheet(
    ws: Any,
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
) -> None:
    append_openpyxl_row(ws, [column["label"] for column in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="1f2937")
        cell.fill = PatternFill("solid", fgColor="DCFCE7")
    for row in rows:
        append_openpyxl_row(ws, [row.get(column["key"]) for column in columns])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for index, column in enumerate(columns, start=1):
        letter = get_column_letter(index)
        ws.column_dimensions[letter].width = max(10, min(30, len(column["label"]) + 3))
        number_format = {"currency": "#,##0.00", "percent": "0.00", "integer": "0"}.get(column["type"])
        if number_format:
            for cell in ws[letter][1:]:
                cell.number_format = number_format


def _add_chart(
    ws: Any,
    *,
    months: list[str],
    metric_label: str,
    max_row: int,
    first_data_col: int,
) -> None:
    if not months or max_row < 2:
        return
    chart = LineChart()
    chart.title = f"Comparatie zilnica - {metric_label}"
    chart.y_axis.title = metric_label
    _configure_day_axis(chart)
    chart.visible_cells_only = True
    chart.style = 13
    data = Reference(
        ws,
        min_col=first_data_col,
        max_col=first_data_col + len(months) - 1,
        min_row=1,
        max_row=max_row,
    )
    categories = Reference(ws, min_col=first_data_col - 1, min_row=2, max_row=max_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)
    chart.height = 8
    chart.width = 20
    ws.add_chart(chart, f"{get_column_letter(first_data_col + len(months) + 3)}2")


def render_daily_comparison_xlsx(payload: dict[str, Any]) -> dict[str, Any]:
    """Render one complex workbook and return only a temporary path and budgets."""
    started_at = time.perf_counter()
    request = payload["request"]
    months: list[str] = payload["months"]
    metrics: list[str] = payload["metrics"]
    levels: list[str] = payload["levels"]
    level_config: dict[str, dict[str, Any]] = payload["level_config"]
    metric_labels: dict[str, str] = payload["metric_labels"]
    selected_days: list[int] | None = payload["selected_days"]
    tables: list[tuple[str, dict[str, Any]]] = payload["tables"]
    include_closed_stores = bool(payload["include_closed_stores"])

    workbook = Workbook()
    first_sheet = True
    total_rows = 0
    try:
        for level, table in tables:
            sheet_name = level_config[level]["sheet"]
            ws = workbook.active if first_sheet else workbook.create_sheet(sheet_name)
            ws.title = sheet_name
            first_sheet = False
            _write_table_sheet(ws, table["columns"], table["rows"])
            total_rows += len(table["rows"])
            _add_chart(
                ws,
                months=months,
                metric_label=metric_labels[metrics[0]],
                max_row=len(table["rows"]) + 1,
                first_data_col=len(level_config[level]["dimensions"]) + 2,
            )

        config = workbook.create_sheet("Configuratie")
        append_openpyxl_row(config, ["Optiune", "Valoare"])
        append_openpyxl_row(config, ["Tip export", "Evolutie zilnica comparativa"])
        append_openpyxl_row(config, ["Luni", ", ".join(months)])
        append_openpyxl_row(
            config,
            ["Zile", ", ".join(str(day) for day in selected_days) if selected_days else "Toata luna"],
        )
        append_openpyxl_row(config, ["Metrici zilnice", ", ".join(metric_labels[item] for item in metrics)])
        append_openpyxl_row(config, ["Niveluri", ", ".join(str(level_config[item]["label"]) for item in levels)])
        append_openpyxl_row(config, ["Include magazine inchise", "Da" if include_closed_stores else "Nu"])
        append_openpyxl_row(config, ["Generat", time.strftime("%Y-%m-%d %H:%M")])
        append_openpyxl_row(config, ["Randuri", total_rows])
        for cell in config[1]:
            cell.font = Font(bold=True)
        config.column_dimensions["A"].width = 28
        config.column_dimensions["B"].width = 72

        filename = request.get("filename") or (
            f"export_retail_evolutie_zilnica_{'_'.join(months)}"
            f"{_days_filename_suffix(selected_days)}.xlsx"
        )
        descriptor, path_value = tempfile.mkstemp(prefix="unihub-export-", suffix=".xlsx")
        os.close(descriptor)
        path = Path(path_value)
        workbook.save(path)
        size = path.stat().st_size
        return {
            "path": str(path),
            "filename": _safe_filename(str(filename)),
            "size": size,
            "peak_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "build_seconds": time.perf_counter() - started_at,
        }
    except Exception:
        if "path" in locals() and path.exists():
            path.unlink()
        raise
    finally:
        workbook.close()
