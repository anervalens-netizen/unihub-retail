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

    async def _campaign_exclusions_by_month(self, months: list[str], filters: dict[str, list[str]], selected_days: list[int] | None = None, max_entries: int = EXPORT_MAX_ROWS) -> dict[str, dict[tuple[str, str, str], int]]:
        pool = getattr(self.repo, "pool", None)
        if pool is None:
            return {}
        scoped_filters = normalize_filters(filters)
        output: dict[str, dict[tuple[str, str, str], int]] = {}
        async with pool.acquire() as conn:
            for month in months:
                if selected_days:
                    config, config_error = load_special_cards_config()
                    definitions, definitions_error = parse_promotion_definitions(config, month)
                    if config_error is not None or definitions_error is not None:
                        raise ExportValidationError(f"Export indisponibil pentru {month}: configuratia Promo este incompleta.")
                    units_by_key: dict[tuple[str, str, str], int] = {}
                    year, month_number = (int(value) for value in month.split("-", 1))
                    for definition in definitions:
                        dates = []
                        for day in selected_days:
                            try:
                                candidate = date(year, month_number, day)
                            except ValueError:
                                continue
                            if definition["start_date"] <= candidate <= definition["end_date"]:
                                dates.append(candidate)
                        if not dates:
                            continue
                        ranges: list[tuple[date, date]] = []
                        start = end = dates[0]
                        for candidate in dates[1:]:
                            if candidate == end + timedelta(days=1): end = candidate
                            else: ranges.append((start, end)); start = end = candidate
                        ranges.append((start, end))
                        for start, end in ranges:
                            evaluation = await compute_promotion_result(conn, month=month, definition=scope_promotion_definition_to_interval(definition, start, end), firma=scoped_filter_values(scoped_filters, "firma"), regional=scoped_filter_values(scoped_filters, "regional"), asm=scoped_filter_values(scoped_filters, "asm"), site_code=scoped_filter_values(scoped_filters, "site_code"), agent=scoped_filter_values(scoped_filters, "agent"))
                            if evaluation.status is not PromotionEvaluationStatus.COMPLETE or evaluation.result is None:
                                raise ExportValidationError(f"Export indisponibil pentru {month}: excluderile Promo nu pot fi validate complet.")
                            for key, units in evaluation.result.excluded_units.items():
                                if key not in units_by_key and len(units_by_key) >= max_entries:
                                    raise ExportValidationError("Excluderile Promo depasesc limita de randuri a exportului.")
                                units_by_key[key] = units_by_key.get(key, 0) + units
                    if units_by_key:
                        if len(units_by_key) > max_entries or sum(len(value) for value in output.values()) + len(units_by_key) > max_entries:
                            raise ExportValidationError("Excluderile Promo depasesc limita de randuri a exportului.")
                        output[month] = units_by_key
                    continue
                context = await load_campaign_context(conn, month, firma=scoped_filter_values(scoped_filters, "firma"), regional=scoped_filter_values(scoped_filters, "regional"), asm=scoped_filter_values(scoped_filters, "asm"), site_code=scoped_filter_values(scoped_filters, "site_code"), agent=scoped_filter_values(scoped_filters, "agent"))
                if context.promotion_status is not PromotionEvaluationStatus.COMPLETE:
                    raise ExportValidationError(f"Export indisponibil pentru {month}: excluderile Promo nu pot fi validate complet.")
                if context.promo_excluded_units:
                    if len(context.promo_excluded_units) > max_entries or sum(len(value) for value in output.values()) + len(context.promo_excluded_units) > max_entries:
                        raise ExportValidationError("Excluderile Promo depasesc limita de randuri a exportului.")
                    output[month] = {(str(site), str(agent), str(item)): int(units) for (site, agent, item), units in context.promo_excluded_units.items()}
        return output
