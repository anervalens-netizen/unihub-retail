"""Read-only overview and reconciliation for the isolated Grile V2 pilot."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from repositories.grile import GrileRepository
from services.grile import DEFAULT_TOLERANCE
from services.grile_sheets import build_services, close_services


PILOT_V2_MONTH = "2026-08"
PILOT_V2_READ_TIMEOUT_SECONDS = 35.0
PILOT_V2_RANGES = (
    "'Rezumat & Program'!H2",
    "'Rezumat & Program'!A10",
    "'Rezumat & Program'!J10",
    "'Rezumat & Program'!F10",
    "'Rezumat & Program'!O10",
)


@dataclass(frozen=True)
class PilotV2Sheet:
    site_code: str
    sheet_id: str


PILOT_V2_SHEETS = (
    PilotV2Sheet("PROMEN", "1jcVCLHaujv0O2qlTPXG7b1IqGGVq8572p7pJFvEAgdg"),  # pragma: allowlist secret
    PilotV2Sheet("MCRFBAL", "1MusUrpTjkFyW2JefvJVdFOdx5ypUbKr1Hs-2SViihEo"),  # pragma: allowlist secret
    PilotV2Sheet("CRFFEER", "1bEWiDcg9tqWPeqQdw6hna_lsIIc16ozKMCutkVIAHu0"),  # pragma: allowlist secret
    PilotV2Sheet("ORAUCHAN", "1ZxugdHXXhvPSFyxyOh9bipq11J2N872n7isAxRXMxuM"),  # pragma: allowlist secret
    PilotV2Sheet("ORAUCH", "12ejRCcDRNdQqiz38S7BjTKNb-pSrJWW2UNclhFJUiCI"),  # pragma: allowlist secret
)


@dataclass(frozen=True)
class PilotV2Reading:
    target: Decimal | None
    realized: Decimal | None
    forecast: Decimal | None
    error: str | None = None


def _range_number(value_range: dict[str, Any]) -> Decimal | None:
    values = value_range.get("values")
    if not isinstance(values, list) or not values or not isinstance(values[0], list) or not values[0]:
        return None
    value = values[0][0]
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _fetch_sheet(sheet: PilotV2Sheet) -> tuple[str, PilotV2Reading]:
    sheets_service = drive_service = None
    try:
        sheets_service, drive_service = build_services()
        response = (
            sheets_service.spreadsheets()
            .values()
            .batchGet(
                spreadsheetId=sheet.sheet_id,
                ranges=list(PILOT_V2_RANGES),
                valueRenderOption="UNFORMATTED_VALUE",
            )
            .execute()
        )
        value_ranges = response.get("valueRanges", [])
        if len(value_ranges) != len(PILOT_V2_RANGES):
            return sheet.site_code, PilotV2Reading(None, None, None, "Structură V2 incompletă")
        target, sales_one, sales_two, forecast_one, forecast_two = map(
            _range_number,
            value_ranges,
        )
        realized = sales_one + sales_two if sales_one is not None and sales_two is not None else None
        forecast = (
            forecast_one + forecast_two
            if forecast_one is not None and forecast_two is not None
            else None
        )
        if target is None or realized is None or forecast is None:
            return sheet.site_code, PilotV2Reading(target, realized, forecast, "Valori V2 incomplete")
        return sheet.site_code, PilotV2Reading(target, realized, forecast)
    except Exception:
        return sheet.site_code, PilotV2Reading(None, None, None, "Grila Google nu poate fi citită")
    finally:
        close_services(sheets_service, drive_service)


async def read_pilot_v2_sheets() -> dict[str, PilotV2Reading]:
    tasks = [asyncio.to_thread(_fetch_sheet, sheet) for sheet in PILOT_V2_SHEETS]
    try:
        readings = await asyncio.wait_for(
            asyncio.gather(*tasks),
            timeout=PILOT_V2_READ_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return {
            sheet.site_code: PilotV2Reading(None, None, None, "Citirea Google a expirat")
            for sheet in PILOT_V2_SHEETS
        }
    return dict(readings)


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
        read_pilot_v2_sheets(),
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
