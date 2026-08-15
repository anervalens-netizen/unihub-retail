"""Pure value types and template constants for monthly Grile operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from services.grile_monthly_integrity import MonthlyIntegrityError


RO_MONTHS = [
    "",
    "Ianuarie",
    "Februarie",
    "Martie",
    "Aprilie",
    "Mai",
    "Iunie",
    "Iulie",
    "August",
    "Septembrie",
    "Octombrie",
    "Noiembrie",
    "Decembrie",
]

RESET_RANGES = [
    "Grila!D8",
    "Grila!D22",
    "Grila!P5:P36",
    "Grila!Q5:S36",
    "Grila!U5:U36",
    "Grila!V5:X36",
    "Grila!B32:F46",
    "Grila!F12:F14",
    "Grila!F26:F28",
    "Pontaj!C8:AG31",
]
RESET_RANGES_V3 = [
    "Grila!D8",
    "Grila!D22",
    "Grila!D36",
    "Grila!P5:P50",
    "Grila!Q5:S50",
    "Grila!U5:U50",
    "Grila!V5:X50",
    "Grila!Z5:Z50",
    "Grila!AA5:AC50",
    "Grila!B46:F60",
    "Grila!F12:F14",
    "Grila!F26:F28",
    "Grila!F40:F42",
    "Pontaj!C8:AG31",
]
GRILA_CELLS = {
    1: {
        "agent": "D2",
        "base_salary": "D3",
        "sales_commission_cells": ["G8", "G9", "G12", "G13", "G14"],
        "bonuri": "D4",
        "extra_hours_pay": "G10",
        "extra_location_commission": "G11",
        "worked_hours": "Pontaj!AH8",
    },
    2: {
        "agent": "D16",
        "base_salary": "D17",
        "sales_commission_cells": ["G22", "G23", "G26", "G27", "G28"],
        "bonuri": "D18",
        "extra_hours_pay": "G24",
        "extra_location_commission": "G25",
        "worked_hours": "Pontaj!AH11",
    },
}
GRILA_CELLS_V3 = {
    **GRILA_CELLS,
    3: {
        "agent": "D30",
        "base_salary": "D31",
        "sales_commission_cells": ["G36", "G37", "G40", "G41", "G42"],
        "bonuri": "D32",
        "extra_hours_pay": "G38",
        "extra_location_commission": "G39",
        "worked_hours": "Pontaj!AH14",
    },
}

HEADERS = [
    "Nr",
    "Manager",
    "Magazin",
    "Agent",
    "Salariu baza",
    "Comision vanzare",
    "Flip",
    "Comision vanzare zile suplimentare",
    "Incentive lunar",
    "Plata ore suplimentare",
    "Total salariu",
    "Salariu Cash",
    "Bonuri",
    "Data angajarii",
    "Data plecarii",
    "Nr. Ore lucrate",
    "Zile CO luna in curs",
]
AUDIT_HEADERS = [
    "Company",
    "Store",
    "Slot",
    "Agent",
    "Sheet ID",
    "Comision vanzare",
    "Comision supl",
    "Plata ore supl",
    "Bonuri",
    "Ore lucrate",
    "Source",
    "Status",
    "Error",
]


@dataclass(frozen=True)
class StoreEntry:
    company: str
    store: str
    sheet_id: str
    site_code: str
    manager: str
    is_closed: bool = False
    template_version: str = "v2"


@dataclass
class ExtractedAgentRow:
    company: str
    store: str
    slot: int
    agent: Any
    base_salary: Any
    sales_commission: Any
    extra_location_commission: Any
    extra_hours_pay: Any
    bonuri: Any
    worked_hours: Any
    status: str
    error: str
    sheet_id: str
    site_code: str = ""
    error_code: str = ""


@dataclass(frozen=True)
class MonthlyExecution:
    path: Path
    manifest: dict[str, Any]
    rollback: Callable[[], Awaitable[dict[str, Any]]] | None = None


class MonthlyManifestError(MonthlyIntegrityError):
    def __init__(self, code: str, message: str, manifest: dict[str, Any]):
        super().__init__(code, message)
        self.manifest = manifest


def cells_for_entry(entry: StoreEntry) -> dict[int, dict[str, Any]]:
    return GRILA_CELLS_V3 if entry.template_version == "v3" else GRILA_CELLS


def reset_ranges_for_entry(entry: StoreEntry) -> list[str]:
    return list(RESET_RANGES_V3 if entry.template_version == "v3" else RESET_RANGES)


def ro_month_label(ym: str) -> str:
    """Convert ``2026-05`` to the Romanian label ``Mai 2026``."""
    year, month = ym.split("-")
    return f"{RO_MONTHS[int(month)]} {year}"


def next_ym(ym: str) -> str:
    year, month = (int(value) for value in ym.split("-"))
    month += 1
    if month > 12:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}"
