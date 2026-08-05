"""Client Google read-only pentru grilele salariale (Google Sheets).

Citeste K5/L5 (target/realizat la nivel de magazin) + coloanele zilnice
pentru % completare + Drive modifiedTime, intr-un numar minim de apeluri
(1 batchGet Sheets + 1 Drive get per magazin).

IMPORTANT: scope-uri READ-ONLY. Chiar daca service account-ul are Editor
in Google, codul retail nu are capabilitate de scriere asupra grilelor.
Regulile de analiza sunt portate din grile-salarii (monitor_grile.py /
target_check.py) ca sursa de reguli, nu ca runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from business_clock import business_now

# Scope-uri minime, read-only (vezi docs/grile-integration-plan.md)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

# Range-uri citite intr-un singur batchGet per spreadsheet (UNFORMATTED).
# Index-ul conteaza pentru analyze().
GRILA_RANGES = [
    "Grila!K5",        # 0: target magazin (K5)
    "Grila!L5",        # 1: realizat magazin (L5)
    "Grila!P5:P35",    # 2: vanzari zilnice Agent 1 (31 zile)
    "Grila!U5:U35",    # 3: vanzari zilnice Agent 2
    "Grila!B32:G46",   # 4: sectiunea Suplimentar (15 randuri; D=data, E=target, F=realizat)
]
GRILA_RANGES_V3 = [
    "Grila!K5",        # 0: target magazin
    "Grila!L5",        # 1: realizat magazin
    "Grila!P5:P35",    # 2: vanzari zilnice Agent 1
    "Grila!U5:U35",    # 3: vanzari zilnice Agent 2
    "Grila!Z5:Z35",    # 4: vanzari zilnice Agent 3
    "Grila!B46:G60",   # 5: sectiunea Suplimentar mutata in schema v3
]


class GrileStructureError(ValueError):
    """Google batchGet response does not match the active v3 Grile template."""


def validate_grila_v3_response(value_ranges: list[dict[str, Any]]) -> None:
    """Fail closed before analysis when the v3 response lost a range or its shape."""
    if len(value_ranges) != len(GRILA_RANGES_V3):
        raise GrileStructureError(
            f"Grila v3 expected {len(GRILA_RANGES_V3)} ranges, received {len(value_ranges)}"
        )
    limits = ((1, 1), (1, 1), (31, 1), (31, 1), (31, 1), (15, 6))
    for index, (entry, expected_range, (max_rows, max_columns)) in enumerate(
        zip(value_ranges, GRILA_RANGES_V3, limits, strict=True)
    ):
        if not isinstance(entry, dict) or entry.get("range") != expected_range:
            raise GrileStructureError(
                f"Grila v3 range {index} must be {expected_range!r} in canonical order"
            )
        values = entry.get("values", [])
        if not isinstance(values, list) or len(values) > max_rows:
            raise GrileStructureError(f"Grila v3 range {expected_range!r} has invalid row cardinality")
        if any(not isinstance(row, list) or len(row) > max_columns for row in values):
            raise GrileStructureError(f"Grila v3 range {expected_range!r} has invalid row shape")


def _sa_file() -> str:
    return os.getenv(
        "GRILE_GOOGLE_SA_FILE",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "google", "service-account.json"),
    )


def get_credentials() -> Any:
    from google.oauth2.service_account import Credentials

    path = _sa_file()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Service account Google lipsa: {path}. "
            "Pune fisierul (chmod 600) sau seteaza GRILE_GOOGLE_SA_FILE."
        )
    return Credentials.from_service_account_file(path, scopes=SCOPES)


def build_services() -> tuple[Any, Any]:
    """Returneaza (sheets_service, drive_service). Sincron — a se rula in to_thread."""
    from googleapiclient.discovery import build

    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return sheets, drive


def close_services(*services: Any) -> None:
    """Close Google transports once the owning check has finished."""
    closed: set[int] = set()
    for service in services:
        if service is None:
            continue
        close_target = service
        close = getattr(close_target, "close", None)
        if not callable(close):
            close_target = getattr(service, "_http", None)
            close = getattr(close_target, "close", None)
        if not callable(close) or id(close_target) in closed:
            continue
        closed.add(id(close_target))
        close()


# ---------- helpers de parsare (portate din monitor/target_check) ----------

def _to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.startswith("#"):  # eroare formula (#REF!, #DIV/0! ...)
        return None
    text = text.replace(" ", "").replace("%", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _cell(values: list, r: int, c: int = 0) -> Any:
    try:
        v = values[r][c]
        return v if v != "" else None
    except (IndexError, TypeError):
        return None


def _parse_day(value: Any) -> int | None:
    """Extrage ziua (1..31) dintr-un cell Data (string sau serial Google)."""
    import re

    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2})(?:[./-]\d{1,2}(?:[./-]\d{2,4})?)?$", s)
    if m:
        d = int(m.group(1))
        return d if 1 <= d <= 31 else None
    try:
        f = float(s)
        if f > 30000:  # serial Google (epoch 1899-12-30)
            return (datetime(1899, 12, 30) + timedelta(days=f)).day
    except (ValueError, TypeError):
        pass
    return None


@dataclass(frozen=True)
class GrilaReading:
    grila_target: float | None
    grila_sales: float | None
    completion_pct: float | None
    missing_days: list[int]
    days_elapsed: int


def analyze_grila(
    value_ranges: list[dict[str, Any]],
    *,
    as_of: datetime | None = None,
    template_version: str = "v2",
) -> GrilaReading:
    """Extrage target/realizat (K5/L5) + % completare + zilele lipsa dintr-un batchGet.

    Model completare ("acoperire zi", portat din monitor_grile.py): o zi e
    acoperita daca P[zi] sau U[zi] are valoare, sau ziua apare in sectiunea
    Suplimentar (D32:D46). % = zile acoperite / zilele complete din luna curenta.
    Ziua curenta nu se cere, pentru ca grilele se completeaza abia seara dupa program.
    """
    if template_version == "v3":
        validate_grila_v3_response(value_ranges)
    vals = [vr.get("values", []) for vr in value_ranges]
    grila_target = _to_number(_cell(vals[0], 0, 0)) if len(vals) > 0 else None
    grila_sales = _to_number(_cell(vals[1], 0, 0)) if len(vals) > 1 else None

    daily_ranges = vals[2:-1] if len(vals) >= 5 else []

    days_from_supl: set[int] = set()
    if len(vals) >= 5:
        supplemental = vals[-1]
        for i in range(15):
            d = _parse_day(_cell(supplemental, i, 2))  # col D = data
            if d:
                days_from_supl.add(d)

    today = as_of or business_now()
    days_elapsed = max(today.day - 1, 0)
    covered = 0
    missing_days: list[int] = []
    for d in range(1, days_elapsed + 1):
        idx = d - 1
        has_daily = any(
            _to_number(_cell(daily, idx, 0)) is not None
            for daily in daily_ranges
        )
        if has_daily or d in days_from_supl:
            covered += 1
        else:
            missing_days.append(d)
    completion_pct = round(covered / days_elapsed * 100, 1) if days_elapsed > 0 else None

    return GrilaReading(
        grila_target=grila_target,
        grila_sales=grila_sales,
        completion_pct=completion_pct,
        missing_days=missing_days,
        days_elapsed=days_elapsed,
    )


def fetch_grila(
    sheets_svc: Any,
    sheet_id: str,
    template_version: str = "v2",
) -> list[dict[str, Any]]:
    """Un batchGet UNFORMATTED per spreadsheet (sincron)."""
    value_ranges = sheets_svc.spreadsheets().values().batchGet(
        spreadsheetId=sheet_id,
        ranges=GRILA_RANGES_V3 if template_version == "v3" else GRILA_RANGES,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute().get("valueRanges", [])
    if template_version == "v3":
        validate_grila_v3_response(value_ranges)
    return value_ranges


def fetch_mod_time(drive_svc: Any, sheet_id: str) -> str | None:
    meta = drive_svc.files().get(fileId=sheet_id, fields="modifiedTime").execute()
    return meta.get("modifiedTime")
