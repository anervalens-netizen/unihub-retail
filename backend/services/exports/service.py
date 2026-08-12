from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Any

from repositories.exports import ExportsRepository
from services.campaigns import get_store_incentive_multipliers
from services.incentive_db import get_incentive_campaign
from services.export_process import (
    ExportRendererProcessError,
    RendererName,
    run_export_renderer_process,
)
from .artifact import XLSX_STREAM_CHUNK_BYTES, XlsxArtifact
from .artifact_builder import ExportArtifactBuilder
from .incentive_report import IncentiveReportBuilder
from . import incentive_report as incentive_report_module
from .catalog import (
    COMPARISON_LEVELS,
    DAILY_EVOLUTION_METRICS,
    DATASETS,
    DEFAULT_METRICS,
    DIMENSIONS,
    EVOLUTION_METRICS,
    METRICS,
)
from .metrics import (
    EXPORT_BUILD_SECONDS,
    EXPORT_CELLS,
    EXPORT_OUTPUT_BYTES,
    EXPORT_PEAK_RSS_BYTES,
    EXPORT_REJECTED_TOTAL,
)
from .loaders import CampaignLoaders
from .planner import ExportPlanner
from .report_builder import ReportBuilder
from . import report_builder as report_builder_module
from .table_renderer import XlsxRenderers
from .validation import (
    EXPORT_MAX_OUTPUT_BYTES,
    EXPORT_MAX_PEAK_RSS_BYTES,
    EXPORT_MAX_ROWS,
    ExportValidationError,
    preview_limit,
    selected_days as parse_selected_days,
    valid_keys,
)


EXPORT_COMPLEX_SEMAPHORE = asyncio.Semaphore(1)


class ExportsService(
    ReportBuilder,
    IncentiveReportBuilder,
    ExportArtifactBuilder,
    ExportPlanner,
    CampaignLoaders,
    XlsxRenderers,
):
    def __init__(self, repo: ExportsRepository):
        # Repository methods have explicit keyword-only signatures; the loader
        # mixin intentionally consumes the same boundary through dynamic calls.
        self.repo: Any = repo

    async def _build_report(
        self,
        request: dict[str, Any],
        *,
        row_limit: int,
        preview_limit: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        # Preserve the established test/operator override boundary while the
        # report implementation lives in its focused module.
        report_builder_module.EXPORT_MAX_ROWS = EXPORT_MAX_ROWS
        return await ReportBuilder._build_report(
            self,
            request,
            row_limit=row_limit,
            preview_limit=preview_limit,
        )

    def catalog(self) -> dict[str, Any]:
        return {
            "datasets": [
                {
                    "key": key,
                    "label": value["label"],
                    "description": value["description"],
                    "dimensions": [self._column_payload(DIMENSIONS[item]) for item in value["dimensions"]],
                }
                for key, value in DATASETS.items()
            ],
            "metrics": [self._column_payload(item) for item in METRICS.values()],
            "monthly_metrics": [self._column_payload(item) for item in EVOLUTION_METRICS.values()],
            "daily_metrics": [self._column_payload(item) for item in DAILY_EVOLUTION_METRICS.values()],
            "comparison_levels": [
                {"key": key, "label": value["label"]}
                for key, value in COMPARISON_LEVELS.items()
            ],
        }

    @staticmethod
    def is_complex_request(request: dict[str, Any]) -> bool:
        return request.get("export_mode") == "daily_comparison" or bool(request.get("daily_metrics"))

    def validate_complex_request(self, request: dict[str, Any]) -> str:
        """Validate the pure request envelope before durable reservation."""
        mode = str(request.get("export_mode") or "table")
        if mode == "daily_comparison":
            self._daily_comparison_params(request)
            return "daily_comparison"
        if mode != "table" or not request.get("daily_metrics"):
            raise ExportValidationError("Operatia durabila este rezervata exporturilor XLSX complexe.")
        dataset = str(request.get("dataset") or "")
        if dataset not in DATASETS or dataset == "incentive_products":
            raise ExportValidationError("Dataset invalid pentru evolutia zilnica.")
        months = sorted({str(item) for item in request.get("months", []) if item})
        if not months or len(months) > 3:
            raise ExportValidationError("Evolutia zilnica necesita intre 1 si 3 luni.")
        dimensions = valid_keys(
            request.get("dimensions"),
            set(DATASETS[dataset]["dimensions"]),
            list(DATASETS[dataset]["dimensions"]),
            "dimensiuni",
        )
        metrics = valid_keys(request.get("metrics"), set(METRICS), DEFAULT_METRICS, "metrici")
        monthly_metrics = valid_keys(
            request.get("monthly_metrics"), set(EVOLUTION_METRICS), [], "metrici lunare"
        )
        daily_metrics = valid_keys(
            request.get("daily_metrics"), set(DAILY_EVOLUTION_METRICS), [], "metrici zilnice"
        )
        if not daily_metrics or len(daily_metrics) * 31 * len(months) > 220:
            raise ExportValidationError("Selectia de metrici zilnice este prea ampla.")
        parse_selected_days(request)
        # Force evaluation of every selected key without retaining request data.
        if not dimensions or not metrics or len(monthly_metrics) > len(EVOLUTION_METRICS):
            raise ExportValidationError("Selectia exportului este invalida.")
        return "daily_metrics"

    async def preview(self, request: dict[str, Any]) -> dict[str, Any]:
        limit = preview_limit(request)
        if request.get("export_mode") == "daily_comparison":
            return await self._preview_daily_comparison(request, limit=limit)
        result, total_rows = await self._build_report(
            request,
            row_limit=limit + 1,
            preview_limit=limit,
        )
        return {
            "columns": result["columns"],
            "rows": result["rows"],
            "total_rows": total_rows,
            "truncated": total_rows > limit,
        }

    async def build_report(self, request: dict[str, Any]) -> dict[str, Any]:
        result, _ = await self._build_report(request, row_limit=EXPORT_MAX_ROWS + 1)
        return result

    async def _build_incentive_products_report(
        self,
        *,
        months: list[str],
        filters: dict[str, list[str]],
        include_closed_stores: bool,
        selected_days: list[int] | None,
        row_limit: int,
        preview_limit: int | None,
    ) -> tuple[dict[str, Any], int]:
        incentive_report_module.get_incentive_campaign = get_incentive_campaign
        incentive_report_module.get_store_incentive_multipliers = (
            get_store_incentive_multipliers
        )
        incentive_report_module.EXPORT_MAX_ROWS = EXPORT_MAX_ROWS
        return await IncentiveReportBuilder._build_incentive_products_report(
            self,
            months=months,
            filters=filters,
            include_closed_stores=include_closed_stores,
            selected_days=selected_days,
            row_limit=row_limit,
            preview_limit=preview_limit,
        )

    @staticmethod
    async def _complex_renderer_result(
        renderer_name: RendererName,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            if renderer_name not in {"daily_metrics", "daily_comparison"}:
                raise ValueError("Unknown complex export renderer")
            return await run_export_renderer_process(renderer_name, payload)
        except asyncio.CancelledError:
            raise
        except ExportRendererProcessError as exc:
            EXPORT_REJECTED_TOTAL.labels(exc.code).inc()
            messages = {
                "renderer_timeout": "Exportul complex a depasit timpul maxim permis.",
                "renderer_memory_limit": "Exportul complex a depasit limita de memorie RSS.",
            }
            message = messages.get(
                exc.code,
                "Exportul complex nu a putut fi finalizat in siguranta.",
            )
            raise ExportValidationError(message) from exc
        except (MemoryError, OSError, ValueError) as exc:
            EXPORT_REJECTED_TOTAL.labels("complex_worker").inc()
            raise ExportValidationError(
                "Exportul complex nu a putut fi finalizat in siguranta."
            ) from exc

    @staticmethod
    def _complex_artifact_paths(
        result: dict[str, Any],
    ) -> tuple[Path | None, Path | None]:
        raw_path = str(result.get("path") or "")
        raw_directory = str(result.get("operation_directory") or "")
        path = Path(raw_path) if raw_path else None
        operation_directory = Path(raw_directory).resolve() if raw_directory else None
        return path, operation_directory

    @staticmethod
    def _validate_complex_artifact_path(
        path: Path | None,
        operation_directory: Path | None,
    ) -> Path:
        invalid_path = (
            path is None
            or operation_directory is None
            or not operation_directory.name.startswith("unihub-export-operation-")
            or path.resolve().parent != operation_directory
        )
        if invalid_path:
            EXPORT_REJECTED_TOTAL.labels("complex_artifact_path").inc()
            raise ExportValidationError(
                "Calea artifactului exportului complex este invalida."
            )
        assert path is not None
        if not path.is_file():
            EXPORT_REJECTED_TOTAL.labels("complex_artifact").inc()
            raise ExportValidationError("Artifactul exportului complex lipseste.")
        return path

    @staticmethod
    def _complex_artifact_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(
                lambda: source.read(XLSX_STREAM_CHUNK_BYTES),
                b"",
            ):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _verify_complex_artifact(
        cls,
        result: dict[str, Any],
        path: Path,
    ) -> tuple[int, str, int]:
        size = path.stat().st_size
        expected_size = int(result.get("size") or -1)
        expected_hash = str(result.get("sha256") or "")
        valid_hash = len(expected_hash) == 64 and cls._complex_artifact_digest(path) == expected_hash
        if size != expected_size or not valid_hash:
            EXPORT_REJECTED_TOTAL.labels("complex_artifact_hash").inc()
            raise ExportValidationError(
                "Artifactul exportului complex nu a trecut verificarea de integritate."
            )
        if size > EXPORT_MAX_OUTPUT_BYTES:
            EXPORT_REJECTED_TOTAL.labels("output_bytes").inc()
            raise ExportValidationError(
                "Fisierul XLSX depaseste limita de dimensiune de output."
            )
        peak_rss = int(result.get("peak_rss") or 0)
        if peak_rss <= 0 or peak_rss > EXPORT_MAX_PEAK_RSS_BYTES:
            EXPORT_REJECTED_TOTAL.labels("peak_rss_bytes").inc()
            raise ExportValidationError("Exportul depaseste limita de memorie RSS.")
        return size, expected_hash, peak_rss

    @staticmethod
    def _record_complex_renderer_metrics(
        result: dict[str, Any],
        *,
        size: int,
        cells: int,
        peak_rss: int,
    ) -> None:
        EXPORT_BUILD_SECONDS.observe(float(result.get("build_seconds") or 0))
        EXPORT_OUTPUT_BYTES.set(size)
        EXPORT_CELLS.set(cells)
        EXPORT_PEAK_RSS_BYTES.set(peak_rss)

    def _adopt_complex_artifact(
        self,
        result: dict[str, Any],
        payload: dict[str, Any],
        path: Path,
        *,
        size: int,
        expected_hash: str,
        peak_rss: int,
        cells: int,
    ) -> XlsxArtifact:
        stream = path.open("r+b")
        try:
            return XlsxArtifact(
                stream=stream,
                filename=self._safe_filename(
                    str(result.get("filename") or payload["filename"])
                ),
                size=size,
                sha256=expected_hash,
                peak_rss_bytes=peak_rss,
                build_seconds=float(result.get("build_seconds") or 0),
                cell_count=cells,
            )
        except Exception:
            stream.close()
            raise

    @staticmethod
    def _cleanup_complex_artifact(
        path: Path | None,
        operation_directory: Path | None,
    ) -> None:
        if path is not None and path.is_file():
            path.unlink(missing_ok=True)
        if (
            operation_directory is not None
            and operation_directory.name.startswith("unihub-export-operation-")
        ):
            shutil.rmtree(operation_directory, ignore_errors=True)

    async def _run_complex_renderer(
        self,
        renderer_name: RendererName,
        payload: dict[str, Any],
        *,
        cells: int,
    ) -> XlsxArtifact:
        """Adopt only a complete, attested artifact from a killable child."""
        result = await self._complex_renderer_result(renderer_name, payload)
        path, operation_directory = self._complex_artifact_paths(result)
        try:
            artifact_path = self._validate_complex_artifact_path(
                path,
                operation_directory,
            )
            size, expected_hash, peak_rss = self._verify_complex_artifact(
                result,
                artifact_path,
            )
            self._record_complex_renderer_metrics(
                result,
                size=size,
                cells=cells,
                peak_rss=peak_rss,
            )
            return self._adopt_complex_artifact(
                result,
                payload,
                artifact_path,
                size=size,
                expected_hash=expected_hash,
                peak_rss=peak_rss,
                cells=cells,
            )
        finally:
            self._cleanup_complex_artifact(path, operation_directory)
