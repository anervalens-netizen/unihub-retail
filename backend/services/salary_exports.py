"""Authoritative, durable XLSX rendering for sensitive salary exports."""

from __future__ import annotations

import json
from typing import Any

import asyncpg
from openpyxl import Workbook
from openpyxl.styles import Font
from pydantic import ValidationError

from business_clock import business_now
from repositories.salarii import SalariiRepository
from schemas.salarii import SalaryExportRequest
from services.export_xlsx_formatting import write_table_sheet
from services.exports.artifact import XlsxArtifact
from services.exports.table_renderer import XlsxRenderers
from services.exports.validation import ExportValidationError, validate_budget
from services.salarii import SalariiService
from services.spreadsheet_safety import append_openpyxl_row


MAX_SALARY_EXPORT_ROWS = 5_000

_KIND_TO_OPERATION = {
    "store_summary": "salary_store_summary",
    "monthly_trend": "salary_monthly_trend",
    "agents": "salary_agents",
}

_COLUMNS: dict[str, list[dict[str, str]]] = {
    "store_summary": [
        {"key": "site_code", "label": "Cod magazin", "type": "string"},
        {"key": "locatie", "label": "Locatie", "type": "string"},
        {"key": "company_name", "label": "Firma", "type": "string"},
        {"key": "agent_count", "label": "Agenti", "type": "integer"},
        {"key": "avg_agent_count", "label": "Agenti eligibili medie", "type": "integer"},
        {"key": "total_salary", "label": "Salarii", "type": "currency"},
        {"key": "avg_salary", "label": "Medie agent", "type": "currency"},
        {"key": "total_sales", "label": "Vanzari", "type": "currency"},
        {"key": "ratio", "label": "Salarii / vanzari %", "type": "percent"},
    ],
    "monthly_trend": [
        {"key": "month", "label": "Luna", "type": "string"},
        {"key": "agent_count", "label": "Agenti", "type": "integer"},
        {"key": "avg_agent_count", "label": "Agenti eligibili medie", "type": "integer"},
        {"key": "total_salary", "label": "Salarii", "type": "currency"},
        {"key": "avg_salary", "label": "Medie agent", "type": "currency"},
        {"key": "total_sales", "label": "Vanzari", "type": "currency"},
    ],
    "agents": [
        {"key": "full_name", "label": "Agent", "type": "string"},
        {"key": "company_name", "label": "Firma", "type": "string"},
        {"key": "locatie", "label": "Locatie", "type": "string"},
        {"key": "month_count", "label": "Luni", "type": "integer"},
        {"key": "avg_month_count", "label": "Luni eligibile medie", "type": "integer"},
        {"key": "avg_salary", "label": "Medie lunara", "type": "currency"},
        {"key": "total_salary", "label": "Total", "type": "currency"},
    ],
}


class SalaryExportsService:
    def __init__(self, pool: asyncpg.Pool):
        self.salary_service = SalariiService(SalariiRepository(pool))

    @staticmethod
    def validate_request(request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        try:
            validated = SalaryExportRequest.model_validate(request)
        except ValidationError as exc:
            raise ExportValidationError("Cererea exportului salarial este invalida.") from exc
        normalized = validated.model_dump(mode="json")
        return normalized, _KIND_TO_OPERATION[validated.export_kind]

    async def build_xlsx_artifact(self, request: dict[str, Any]) -> XlsxArtifact:
        normalized, _ = self.validate_request(request)
        export_kind = str(normalized["export_kind"])
        common = {
            "company_name": normalized["company_name"],
            "site_code": normalized["site_code"],
            "regional": normalized["regional"],
            "asm": normalized["asm"],
        }

        period: str | None = None
        if export_kind == "store_summary":
            result = await self.salary_service.get_summary(
                **common,
                year=normalized["year"],
                month=normalized["month"],
            )
            rows = list(result["items"])
            period = result["month"]
        elif export_kind == "monthly_trend":
            rows = await self.salary_service.get_trend(**common)
        else:
            result = await self.salary_service.get_agents_summary(
                q=normalized["q"],
                **common,
                year=normalized["year"],
                month=normalized["month"],
                limit=MAX_SALARY_EXPORT_ROWS + 1,
                offset=0,
            )
            rows = list(result["items"])
            if int(result["total"]) > MAX_SALARY_EXPORT_ROWS or len(rows) > MAX_SALARY_EXPORT_ROWS:
                raise ExportValidationError(
                    f"Exportul salarial depaseste limita de {MAX_SALARY_EXPORT_ROWS} randuri."
                )

        if len(rows) > MAX_SALARY_EXPORT_ROWS:
            raise ExportValidationError(
                f"Exportul salarial depaseste limita de {MAX_SALARY_EXPORT_ROWS} randuri."
            )

        columns = _COLUMNS[export_kind]
        validate_budget(
            len(rows),
            len(columns),
            operation="Exportul salarial",
            cells=(len(rows) + 1) * len(columns) + 10 * 2,
        )
        return self._render(
            normalized,
            export_kind=export_kind,
            rows=rows,
            columns=columns,
            period=period,
        )

    @staticmethod
    def _render(
        request: dict[str, Any],
        *,
        export_kind: str,
        rows: list[dict[str, Any]],
        columns: list[dict[str, str]],
        period: str | None,
    ) -> XlsxArtifact:
        workbook = Workbook()
        report = workbook.active
        report.title = "Raport salarii"
        write_table_sheet(report, columns, rows, header_fill="EEF2FF")

        config = workbook.create_sheet("Configuratie")
        config_rows: list[list[object]] = [
            ["Optiune", "Valoare"],
            ["Tip export", export_kind],
            ["Firma", request["company_name"] or "Toate"],
            ["Magazine", json.dumps(request["site_code"], ensure_ascii=False)],
            ["Manager", request["regional"] or "Toti"],
            ["ASM", request["asm"] or "Toti"],
            ["Perioada", period or (
                f"{request['year']}-{int(request['month']):02d}"
                if request["year"] is not None and request["month"] is not None
                else "Toate"
            )],
            ["Cautare agent", request["q"] or "Niciuna"],
            ["Generat", business_now().isoformat()],
            ["Randuri", len(rows)],
        ]
        for values in config_rows:
            append_openpyxl_row(config, values)
        for cell in config[1]:
            cell.font = Font(bold=True)
        config.column_dimensions["A"].width = 24
        config.column_dimensions["B"].width = 72

        suffix = period or business_now().strftime("%Y%m%d-%H%M%S")
        filename = f"salarii_{export_kind}_{suffix}.xlsx"
        cells = (len(rows) + 1) * len(columns) + len(config_rows) * 2
        return XlsxRenderers._spool_workbook(
            workbook,
            filename,
            cells=cells,
            row_count=len(rows),
        )
