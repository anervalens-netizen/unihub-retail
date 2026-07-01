from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from models import (
    AiForecastDailyPoint,
    AiForecastManagerRow,
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


class AiForecastService:
    def __init__(self, repo: AiForecastRepository):
        self.repo = repo

    async def get_current(
        self,
        *,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
    ) -> AiForecastResponse | None:
        run = await self.repo.fetch_latest_run(month)
        if run is None:
            return None

        payload = await self.repo.fetch_response_rows(
            run_id=run["id"],
            forecast_month=run["forecast_month"],
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

        run_info = dict(run)
        if isinstance(run_info.get("metadata"), str):
            run_info["metadata"] = json.loads(run_info["metadata"])

        return AiForecastResponse(
            run=AiForecastRunInfo(**run_info),
            summary=AiForecastSummary(**summary),
            managers=[AiForecastManagerRow(**row) for row in managers],
            stores=[AiForecastStoreRow(**row) for row in stores],
            daily=[AiForecastDailyPoint(**row) for row in payload["daily"]],
        )
