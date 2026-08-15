from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

from .artifact import XlsxArtifact
from .daily_comparison import comparison_level_config, metric_labels
from .validation import (
    EXPORT_MAX_OUTPUT_BYTES,
    EXPORT_MAX_PEAK_RSS_BYTES,
    EXPORT_MAX_ROWS,
    ExportValidationError,
)


EXPORT_COMPLEX_SEMAPHORE = asyncio.Semaphore(1)


class ExportArtifactBuilder:
    if TYPE_CHECKING:
        repo: Any
        build_report: Any
        _selected_days: Any
        _normalize_filters: Any
        _render_simple_table_xlsx: Any
        _days_filename_suffix: Any
        _safe_filename: Any
        _run_complex_renderer: Any
        _daily_comparison_params: Any
        _daily_comparison_table: Any
        _validate_export_budget: Any

    async def build_xlsx(self, request: dict[str, Any]) -> tuple[bytes, str]:
        """Compatibility helper for in-process callers and focused tests."""
        artifact = await self.build_xlsx_artifact(request)
        try:
            artifact.stream.seek(0)
            return artifact.stream.read(), artifact.filename
        finally:
            artifact.close()

    async def build_xlsx_artifact(self, request: dict[str, Any]) -> XlsxArtifact:
        """Build an XLSX into a bounded spool for chunked HTTP delivery."""
        if request.get("export_mode") == "daily_comparison":
            return await self._build_daily_comparison_xlsx(request)

        result = await self.build_report(request)
        selected_days = self._selected_days(request)
        daily_rows: list[Any] | None = None
        if request.get("daily_metrics"):
            filters = self._normalize_filters(request.get("filters") or {})
            daily_rows = await self.repo.fetch_daily_evolution_rows(
                months=request["months"],
                filters=filters,
                include_closed_stores=bool(request.get("include_closed_stores", False)),
                campaign_codes_by_month={},
                campaign_exclusions_by_month={},
                selected_days=selected_days,
                include_campaign_metrics=False,
                limit=EXPORT_MAX_ROWS + 1,
            )
            if len(daily_rows) > EXPORT_MAX_ROWS:
                raise ExportValidationError("Exportul depaseste limita de randuri pentru evolutia zilnica.")
        if daily_rows is not None:
            return await self._build_daily_metrics_xlsx(
                request=request,
                result=result,
                selected_days=selected_days,
                daily_rows=daily_rows,
            )
        return await asyncio.to_thread(self._render_simple_table_xlsx, request, result, selected_days, None)

    async def _build_daily_metrics_xlsx(
        self,
        *,
        request: dict[str, Any],
        result: dict[str, Any],
        selected_days: list[int] | None,
        daily_rows: list[Any],
    ) -> XlsxArtifact:
        """Run every charted daily sheet out-of-process with one global slot."""
        filename = request.get("filename") or (
            f"export_retail_{request['dataset']}_{'_'.join(request['months'])}"
            f"{self._days_filename_suffix(selected_days)}.xlsx"
        )
        payload = {
            "request": request,
            "result": result,
            "selected_days": selected_days,
            # asyncpg Records are not a process contract; serialize plain data.
            "daily_rows": [dict(row) for row in daily_rows],
            "filename": self._safe_filename(str(filename)),
            "max_output_bytes": EXPORT_MAX_OUTPUT_BYTES,
            "max_peak_rss_bytes": EXPORT_MAX_PEAK_RSS_BYTES,
        }
        cells = (len(result["rows"]) + 1) * len(result["columns"])
        async with EXPORT_COMPLEX_SEMAPHORE:
            return await self._run_complex_renderer("daily_metrics", payload, cells=cells)

    async def _preview_daily_comparison(
        self,
        request: dict[str, Any],
        *,
        limit: int,
    ) -> dict[str, Any]:
        months, metrics, levels, filters, include_closed_stores, selected_days = self._daily_comparison_params(request)
        campaign_codes_by_month: dict[str, list[str]] = {}
        preview_level = "general" if "general" in levels else levels[0]
        records = await self.repo.fetch_daily_comparison_rows(
            level=preview_level,
            months=months,
            filters=filters,
            include_closed_stores=include_closed_stores,
            campaign_codes_by_month=campaign_codes_by_month,
            selected_days=selected_days,
            limit=limit + 1,
        )
        records = records[: limit + 1]
        table = self._daily_comparison_table(
            level=preview_level,
            months=months,
            metrics=metrics,
            records=records,
            selected_days=selected_days,
            row_limit=limit,
        )
        total_rows = int(table.get("total_rows", len(table["rows"])))
        return {
            "columns": table["columns"],
            "rows": table["rows"][:limit],
            "total_rows": total_rows,
            "truncated": total_rows > limit,
        }

    async def _build_daily_comparison_xlsx(self, request: dict[str, Any]) -> XlsxArtifact:
        """Serialize the complex writer so concurrent exports cannot starve web DB work."""
        async with EXPORT_COMPLEX_SEMAPHORE:
            return await self._build_daily_comparison_xlsx_unlocked(request)

    async def _build_daily_comparison_xlsx_unlocked(self, request: dict[str, Any]) -> XlsxArtifact:
        months, metrics, levels, filters, include_closed_stores, selected_days = self._daily_comparison_params(request)
        campaign_codes_by_month: dict[str, list[str]] = {}
        semaphore = asyncio.Semaphore(2)

        async def load_level(level: str) -> tuple[str, list[Any]]:
            async with semaphore:
                records = await self.repo.fetch_daily_comparison_rows(
                    level=level,
                    months=months,
                    filters=filters,
                    include_closed_stores=include_closed_stores,
                    campaign_codes_by_month=campaign_codes_by_month,
                    selected_days=selected_days,
                    limit=EXPORT_MAX_ROWS + 1,
                )
                if len(records) > EXPORT_MAX_ROWS:
                    raise ExportValidationError(
                        f"Comparatia depaseste limita de randuri pentru nivelul {level}."
                    )
                return level, records

        level_records = await asyncio.gather(*(load_level(level) for level in levels))
        tables: list[tuple[str, dict[str, Any]]] = []
        for level, records in level_records:
            table = await asyncio.to_thread(
                self._daily_comparison_table,
                level=level,
                months=months,
                metrics=metrics,
                records=records,
                selected_days=selected_days,
            )
            tables.append((level, table))
        self._validate_export_budget(
            sum(int(table.get("total_rows", len(table["rows"]))) for _, table in tables),
            max((len(table["columns"]) for _, table in tables), default=0),
            operation="Comparatia zilnica",
            cells=sum(
                int(table.get("total_rows", len(table["rows"]))) * len(table["columns"])
                for _, table in tables
            ),
        )
        payload = {
            "request": request,
            "months": months,
            "metrics": metrics,
            "levels": levels,
            "include_closed_stores": include_closed_stores,
            "selected_days": selected_days,
            "tables": tables,
            "level_config": comparison_level_config(levels),
            "metric_labels": metric_labels(metrics),
            "max_output_bytes": EXPORT_MAX_OUTPUT_BYTES,
            "max_peak_rss_bytes": EXPORT_MAX_PEAK_RSS_BYTES,
            "filename": self._safe_filename(str(request.get("filename") or (
                f"export_retail_evolutie_zilnica_{'_'.join(months)}"
                f"{self._days_filename_suffix(selected_days)}.xlsx"
            ))),
        }
        return await self._run_complex_renderer(
            "daily_comparison",
            payload,
            cells=sum(len(table[1]["rows"]) * len(table[1]["columns"]) for table in tables),
        )
