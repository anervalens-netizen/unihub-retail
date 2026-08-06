"""Forecast coverage contract used by Target profitability calculations."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.target_calculator.calculations import money


def forecast_coverage(
    rows: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Decimal]]:
    expected_site_codes = sorted({str(row["site_code"]) for row in rows})
    records_by_site = {str(record["site_code"]): record for record in inputs.get("forecast_rows") or []}
    forecast_values: dict[str, Decimal] = {}
    covered_site_codes: list[str] = []
    missing_site_codes: list[str] = []
    cutoff_values: list[str] = []
    for site_code in expected_site_codes:
        record = records_by_site.get(site_code)
        forecast_present = bool(record and record.get("forecast_present"))
        realized_present = bool(record and record.get("realized_present"))
        forecast_sales = record.get("forecast_sales") if record else None
        cutoff_date = record.get("cutoff_date") if record else None
        if not forecast_present or not realized_present or forecast_sales is None or cutoff_date is None:
            missing_site_codes.append(site_code)
            continue
        forecast_values[site_code] = money(Decimal(forecast_sales))
        covered_site_codes.append(site_code)
        cutoff_values.append(str(cutoff_date))
    distinct_cutoffs = sorted(set(cutoff_values))
    uniform = inputs.get("forecast_run") is not None and len(covered_site_codes) == len(expected_site_codes) and len(distinct_cutoffs) == 1
    return ({
        "mode": "uniform" if uniform else "nonuniform",
        "cutoff": distinct_cutoffs[0] if uniform else None,
        "cutoff_min": min(cutoff_values) if cutoff_values else None,
        "cutoff_max": max(cutoff_values) if cutoff_values else None,
        "expected_store_count": len(expected_site_codes),
        "covered_store_count": len(covered_site_codes),
        "missing_site_codes": missing_site_codes,
    }, forecast_values)
