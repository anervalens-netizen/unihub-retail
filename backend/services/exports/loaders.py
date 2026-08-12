"""Repository-only loading boundary; renderers never import this module."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol, Any

from services.campaigns import compute_promotion_result, load_campaign_context
from services.dashboard_specials import load_promotion_rule_products, load_special_cards_config, parse_promotion_definitions
from services.promotion_evaluation import PromotionEvaluationStatus, scope_promotion_definition_to_interval
from .validation import (
    EXPORT_MAX_ROWS,
    ExportValidationError,
    normalize_filters,
    scoped_filter_values,
)


class ExportRepository(Protocol):
    async def fetch_report_rows(self, **kwargs: Any) -> list[Any]: ...
    async def fetch_daily_evolution_rows(self, **kwargs: Any) -> list[Any]: ...
    async def fetch_daily_comparison_rows(self, **kwargs: Any) -> list[Any]: ...
    async def fetch_incentive_product_rows(self, **kwargs: Any) -> list[Any]: ...


class CampaignLoaders:
    """Promo source loading; all database I/O stays outside renderers."""

    repo: ExportRepository

    def _campaign_codes_by_month(self, months: list[str]) -> dict[str, list[str]]:
        config, error = load_special_cards_config()
        if error is not None:
            raise ExportValidationError("Export indisponibil: configuratia Promo nu poate fi validata.")
        output: dict[str, list[str]] = {}
        for month in months:
            definitions, definitions_error = parse_promotion_definitions(config, month)
            if definitions_error is not None:
                raise ExportValidationError(f"Export indisponibil pentru {month}: definitiile Promo sunt incomplete.")
            codes: set[str] = set()
            for definition in definitions:
                products, products_error = load_promotion_rule_products(definition)
                if products_error is not None or products is None:
                    raise ExportValidationError(f"Export indisponibil pentru {month}: produsele Promo nu pot fi validate.")
                codes.update(str(code) for code in products.get("discounted_codes" if definition.get("rule_type") in {"same_model_screen_camera", "trigger_discounted"} else "item_codes", []))
            if codes:
                output[month] = sorted(codes)
        return output

    @staticmethod
    def _promotion_filter_kwargs(
        scoped_filters: dict[str, list[str]],
    ) -> dict[str, list[str] | None]:
        return {
            key: scoped_filter_values(scoped_filters, key)
            for key in ("firma", "regional", "asm", "site_code", "agent")
        }

    @staticmethod
    def _selected_definition_dates(
        month: str,
        definition: dict[str, Any],
        selected_days: list[int],
    ) -> list[date]:
        year, month_number = (int(value) for value in month.split("-", 1))
        dates: list[date] = []
        for day in selected_days:
            try:
                candidate = date(year, month_number, day)
            except ValueError:
                continue
            if definition["start_date"] <= candidate <= definition["end_date"]:
                dates.append(candidate)
        return dates

    @staticmethod
    def _consecutive_ranges(dates: list[date]) -> list[tuple[date, date]]:
        ranges: list[tuple[date, date]] = []
        start = end = dates[0]
        for candidate in dates[1:]:
            if candidate == end + timedelta(days=1):
                end = candidate
            else:
                ranges.append((start, end))
                start = end = candidate
        ranges.append((start, end))
        return ranges

    @staticmethod
    def _promotion_definitions(month: str) -> list[dict[str, Any]]:
        config, config_error = load_special_cards_config()
        definitions, definitions_error = parse_promotion_definitions(config, month)
        if config_error is not None or definitions_error is not None:
            raise ExportValidationError(
                f"Export indisponibil pentru {month}: configuratia Promo este incompleta."
            )
        return definitions

    @staticmethod
    def _merge_excluded_units(
        units_by_key: dict[tuple[str, str, str], int],
        excluded_units: dict[tuple[str, str, str], int],
        max_entries: int,
    ) -> None:
        for key, units in excluded_units.items():
            if key not in units_by_key and len(units_by_key) >= max_entries:
                raise ExportValidationError(
                    "Excluderile Promo depasesc limita de randuri a exportului."
                )
            units_by_key[key] = units_by_key.get(key, 0) + units

    async def _selected_day_exclusions(
        self,
        conn: Any,
        *,
        month: str,
        scoped_filters: dict[str, list[str]],
        selected_days: list[int],
        max_entries: int,
    ) -> dict[tuple[str, str, str], int]:
        units_by_key: dict[tuple[str, str, str], int] = {}
        filter_kwargs = self._promotion_filter_kwargs(scoped_filters)
        for definition in self._promotion_definitions(month):
            dates = self._selected_definition_dates(month, definition, selected_days)
            if not dates:
                continue
            for start, end in self._consecutive_ranges(dates):
                evaluation = await compute_promotion_result(
                    conn,
                    month=month,
                    definition=scope_promotion_definition_to_interval(
                        definition,
                        start,
                        end,
                    ),
                    **filter_kwargs,
                )
                if (
                    evaluation.status is not PromotionEvaluationStatus.COMPLETE
                    or evaluation.result is None
                ):
                    raise ExportValidationError(
                        f"Export indisponibil pentru {month}: excluderile Promo "
                        "nu pot fi validate complet."
                    )
                self._merge_excluded_units(
                    units_by_key,
                    evaluation.result.excluded_units,
                    max_entries,
                )
        return units_by_key

    async def _full_month_exclusions(
        self,
        conn: Any,
        *,
        month: str,
        scoped_filters: dict[str, list[str]],
    ) -> dict[tuple[str, str, str], int]:
        context = await load_campaign_context(
            conn,
            month,
            **self._promotion_filter_kwargs(scoped_filters),
        )
        if context.promotion_status is not PromotionEvaluationStatus.COMPLETE:
            raise ExportValidationError(
                f"Export indisponibil pentru {month}: excluderile Promo "
                "nu pot fi validate complet."
            )
        return {
            (str(site), str(agent), str(item)): int(units)
            for (site, agent, item), units in (
                context.promo_excluded_units or {}
            ).items()
        }

    @staticmethod
    def _add_month_exclusions(
        output: dict[str, dict[tuple[str, str, str], int]],
        month: str,
        units_by_key: dict[tuple[str, str, str], int],
        max_entries: int,
    ) -> None:
        if not units_by_key:
            return
        total_entries = sum(len(value) for value in output.values())
        if len(units_by_key) > max_entries or total_entries + len(units_by_key) > max_entries:
            raise ExportValidationError(
                "Excluderile Promo depasesc limita de randuri a exportului."
            )
        output[month] = units_by_key

    async def _campaign_exclusions_by_month(
        self,
        months: list[str],
        filters: dict[str, list[str]],
        selected_days: list[int] | None = None,
        max_entries: int = EXPORT_MAX_ROWS,
    ) -> dict[str, dict[tuple[str, str, str], int]]:
        pool = getattr(self.repo, "pool", None)
        if pool is None:
            return {}
        scoped_filters = normalize_filters(filters)
        output: dict[str, dict[tuple[str, str, str], int]] = {}
        async with pool.acquire() as conn:
            for month in months:
                if selected_days:
                    units_by_key = await self._selected_day_exclusions(
                        conn,
                        month=month,
                        scoped_filters=scoped_filters,
                        selected_days=selected_days,
                        max_entries=max_entries,
                    )
                else:
                    units_by_key = await self._full_month_exclusions(
                        conn,
                        month=month,
                        scoped_filters=scoped_filters,
                    )
                self._add_month_exclusions(
                    output,
                    month,
                    units_by_key,
                    max_entries,
                )
        return output
