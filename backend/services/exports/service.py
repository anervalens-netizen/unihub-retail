from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, IO

from repositories.exports import ExportsRepository
from services.campaigns import get_store_incentive_multipliers
from services.incentive_db import get_incentive_campaign
from services.promotion_evaluation import (
    PromotionEvaluationStatus,
    scope_promotion_definition_to_interval,
)
from services.dashboard_specials import (
    load_promotion_rule_products,
    load_special_cards_config,
    parse_promotion_definitions,
)
from services.export_process import (
    ExportRendererProcessError,
    RendererName,
    run_export_renderer_process,
)
from .artifact import XLSX_STREAM_CHUNK_BYTES, XlsxArtifact
from .catalog import (
    CAMPAIGN_METRICS,
    COMPARISON_LEVELS,
    DAILY_EVOLUTION_METRICS,
    DATASETS,
    DEFAULT_METRICS,
    DIMENSIONS,
    EVOLUTION_METRICS,
    METRICS,
    ColumnDef,
)
from .calculations import pct, ratio
from .daily_comparison import comparison_level_config, metric_labels
from .metrics import (
    EXPORT_BUILD_SECONDS,
    EXPORT_CELLS,
    EXPORT_OUTPUT_BYTES,
    EXPORT_PEAK_RSS_BYTES,
    EXPORT_REJECTED_TOTAL,
)
from .loaders import CampaignLoaders
from .planner import ExportPlanner
from .table_renderer import XlsxRenderers
from .validation import (
    EXPORT_ESTIMATED_BYTES_PER_CELL,
    EXPORT_MAX_CELLS,
    EXPORT_MAX_OUTPUT_BYTES,
    EXPORT_MAX_PEAK_RSS_BYTES,
    EXPORT_MAX_PREVIEW_ROWS,
    EXPORT_MAX_ROWS,
    ExportValidationError,
    max_days_for_months,
    normalize_filters,
    preview_limit,
    selected_days as parse_selected_days,
    valid_keys,
    validate_budget,
)


EXPORT_COMPLEX_SEMAPHORE = asyncio.Semaphore(1)

class ExportsService(ExportPlanner, CampaignLoaders, XlsxRenderers):
    def __init__(self, repo: ExportsRepository):
        # Repository methods have explicit keyword-only signatures; the loader
        # mixin intentionally consumes the same boundary through dynamic calls.
        self.repo: Any = repo

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

    async def _build_report(
        self,
        request: dict[str, Any],
        *,
        row_limit: int,
        preview_limit: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        dataset = str(request.get("dataset") or "")
        if dataset not in DATASETS:
            raise ExportValidationError("Dataset invalid.")
        months = sorted({str(item) for item in request.get("months", []) if item})
        if not months:
            raise ExportValidationError("Selecteaza cel putin o luna.")
        if len(months) > 144:
            raise ExportValidationError("Selectia poate contine maxim 144 luni.")
        selected_days = selected_days_for_request = parse_selected_days(request)
        include_closed_stores = bool(request.get("include_closed_stores", False))

        if dataset == "incentive_products":
            incentive_result = await self._build_incentive_products_report(
                months=months,
                filters=normalize_filters(request.get("filters") or {}),
                include_closed_stores=include_closed_stores,
                selected_days=selected_days,
                row_limit=row_limit,
                preview_limit=preview_limit,
            )
            return incentive_result

        dimensions = valid_keys(
            request.get("dimensions"),
            set(DATASETS[dataset]["dimensions"]),
            list(DATASETS[dataset]["dimensions"]),
            "dimensiuni",
        )
        metrics = valid_keys(
            request.get("metrics"),
            set(METRICS),
            DEFAULT_METRICS,
            "metrici",
        )
        monthly_metrics = valid_keys(
            request.get("monthly_metrics"),
            set(EVOLUTION_METRICS),
            [],
            "metrici lunare",
        )
        daily_metrics = valid_keys(
            request.get("daily_metrics"),
            set(DAILY_EVOLUTION_METRICS),
            [],
            "metrici zilnice",
        )
        if daily_metrics and len(months) > 3:
            raise ExportValidationError("Evolutia zilnica este limitata la maxim 3 luni selectate.")
        if daily_metrics and len(daily_metrics) * 31 * len(months) > 220:
            raise ExportValidationError("Prea multe coloane zilnice. Redu lunile sau metricile zilnice.")

        filters = normalize_filters(request.get("filters") or {})
        total_has_campaign_metrics = bool(CAMPAIGN_METRICS.intersection(metrics))
        monthly_has_campaign_metrics = bool(CAMPAIGN_METRICS.intersection(monthly_metrics))
        needs_campaign_data = total_has_campaign_metrics or monthly_has_campaign_metrics
        campaign_codes_by_month = self._campaign_codes_by_month(months) if needs_campaign_data else {}
        campaign_exclusions_by_month = (
            await self._campaign_exclusions_by_month(months, filters, selected_days)
            if needs_campaign_data
            else {}
        )

        total_records = await self.repo.fetch_report_rows(
            dataset=dataset,
            months=months,
            filters=filters,
            include_closed_stores=include_closed_stores,
            campaign_codes_by_month=campaign_codes_by_month,
            campaign_exclusions_by_month=campaign_exclusions_by_month,
            selected_days=selected_days,
            include_campaign_metrics=total_has_campaign_metrics,
            limit=row_limit,
            include_total_count=preview_limit is not None,
        )
        if preview_limit is None and len(total_records) > EXPORT_MAX_ROWS:
            raise ExportValidationError("Exportul depaseste limita de randuri.")
        visible_records = total_records[:preview_limit] if preview_limit is not None else total_records
        rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        for record in visible_records:
            row = self._base_row(record, dimensions, metrics)
            rows_by_key[self._row_key(record, dataset)] = row

        max_days = len(selected_days_for_request) if selected_days_for_request else max_days_for_months(months)
        max_columns = (
            len(dimensions)
            + len(metrics)
            + len(months) * len(monthly_metrics)
            + max_days * len(daily_metrics)
        )
        validate_budget(
            len(rows_by_key),
            max_columns,
            operation="Raportul",
        )

        period_loaders: dict[str, Any] = {}
        period_limit = min(
            EXPORT_MAX_ROWS + 1,
            max(
                1,
                (preview_limit or EXPORT_MAX_ROWS)
                * max(1, len(months) * max(1, len(monthly_metrics) + len(daily_metrics))),
            )
            + 1,
        )
        if monthly_metrics:
            period_loaders["month"] = self.repo.fetch_report_rows(
                dataset=dataset,
                months=months,
                filters=filters,
                include_closed_stores=include_closed_stores,
                campaign_codes_by_month=campaign_codes_by_month,
                campaign_exclusions_by_month=campaign_exclusions_by_month,
                selected_days=selected_days,
                period="month",
                include_campaign_metrics=monthly_has_campaign_metrics,
                limit=period_limit,
            )
        if daily_metrics:
            period_loaders["day"] = self.repo.fetch_report_rows(
                dataset=dataset,
                months=months,
                filters=filters,
                include_closed_stores=include_closed_stores,
                campaign_codes_by_month=campaign_codes_by_month,
                campaign_exclusions_by_month=campaign_exclusions_by_month,
                selected_days=selected_days,
                period="day",
                include_campaign_metrics=False,
                limit=period_limit,
            )

        period_records: dict[str, list[Any]] = {}
        if period_loaders:
            names = tuple(period_loaders)
            tasks = {
                name: asyncio.create_task(period_loaders[name], name=f"export:{name}")
                for name in names
            }
            try:
                results = await asyncio.gather(*(tasks[name] for name in names))
            except BaseException:
                for task in tasks.values():
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks.values(), return_exceptions=True)
                raise
            period_records = dict(zip(names, results, strict=True))

        for name, records in period_records.items():
            if preview_limit is None and len(records) > EXPORT_MAX_ROWS:
                raise ExportValidationError(
                    f"Exportul depaseste limita de randuri pentru evolutia {name}."
                )
            if preview_limit is not None:
                period_records[name] = records[:period_limit]

        if monthly_metrics:
            self._attach_period_metrics(
                rows_by_key,
                period_records["month"],
                dataset,
                monthly_metrics,
                period_prefix="month",
            )

        if daily_metrics:
            self._attach_period_metrics(
                rows_by_key,
                period_records["day"],
                dataset,
                daily_metrics,
                period_prefix="day",
            )

        columns = self._build_columns(dataset, dimensions, metrics, months, monthly_metrics, rows_by_key, daily_metrics)
        rows = list(rows_by_key.values())
        rows.sort(key=lambda row: tuple(str(row.get(dim) or "") for dim in dimensions))
        validate_budget(len(rows), len(columns), operation="Raportul")
        standard_result = {
            "columns": columns,
            "rows": [self._public_row(row, columns) for row in rows[:preview_limit] if preview_limit is not None]
            if preview_limit is not None
            else [self._public_row(row, columns) for row in rows],
        }
        if preview_limit is None:
            return standard_result, len(rows)
        total_count = self._record_total_count(total_records)
        return standard_result, total_count if total_count is not None else max(len(total_records), len(rows))

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
        columns = [
            {"key": "month", "label": "Luna", "type": "text", "group": "Perioada"},
            {"key": "category", "label": "Categorie", "type": "text", "group": "Produs"},
            {"key": "subcategory", "label": "Subcategorie", "type": "text", "group": "Produs"},
            {"key": "item_code", "label": "Cod produs", "type": "text", "group": "Produs"},
            {"key": "item_name", "label": "Produs", "type": "text", "group": "Produs"},
            {"key": "reward_value", "label": "Reward/unitate RON", "type": "currency", "group": "Incentive"},
            {"key": "positive_quantity", "label": "Vandute pozitive", "type": "integer", "group": "Vanzari"},
            {"key": "return_quantity", "label": "Retururi", "type": "integer", "group": "Vanzari"},
            {"key": "net_quantity", "label": "Vandute net", "type": "integer", "group": "Vanzari"},
            {"key": "promo_excluded_quantity", "label": "Excluse promo", "type": "integer", "group": "Incentive"},
            {"key": "eligible_quantity", "label": "Eligibile dupa promo", "type": "integer", "group": "Incentive"},
            {"key": "paid_quantity", "label": "Buc. platite >0", "type": "integer", "group": "Plata"},
            {"key": "paid_full_quantity", "label": "Buc. platite 100%", "type": "integer", "group": "Plata"},
            {"key": "paid_half_quantity", "label": "Buc. platite 50%", "type": "integer", "group": "Plata"},
            {"key": "unpaid_quantity", "label": "Neplatite", "type": "integer", "group": "Plata"},
            {"key": "qualified_ui_quantity", "label": "Calificate UI", "type": "integer", "group": "Plata"},
            {"key": "potential_value", "label": "Valoare potentiala RON", "type": "currency", "group": "Incentive"},
            {"key": "paid_value", "label": "RON platiti", "type": "currency", "group": "Plata"},
        ]
        pool = getattr(self.repo, "pool", None)
        if pool is None:
            raise ExportValidationError("Exportul incentive nu are conexiune la baza de date.")

        def csv_filter(key: str) -> str | None:
            values = [value for value in filters.get(key, []) if value]
            return ",".join(values) if values else None

        rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        total_rows = 0
        for month in months:
            remaining = row_limit - len(rows_by_key)
            if remaining <= 0:
                raise ExportValidationError("Exportul incentive depaseste limita de randuri.")
            async with pool.acquire() as conn:
                campaign = await get_incentive_campaign(conn, month)
            if campaign is None:
                continue
            period_exclusions: dict[tuple[str, str, str], int] = {}
            periods = campaign.get("periods") or []
            if len(periods) <= 1:
                month_exclusions = await self._campaign_exclusions_by_month(
                    [month], filters, selected_days
                )
                for (site_code_value, _agent, item_code_value), units in month_exclusions.get(month, {}).items():
                    key = (
                        periods[0]["valid_from"].isoformat() if periods else "",
                        site_code_value,
                        item_code_value,
                    )
                    if key not in period_exclusions and len(period_exclusions) >= EXPORT_MAX_ROWS:
                        raise ExportValidationError("Exportul incentive depaseste limita de randuri.")
                    period_exclusions[key] = period_exclusions.get(key, 0) + units
            else:
                requested_days = set(selected_days or range(1, 32))
                for period in periods:
                    period_days = [
                        day for day in requested_days
                        if period["valid_from"].day <= day <= period["valid_to"].day
                    ]
                    if not period_days:
                        continue
                    period_result = await self._campaign_exclusions_by_month(
                        [month], filters, sorted(period_days)
                    )
                    for (site_code_value, _agent, item_code_value), units in period_result.get(month, {}).items():
                        key = (period["valid_from"].isoformat(), site_code_value, item_code_value)
                        if key not in period_exclusions and len(period_exclusions) >= EXPORT_MAX_ROWS:
                            raise ExportValidationError("Exportul incentive depaseste limita de randuri.")
                        period_exclusions[key] = period_exclusions.get(key, 0) + units
            async with pool.acquire() as conn:
                multipliers, achievements = await get_store_incentive_multipliers(
                    conn,
                    month,
                    firma=csv_filter("firma"),
                    regional=csv_filter("regional"),
                    asm=csv_filter("asm"),
                    site_code=csv_filter("site_code"),
                    current_scope=True,
                    include_closed_stores=include_closed_stores,
                )
            records = await self.repo.fetch_incentive_product_rows(
                month=month,
                filters=filters,
                include_closed_stores=include_closed_stores,
                selected_days=selected_days,
                limit=(
                    min(remaining, EXPORT_MAX_ROWS + 1)
                    if preview_limit is None or len(rows_by_key) < preview_limit
                    else 1
                ),
                include_total_count=preview_limit is not None,
            )
            month_total = self._record_total_count(records)
            total_rows += month_total if month_total is not None else len(records)
            if preview_limit is None and len(records) > remaining - 1:
                raise ExportValidationError("Exportul incentive depaseste limita de randuri.")
            for record in records:
                if preview_limit is not None and len(rows_by_key) >= preview_limit:
                    break
                reward = Decimal(record["reward_value"] or 0)
                row_key = (
                    month,
                    record["category"],
                    record["subcategory"],
                    record["item_code"],
                    record["item_name"],
                    reward,
                )
                row = rows_by_key.setdefault(row_key, {
                    "month": month,
                    "category": record["category"],
                    "subcategory": record["subcategory"],
                    "item_code": record["item_code"],
                    "item_name": record["item_name"],
                    "reward_value": reward,
                    "positive_quantity": 0,
                    "return_quantity": 0,
                    "net_quantity": 0,
                    "promo_excluded_quantity": 0,
                    "eligible_quantity": 0,
                    "paid_quantity": 0,
                    "paid_full_quantity": 0,
                    "paid_half_quantity": 0,
                    "unpaid_quantity": 0,
                    "qualified_ui_quantity": 0,
                    "potential_value": Decimal(0),
                    "paid_value": Decimal(0),
                })
                net_quantity = int(record["net_quantity"] or 0)
                # Exclusions cannot reduce a store-product below zero. This
                # is the same clipping used by Focus for promo incentive.
                excluded_quantity = min(
                    max(0, net_quantity),
                    int(period_exclusions.get((
                        record.get("valid_from").isoformat() if record.get("valid_from") else "",
                        record["site_code"],
                        record["item_code"],
                    ), 0)),
                )
                eligible_quantity = max(0, net_quantity - excluded_quantity)
                multiplier = Decimal(str(multipliers.get(record["site_code"], 0)))
                achievement = achievements.get(record["site_code"])
                row["positive_quantity"] += int(record["positive_quantity"] or 0)
                row["return_quantity"] += int(record["return_quantity"] or 0)
                row["net_quantity"] += net_quantity
                row["promo_excluded_quantity"] += excluded_quantity
                row["eligible_quantity"] += eligible_quantity
                row["potential_value"] += eligible_quantity * reward
                row["paid_value"] += eligible_quantity * reward * multiplier
                if multiplier > 0:
                    row["paid_quantity"] += eligible_quantity
                else:
                    row["unpaid_quantity"] += eligible_quantity
                if multiplier == 1:
                    row["paid_full_quantity"] += eligible_quantity
                elif multiplier > 0:
                    row["paid_half_quantity"] += eligible_quantity
                if achievement is not None and achievement >= 0.9:
                    row["qualified_ui_quantity"] += eligible_quantity

        rows = [self._public_row(row, columns) for row in rows_by_key.values()]
        rows.sort(key=lambda row: (
            str(row["month"]), str(row["category"]), str(row["subcategory"]), str(row["item_code"])
        ))
        visible_rows = rows[:preview_limit] if preview_limit is not None else rows
        self._validate_export_budget(len(visible_rows), len(columns), operation="Exportul incentive")
        return {"columns": columns, "rows": visible_rows}, (
            total_rows if preview_limit is not None else len(rows)
        )

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

    async def _run_complex_renderer(
        self,
        renderer_name: RendererName,
        payload: dict[str, Any],
        *,
        cells: int,
    ) -> XlsxArtifact:
        """Adopt only a complete, attested artifact from a killable child."""
        try:
            if renderer_name not in {"daily_metrics", "daily_comparison"}:
                raise ValueError("Unknown complex export renderer")
            result = await run_export_renderer_process(renderer_name, payload)
        except asyncio.CancelledError:
            raise
        except ExportRendererProcessError as exc:
            EXPORT_REJECTED_TOTAL.labels(exc.code).inc()
            if exc.code == "renderer_timeout":
                raise ExportValidationError("Exportul complex a depasit timpul maxim permis.") from exc
            if exc.code == "renderer_memory_limit":
                raise ExportValidationError("Exportul complex a depasit limita de memorie RSS.") from exc
            raise ExportValidationError("Exportul complex nu a putut fi finalizat in siguranta.") from exc
        except (MemoryError, OSError, ValueError) as exc:
            EXPORT_REJECTED_TOTAL.labels("complex_worker").inc()
            raise ExportValidationError("Exportul complex nu a putut fi finalizat in siguranta.") from exc

        raw_path = str(result.get("path") or "")
        raw_operation_directory = str(result.get("operation_directory") or "")
        path = Path(raw_path) if raw_path else None
        operation_directory = (
            Path(raw_operation_directory).resolve()
            if raw_operation_directory
            else None
        )
        stream: IO[bytes] | None = None
        try:
            if (
                path is None
                or operation_directory is None
                or not operation_directory.name.startswith("unihub-export-operation-")
                or path.resolve().parent != operation_directory
            ):
                EXPORT_REJECTED_TOTAL.labels("complex_artifact_path").inc()
                raise ExportValidationError("Calea artifactului exportului complex este invalida.")
            if not path.is_file():
                EXPORT_REJECTED_TOTAL.labels("complex_artifact").inc()
                raise ExportValidationError("Artifactul exportului complex lipseste.")
            size = path.stat().st_size
            expected_size = int(result.get("size") or -1)
            expected_hash = str(result.get("sha256") or "")
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(XLSX_STREAM_CHUNK_BYTES), b""):
                    digest.update(chunk)
            if size != expected_size or len(expected_hash) != 64 or digest.hexdigest() != expected_hash:
                EXPORT_REJECTED_TOTAL.labels("complex_artifact_hash").inc()
                raise ExportValidationError("Artifactul exportului complex nu a trecut verificarea de integritate.")
            if size > EXPORT_MAX_OUTPUT_BYTES:
                EXPORT_REJECTED_TOTAL.labels("output_bytes").inc()
                raise ExportValidationError("Fisierul XLSX depaseste limita de dimensiune de output.")
            peak_rss = int(result.get("peak_rss") or 0)
            if peak_rss <= 0 or peak_rss > EXPORT_MAX_PEAK_RSS_BYTES:
                EXPORT_REJECTED_TOTAL.labels("peak_rss_bytes").inc()
                raise ExportValidationError("Exportul depaseste limita de memorie RSS.")
            stream = path.open("r+b")
            EXPORT_BUILD_SECONDS.observe(float(result.get("build_seconds") or 0))
            EXPORT_OUTPUT_BYTES.set(size)
            EXPORT_CELLS.set(cells)
            EXPORT_PEAK_RSS_BYTES.set(peak_rss)
            return XlsxArtifact(
                stream=stream,
                filename=self._safe_filename(str(result.get("filename") or payload["filename"])),
                size=size,
                sha256=expected_hash,
                peak_rss_bytes=peak_rss,
                build_seconds=float(result.get("build_seconds") or 0),
                cell_count=cells,
            )
        except Exception:
            if stream is not None:
                stream.close()
            raise
        finally:
            if path is not None and path.is_file():
                path.unlink(missing_ok=True)
            if (
                operation_directory is not None
                and operation_directory.name.startswith("unihub-export-operation-")
            ):
                shutil.rmtree(operation_directory, ignore_errors=True)


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
