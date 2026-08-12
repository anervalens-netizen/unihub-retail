"""Fast read-only overview over the worker-produced Grile V2 snapshot."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any

from repositories.grile import GrileRepository
from services.grile import DEFAULT_TOLERANCE
from services.grile_pilot_v2_registry import (
    PILOT_V2_MONTH,
    PILOT_V2_SHEETS,
)


PILOT_V2_SNAPSHOT_SCHEMA_VERSION = 1
PILOT_V2_SNAPSHOT_PATH = Path(
    os.getenv(
        "GRILE_PILOT_V2_SNAPSHOT_PATH",
        Path(__file__).resolve().parents[1]
        / "outputs"
        / "grile"
        / "pilot-v2-overview-2026-08.json",
    )
)


@dataclass(frozen=True)
class PilotV2Reading:
    target: Decimal | None
    realized: Decimal | None
    forecast: Decimal | None
    error: str | None = None


def _load_pilot_v2_snapshot() -> dict[str, PilotV2Reading]:
    """Load the bounded last-good projection without any Google request."""

    with PILOT_V2_SNAPSHOT_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != PILOT_V2_SNAPSHOT_SCHEMA_VERSION
        or payload.get("month") != PILOT_V2_MONTH
        or not isinstance(payload.get("stores"), dict)
    ):
        raise RuntimeError("Grile V2 snapshot is invalid")
    stores = payload["stores"]
    expected_sites = {sheet.site_code for sheet in PILOT_V2_SHEETS}
    if set(stores) != expected_sites:
        raise RuntimeError("Grile V2 snapshot coverage is invalid")
    readings: dict[str, PilotV2Reading] = {}
    for site_code, values in stores.items():
        if not isinstance(values, dict):
            raise RuntimeError("Grile V2 snapshot store is invalid")
        try:
            readings[site_code] = PilotV2Reading(
                Decimal(str(values["target"])),
                Decimal(str(values["realized"])),
                Decimal(str(values["forecast"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Grile V2 snapshot values are invalid") from exc
    return readings


async def read_pilot_v2_snapshot() -> dict[str, PilotV2Reading]:
    return await asyncio.to_thread(_load_pilot_v2_snapshot)


def _delta_message(label: str, delta: Decimal) -> str:
    rounded = delta.quantize(Decimal("1"))
    sign = "+" if rounded > 0 else ""
    return f"{label} V2 {sign}{rounded} lei"


def _compare(
    reading: PilotV2Reading,
    *,
    target: Any,
    realized: Any,
    missing_message: str,
) -> dict[str, Any]:
    if reading.error is not None:
        return {"status": "unavailable", "message": reading.error}
    if target is None or realized is None:
        return {"status": "unavailable", "message": missing_message}
    reference_target = Decimal(str(target))
    reference_realized = Decimal(str(realized))
    if reading.target is None or reading.realized is None:
        return {"status": "problem", "message": "Valori V2 incomplete"}
    target_delta = reading.target - reference_target
    realized_delta = reading.realized - reference_realized
    issues = []
    tolerance = Decimal(str(DEFAULT_TOLERANCE))
    if abs(target_delta) > tolerance:
        issues.append(_delta_message("Target", target_delta))
    if abs(realized_delta) > tolerance:
        issues.append(_delta_message("Realizat", realized_delta))
    return {
        "status": "problem" if issues else "ok",
        "message": "; ".join(issues) if issues else "OK",
        "target": reference_target,
        "realized": reference_realized,
        "target_diff": target_delta,
        "realized_diff": realized_delta,
    }


def _percentage(value: Decimal | None, target: Decimal | None) -> Decimal | None:
    if value is None or target is None or target <= 0:
        return None
    return (value / target * Decimal("100")).quantize(Decimal("0.1"))


def _store_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("firma") or ""), str(item.get("locatie") or "")


def _store_payload(
    sheet: PilotV2Sheet,
    reading: PilotV2Reading,
    hierarchy: dict[str, dict[str, Any]],
    expected: dict[str, dict[str, Any]],
    v1_by_site: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    store = hierarchy.get(sheet.site_code, {})
    report = expected.get(sheet.site_code, {})
    v1 = v1_by_site.get(sheet.site_code, {})
    return {
        "site_code": sheet.site_code,
        "sheet_id": sheet.sheet_id,
        "locatie": store.get("locatie") or sheet.site_code,
        "firma": store.get("firma") or "",
        "manager": store.get("asm") or store.get("regional") or "Nealocat",
        "target_v2": reading.target,
        "realized_v2": reading.realized,
        "realized_pct_v2": _percentage(reading.realized, reading.target),
        "forecast_v2": reading.forecast,
        "forecast_pct_v2": _percentage(reading.forecast, reading.target),
        "report_cutoff": report.get("db_max_sale_date"),
        "report_check": _compare(
            reading,
            target=report.get("db_target"),
            realized=report.get("db_sales_mtd"),
            missing_message="Raport Retail indisponibil",
        ),
        "v1_check": _compare(
            reading,
            target=v1.get("grila_target"),
            realized=v1.get("grila_sales"),
            missing_message="V1 neverificat",
        ),
    }


async def get_pilot_v2_overview(repo: GrileRepository, month: str) -> dict[str, Any]:
    if month != PILOT_V2_MONTH:
        raise ValueError("Pilotul V2 este disponibil doar pentru august 2026.")
    expected, hierarchy, current_statuses, readings = await asyncio.gather(
        repo.get_expected_by_site(month),
        repo.get_hierarchy(),
        repo.get_current_statuses(month),
        read_pilot_v2_snapshot(),
    )
    v1_by_site: dict[str, dict[str, Any]] = {}
    for row in current_statuses:
        payload = dict(row)
        v1_by_site[str(payload["site_code"])] = payload
    stores = [
        _store_payload(sheet, readings[sheet.site_code], hierarchy, expected, v1_by_site)
        for sheet in PILOT_V2_SHEETS
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for store in stores:
        grouped.setdefault(store["manager"], []).append(store)
    managers: list[dict[str, Any]] = []
    for manager in sorted(grouped):
        managers.append({"name": manager, "stores": sorted(grouped[manager], key=_store_sort_key)})
    return {"month": month, "store_count": len(stores), "managers": managers}
