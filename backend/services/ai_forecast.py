from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Literal

from models import (
    AiForecastDailyPoint,
    AiForecastManagerRow,
    AiForecastRollingManagerRow,
    AiForecastRollingMonthlyPoint,
    AiForecastRollingResponse,
    AiForecastRollingStoreRow,
    AiForecastRollingSummary,
    AiForecastResponse,
    AiForecastRunInfo,
    AiForecastStoreRow,
    AiForecastSummary,
)
from repositories.ai_forecast import AiForecastRepository


def _delta_pct(actual: Decimal, expected: Decimal) -> Decimal | None:
    if expected == 0:
        return None
    return (actual - expected) / expected * Decimal("100")


def _with_delta(row: dict[str, Any]) -> dict[str, Any]:
    actual = row["actual_sales"]
    expected = row["expected_sales_to_date"]
    return {
        **row,
        "delta_sales": actual - expected,
        "delta_pct": _delta_pct(actual, expected),
    }


def _with_forecast_delta(row: dict[str, Any]) -> dict[str, Any]:
    actual = row.get("actual_sales")
    forecast = row["forecast_sales"]
    if actual is None:
        return {
            **row,
            "delta_sales": None,
            "delta_pct": None,
        }
    return {
        **row,
        "delta_sales": actual - forecast,
        "delta_pct": _delta_pct(actual, forecast),
    }


def add_month(month: str, offset: int) -> str:
    year, month_number = map(int, month.split("-"))
    month_index = year * 12 + (month_number - 1) + offset
    return f"{month_index // 12:04d}-{month_index % 12 + 1:02d}"


def _run_info(row: Any) -> AiForecastRunInfo:
    run_info = dict(row)
    if isinstance(run_info.get("metadata"), str):
        run_info["metadata"] = json.loads(run_info["metadata"])
    return AiForecastRunInfo(**run_info)


class AiForecastService:
    def __init__(self, repo: AiForecastRepository):
        self.repo = repo

    async def get_current(
        self,
        *,
        month: str,
        metric: Literal["sales_value", "units"],
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> AiForecastResponse | None:
        run = await self.repo.fetch_latest_run(month, metric=metric)
        if run is None:
            return None

        payload = await self.repo.fetch_response_rows(
            run_id=run["id"],
            forecast_month=run["forecast_month"],
            metric=metric,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
        )
        if payload is None:
            return None

        summary = _with_delta(
            {
                **payload["summary"],
                "source_month": run["source_month"],
            }
        )
        managers = [_with_delta(row) for row in payload["managers"]]
        stores = [_with_delta(row) for row in payload["stores"]]

        return AiForecastResponse(
            run=_run_info(run),
            summary=AiForecastSummary(**summary),
            managers=[AiForecastManagerRow(**row) for row in managers],
            stores=[AiForecastStoreRow(**row) for row in stores],
            daily=[AiForecastDailyPoint(**row) for row in payload["daily"]],
        )

    async def get_rolling_12(
        self,
        *,
        month: str,
        metric: Literal["sales_value", "units"],
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> AiForecastRollingResponse | None:
        start_month = add_month(month, 1)
        end_month = add_month(month, 12)
        runs = await self.repo.fetch_latest_rolling_runs(
            anchor_month=month,
            start_month=start_month,
            end_month=end_month,
            metric=metric,
        )
        if not runs:
            return None

        payload = await self.repo.fetch_rolling_rows(
            run_ids=[int(run["id"]) for run in runs],
            metric=metric,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
        )
        if payload is None:
            return None

        months = [_with_forecast_delta(row) for row in payload["months"]]
        managers = [_with_forecast_delta(row) for row in payload["managers"]]
        stores = [_with_forecast_delta(row) for row in payload["stores"]]
        summary = _with_forecast_delta(
            {
                **payload["summary"],
                "source_month": runs[0]["source_month"],
                "start_month": start_month,
                "end_month": end_month,
                "month_count": len(months),
            }
        )

        return AiForecastRollingResponse(
            runs=[_run_info(run) for run in runs],
            summary=AiForecastRollingSummary(**summary),
            months=[AiForecastRollingMonthlyPoint(**row) for row in months],
            managers=[AiForecastRollingManagerRow(**row) for row in managers],
            stores=[AiForecastRollingStoreRow(**row) for row in stores],
        )
