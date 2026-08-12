from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from .catalog import (
    CAMPAIGN_METRICS,
    DAILY_EVOLUTION_METRICS,
    DATASETS,
    DEFAULT_METRICS,
    EVOLUTION_METRICS,
    METRICS,
)
from .validation import (
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


@dataclass(slots=True)
class _ReportPlan:
    dataset: str
    months: list[str]
    selected_days: list[int] | None
    include_closed_stores: bool
    filters: dict[str, list[str]]
    dimensions: list[str]
    metrics: list[str]
    monthly_metrics: list[str]
    daily_metrics: list[str]
    total_campaign_metrics: bool
    monthly_campaign_metrics: bool


class ReportBuilder:
    if TYPE_CHECKING:
        repo: Any
        _campaign_codes_by_month: Any
        _campaign_exclusions_by_month: Any
        _row_key: Any
        _base_row: Any
        _attach_period_metrics: Any
        _build_columns: Any
        _public_row: Any
        _record_total_count: Any
        _build_incentive_products_report: Any

    @staticmethod
    def _report_plan(request: dict[str, Any]) -> _ReportPlan:
        dataset = str(request.get("dataset") or "")
        if dataset not in DATASETS:
            raise ExportValidationError("Dataset invalid.")
        months = sorted({str(item) for item in request.get("months", []) if item})
        if not months:
            raise ExportValidationError("Selecteaza cel putin o luna.")
        if len(months) > 144:
            raise ExportValidationError("Selectia poate contine maxim 144 luni.")
        daily_metrics = valid_keys(
            request.get("daily_metrics"), set(DAILY_EVOLUTION_METRICS), [], "metrici zilnice"
        )
        if daily_metrics and len(months) > 3:
            raise ExportValidationError("Evolutia zilnica este limitata la maxim 3 luni selectate.")
        if daily_metrics and len(daily_metrics) * 31 * len(months) > 220:
            raise ExportValidationError(
                "Prea multe coloane zilnice. Redu lunile sau metricile zilnice."
            )
        dimensions = valid_keys(
            request.get("dimensions"),
            set(DATASETS[dataset]["dimensions"]),
            list(DATASETS[dataset]["dimensions"]),
            "dimensiuni",
        )
        metrics = valid_keys(request.get("metrics"), set(METRICS), DEFAULT_METRICS, "metrici")
        monthly = valid_keys(
            request.get("monthly_metrics"), set(EVOLUTION_METRICS), [], "metrici lunare"
        )
        return _ReportPlan(
            dataset=dataset,
            months=months,
            selected_days=parse_selected_days(request),
            include_closed_stores=bool(request.get("include_closed_stores", False)),
            filters=normalize_filters(request.get("filters") or {}),
            dimensions=dimensions,
            metrics=metrics,
            monthly_metrics=monthly,
            daily_metrics=daily_metrics,
            total_campaign_metrics=bool(CAMPAIGN_METRICS.intersection(metrics)),
            monthly_campaign_metrics=bool(CAMPAIGN_METRICS.intersection(monthly)),
        )

    async def _campaign_inputs(
        self, plan: _ReportPlan
    ) -> tuple[dict[str, list[str]], dict[str, dict[tuple[str, str, str], int]]]:
        needed = plan.total_campaign_metrics or plan.monthly_campaign_metrics
        if not needed:
            return {}, {}
        return self._campaign_codes_by_month(plan.months), await self._campaign_exclusions_by_month(
            plan.months, plan.filters, plan.selected_days
        )

    async def _load_total_records(
        self,
        plan: _ReportPlan,
        campaign_codes: dict[str, list[str]],
        exclusions: dict[str, dict[tuple[str, str, str], int]],
        *,
        row_limit: int,
        preview_limit: int | None,
    ) -> tuple[list[Any], dict[tuple[Any, ...], dict[str, Any]]]:
        records = await self.repo.fetch_report_rows(
            dataset=plan.dataset,
            months=plan.months,
            filters=plan.filters,
            include_closed_stores=plan.include_closed_stores,
            campaign_codes_by_month=campaign_codes,
            campaign_exclusions_by_month=exclusions,
            selected_days=plan.selected_days,
            include_campaign_metrics=plan.total_campaign_metrics,
            limit=row_limit,
            include_total_count=preview_limit is not None,
        )
        if preview_limit is None and len(records) > EXPORT_MAX_ROWS:
            raise ExportValidationError("Exportul depaseste limita de randuri.")
        visible = records[:preview_limit] if preview_limit is not None else records
        rows = {
            self._row_key(record, plan.dataset): self._base_row(
                record, plan.dimensions, plan.metrics
            )
            for record in visible
        }
        max_days = (
            len(plan.selected_days)
            if plan.selected_days
            else max_days_for_months(plan.months)
        )
        columns = (
            len(plan.dimensions)
            + len(plan.metrics)
            + len(plan.months) * len(plan.monthly_metrics)
            + max_days * len(plan.daily_metrics)
        )
        validate_budget(len(rows), columns, operation="Raportul")
        return records, rows

    def _period_loaders(
        self,
        plan: _ReportPlan,
        campaign_codes: dict[str, list[str]],
        exclusions: dict[str, dict[tuple[str, str, str], int]],
        preview_limit: int | None,
    ) -> tuple[dict[str, Any], int]:
        multiplier = len(plan.months) * max(
            1, len(plan.monthly_metrics) + len(plan.daily_metrics)
        )
        period_limit = min(
            EXPORT_MAX_ROWS + 1,
            max(1, (preview_limit or EXPORT_MAX_ROWS) * max(1, multiplier)) + 1,
        )
        common = {
            "dataset": plan.dataset,
            "months": plan.months,
            "filters": plan.filters,
            "include_closed_stores": plan.include_closed_stores,
            "campaign_codes_by_month": campaign_codes,
            "campaign_exclusions_by_month": exclusions,
            "selected_days": plan.selected_days,
            "limit": period_limit,
        }
        loaders: dict[str, Any] = {}
        if plan.monthly_metrics:
            loaders["month"] = self.repo.fetch_report_rows(
                period="month",
                include_campaign_metrics=plan.monthly_campaign_metrics,
                **common,
            )
        if plan.daily_metrics:
            loaders["day"] = self.repo.fetch_report_rows(
                period="day", include_campaign_metrics=False, **common
            )
        return loaders, period_limit

    @staticmethod
    async def _await_period_records(
        loaders: dict[str, Any], period_limit: int, preview_limit: int | None
    ) -> dict[str, list[Any]]:
        if not loaders:
            return {}
        names = tuple(loaders)
        tasks = {
            name: asyncio.create_task(loaders[name], name=f"export:{name}")
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
        records = dict(zip(names, results, strict=True))
        for name, rows in records.items():
            if preview_limit is None and len(rows) > EXPORT_MAX_ROWS:
                raise ExportValidationError(
                    f"Exportul depaseste limita de randuri pentru evolutia {name}."
                )
            if preview_limit is not None:
                records[name] = rows[:period_limit]
        return records

    def _attach_period_records(
        self,
        plan: _ReportPlan,
        rows: dict[tuple[Any, ...], dict[str, Any]],
        periods: dict[str, list[Any]],
    ) -> None:
        if plan.monthly_metrics:
            self._attach_period_metrics(
                rows,
                periods["month"],
                plan.dataset,
                plan.monthly_metrics,
                period_prefix="month",
            )
        if plan.daily_metrics:
            self._attach_period_metrics(
                rows,
                periods["day"],
                plan.dataset,
                plan.daily_metrics,
                period_prefix="day",
            )

    def _finalize_report(
        self,
        plan: _ReportPlan,
        rows_by_key: dict[tuple[Any, ...], dict[str, Any]],
        total_records: list[Any],
        preview_limit: int | None,
    ) -> tuple[dict[str, Any], int]:
        columns = self._build_columns(
            plan.dataset,
            plan.dimensions,
            plan.metrics,
            plan.months,
            plan.monthly_metrics,
            rows_by_key,
            plan.daily_metrics,
        )
        rows = list(rows_by_key.values())
        rows.sort(key=lambda row: tuple(str(row.get(dim) or "") for dim in plan.dimensions))
        validate_budget(len(rows), len(columns), operation="Raportul")
        visible = rows[:preview_limit] if preview_limit is not None else rows
        result = {
            "columns": columns,
            "rows": [self._public_row(row, columns) for row in visible],
        }
        if preview_limit is None:
            return result, len(rows)
        total = self._record_total_count(total_records)
        return result, total if total is not None else max(len(total_records), len(rows))

    async def _build_report(
        self,
        request: dict[str, Any],
        *,
        row_limit: int,
        preview_limit: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        plan = self._report_plan(request)
        if plan.dataset == "incentive_products":
            return await self._build_incentive_products_report(
                months=plan.months,
                filters=plan.filters,
                include_closed_stores=plan.include_closed_stores,
                selected_days=plan.selected_days,
                row_limit=row_limit,
                preview_limit=preview_limit,
            )
        campaign_codes, exclusions = await self._campaign_inputs(plan)
        total_records, rows = await self._load_total_records(
            plan,
            campaign_codes,
            exclusions,
            row_limit=row_limit,
            preview_limit=preview_limit,
        )
        loaders, period_limit = self._period_loaders(
            plan, campaign_codes, exclusions, preview_limit
        )
        periods = await self._await_period_records(loaders, period_limit, preview_limit)
        self._attach_period_records(plan, rows, periods)
        return self._finalize_report(plan, rows, total_records, preview_limit)
