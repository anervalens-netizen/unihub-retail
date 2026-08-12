from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from services.campaigns import get_store_incentive_multipliers
from services.incentive_db import get_incentive_campaign
from .validation import (
    EXPORT_MAX_ROWS,
    ExportValidationError,
    preview_limit,
    scoped_filter_values,
)


EXPORT_COMPLEX_SEMAPHORE = asyncio.Semaphore(1)

INCENTIVE_COLUMNS = [
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


def _add_exclusion(
    exclusions: dict[tuple[str, str, str], int],
    key: tuple[str, str, str],
    units: int,
) -> None:
    if key not in exclusions and len(exclusions) >= EXPORT_MAX_ROWS:
        raise ExportValidationError("Exportul incentive depaseste limita de randuri.")
    exclusions[key] = exclusions.get(key, 0) + units


class IncentiveReportBuilder:
    if TYPE_CHECKING:
        repo: Any
        _campaign_exclusions_by_month: Any
        _public_row: Any
        _validate_export_budget: Any
        _record_total_count: Any

    async def _single_period_exclusions(
        self,
        month: str,
        periods: list[dict[str, Any]],
        filters: dict[str, list[str]],
        selected_days: list[int] | None,
    ) -> dict[tuple[str, str, str], int]:
        source = await self._campaign_exclusions_by_month([month], filters, selected_days)
        prefix = periods[0]["valid_from"].isoformat() if periods else ""
        result: dict[tuple[str, str, str], int] = {}
        for (site_code, _agent, item_code), units in source.get(month, {}).items():
            _add_exclusion(result, (prefix, site_code, item_code), units)
        return result

    async def _multiple_period_exclusions(
        self,
        month: str,
        periods: list[dict[str, Any]],
        filters: dict[str, list[str]],
        selected_days: list[int] | None,
    ) -> dict[tuple[str, str, str], int]:
        requested_days = set(selected_days or range(1, 32))
        result: dict[tuple[str, str, str], int] = {}
        for period in periods:
            days = [
                day
                for day in requested_days
                if period["valid_from"].day <= day <= period["valid_to"].day
            ]
            if not days:
                continue
            source = await self._campaign_exclusions_by_month(
                [month], filters, sorted(days)
            )
            prefix = period["valid_from"].isoformat()
            for (site_code, _agent, item_code), units in source.get(month, {}).items():
                _add_exclusion(result, (prefix, site_code, item_code), units)
        return result

    async def _period_exclusions(
        self,
        month: str,
        campaign: dict[str, Any],
        filters: dict[str, list[str]],
        selected_days: list[int] | None,
    ) -> dict[tuple[str, str, str], int]:
        periods = campaign.get("periods") or []
        if len(periods) <= 1:
            return await self._single_period_exclusions(
                month, periods, filters, selected_days
            )
        return await self._multiple_period_exclusions(
            month, periods, filters, selected_days
        )

    async def _store_context(
        self,
        pool: Any,
        month: str,
        filters: dict[str, list[str]],
        include_closed_stores: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
        async with pool.acquire() as conn:
            campaign = await get_incentive_campaign(conn, month)
        if campaign is None:
            return None, {}, {}
        async with pool.acquire() as conn:
            multipliers, achievements = await get_store_incentive_multipliers(
                conn,
                month,
                firma=scoped_filter_values(filters, "firma"),
                regional=scoped_filter_values(filters, "regional"),
                asm=scoped_filter_values(filters, "asm"),
                site_code=scoped_filter_values(filters, "site_code"),
                current_scope=True,
                include_closed_stores=include_closed_stores,
            )
        return campaign, multipliers, achievements

    @staticmethod
    def _incentive_row_key(
        month: str, record: Any, reward: Decimal
    ) -> tuple[Any, ...]:
        return (
            month,
            record["category"],
            record["subcategory"],
            record["item_code"],
            record["item_name"],
            reward,
        )

    @staticmethod
    def _new_incentive_row(
        month: str, record: Any, reward: Decimal
    ) -> dict[str, Any]:
        return {
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
        }

    @staticmethod
    def _update_row(
        row: dict[str, Any],
        record: Any,
        exclusions: dict[tuple[str, str, str], int],
        multipliers: dict[str, Any],
        achievements: dict[str, Any],
    ) -> None:
        net = int(record["net_quantity"] or 0)
        prefix = record.get("valid_from").isoformat() if record.get("valid_from") else ""
        excluded = min(
            max(0, net),
            int(exclusions.get((prefix, record["site_code"], record["item_code"]), 0)),
        )
        eligible = max(0, net - excluded)
        multiplier = Decimal(str(multipliers.get(record["site_code"], 0)))
        reward = row["reward_value"]
        row["positive_quantity"] += int(record["positive_quantity"] or 0)
        row["return_quantity"] += int(record["return_quantity"] or 0)
        row["net_quantity"] += net
        row["promo_excluded_quantity"] += excluded
        row["eligible_quantity"] += eligible
        row["potential_value"] += eligible * reward
        row["paid_value"] += eligible * reward * multiplier
        row["paid_quantity" if multiplier > 0 else "unpaid_quantity"] += eligible
        if multiplier == 1:
            row["paid_full_quantity"] += eligible
        elif multiplier > 0:
            row["paid_half_quantity"] += eligible
        achievement = achievements.get(record["site_code"])
        if achievement is not None and achievement >= 0.9:
            row["qualified_ui_quantity"] += eligible

    async def _month_rows(
        self,
        *,
        month: str,
        filters: dict[str, list[str]],
        include_closed_stores: bool,
        selected_days: list[int] | None,
        remaining: int,
        preview_limit: int | None,
        current_rows: int,
    ) -> tuple[list[Any], dict[tuple[str, str, str], int], dict[str, Any], dict[str, Any]]:
        pool = getattr(self.repo, "pool", None)
        if pool is None:
            raise ExportValidationError(
                "Exportul incentive nu are conexiune la baza de date."
            )
        campaign, multipliers, achievements = await self._store_context(
            pool, month, filters, include_closed_stores
        )
        if campaign is None:
            return [], {}, multipliers, achievements
        exclusions = await self._period_exclusions(
            month, campaign, filters, selected_days
        )
        limit = (
            min(remaining, EXPORT_MAX_ROWS + 1)
            if preview_limit is None or current_rows < preview_limit
            else 1
        )
        records = await self.repo.fetch_incentive_product_rows(
            month=month,
            filters=filters,
            include_closed_stores=include_closed_stores,
            selected_days=selected_days,
            limit=limit,
            include_total_count=preview_limit is not None,
        )
        return records, exclusions, multipliers, achievements

    def _public_incentive_result(
        self,
        rows_by_key: dict[tuple[Any, ...], dict[str, Any]],
        total_rows: int,
        preview_limit: int | None,
    ) -> tuple[dict[str, Any], int]:
        rows = [self._public_row(row, INCENTIVE_COLUMNS) for row in rows_by_key.values()]
        rows.sort(
            key=lambda row: (
                str(row["month"]),
                str(row["category"]),
                str(row["subcategory"]),
                str(row["item_code"]),
            )
        )
        visible = rows[:preview_limit] if preview_limit is not None else rows
        self._validate_export_budget(
            len(visible), len(INCENTIVE_COLUMNS), operation="Exportul incentive"
        )
        result_count = total_rows if preview_limit is not None else len(rows)
        return {"columns": INCENTIVE_COLUMNS, "rows": visible}, result_count

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
        rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        total_rows = 0
        for month in months:
            remaining = row_limit - len(rows_by_key)
            if remaining <= 0:
                raise ExportValidationError(
                    "Exportul incentive depaseste limita de randuri."
                )
            records, exclusions, multipliers, achievements = await self._month_rows(
                month=month,
                filters=filters,
                include_closed_stores=include_closed_stores,
                selected_days=selected_days,
                remaining=remaining,
                preview_limit=preview_limit,
                current_rows=len(rows_by_key),
            )
            count = self._record_total_count(records)
            total_rows += count if count is not None else len(records)
            if preview_limit is None and len(records) > remaining - 1:
                raise ExportValidationError(
                    "Exportul incentive depaseste limita de randuri."
                )
            for record in records:
                if preview_limit is not None and len(rows_by_key) >= preview_limit:
                    break
                reward = Decimal(record["reward_value"] or 0)
                key = self._incentive_row_key(month, record, reward)
                row = rows_by_key.setdefault(
                    key, self._new_incentive_row(month, record, reward)
                )
                self._update_row(row, record, exclusions, multipliers, achievements)
        return self._public_incentive_result(rows_by_key, total_rows, preview_limit)
