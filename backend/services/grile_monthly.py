"""Operatii lunare native pentru grile in UniHub Retail.

Inlocuieste proxy-ul catre aplicatia veche `grile-salarii`: Retail citeste
registrul din DB (`grile_sheets` + `stores`), genereaza Excelul final, arhiva
XLSX/ZIP si ruleaza resetul controlat direct cu Google APIs.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import asyncpg
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

RO_MONTHS = [
    "", "Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie",
    "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie",
]

VALID_OPS = {"finalize", "archive", "reset"}
VALID_DOWNLOADS = {"final": "final", "archive": "archive"}
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = Path(os.getenv("GRILE_OUTPUTS_DIR", BASE_DIR / "outputs" / "grile"))
FINAL_EXPORT_NAME_PREFIX = "Tabel Salarii -"
ARCHIVE_DIR_NAME = "archive"
RESET_RANGES = [
    "Grila!D8",
    "Grila!D22",
    "Grila!P5:P36",
    "Grila!Q5:S36",
    "Grila!U5:U36",
    "Grila!V5:X36",
    "Grila!B32:F37",
    "Grila!F12:F14",
    "Grila!F26:F28",
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
_TRANSIENT = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class StoreEntry:
    company: str
    store: str
    sheet_id: str
    site_code: str
    manager: str


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


def ro_month_label(ym: str) -> str:
    """`2026-05` -> `Mai 2026`."""
    year, month = ym.split("-")
    return f"{RO_MONTHS[int(month)]} {year}"


def next_ym(ym: str) -> str:
    year, month = (int(x) for x in ym.split("-"))
    month += 1
    if month > 12:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}"


def _sa_file() -> Path:
    return Path(
        os.getenv(
            "GRILE_GOOGLE_SA_FILE",
            BASE_DIR / "config" / "google" / "service-account.json",
        )
    )


def get_credentials() -> Any:
    from google.oauth2.service_account import Credentials

    path = _sa_file()
    if not path.exists():
        raise FileNotFoundError(
            f"Service account Google lipsa: {path}. Pune fisierul sau seteaza GRILE_GOOGLE_SA_FILE."
        )
    return Credentials.from_service_account_file(str(path), scopes=SCOPES)


def build_google_services() -> tuple[Any, Any]:
    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return sheets, drive


def safe_filename(value: str) -> str:
    import re

    cleaned = value.replace("/", " - ").replace("\\", " - ")
    cleaned = re.sub(r'[<>:"|?*]', "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.rstrip(". ") or "untitled"


def month_slug(month: str) -> str:
    import re

    slug = re.sub(r"[^0-9A-Za-zĂÂÎȘȚăâîșț]+", "-", month.strip())
    return slug.strip("-")


def build_final_export_path(outputs_dir: Path, month: str) -> Path:
    return outputs_dir / f"{FINAL_EXPORT_NAME_PREFIX} {month}.xlsx"


def build_archive_dir(outputs_dir: Path, month: str) -> Path:
    return outputs_dir / ARCHIVE_DIR_NAME / month


def build_archive_manifest_path(outputs_dir: Path, month: str) -> Path:
    return build_archive_dir(outputs_dir, month) / f"archive-manifest-{month_slug(month)}.json"


def build_archive_zip_path(outputs_dir: Path, month: str) -> Path:
    return build_archive_dir(outputs_dir, month) / f"Grile - {month}.zip"


def build_reset_report_path(outputs_dir: Path, next_month: str) -> Path:
    return outputs_dir / f"reset-report-{month_slug(next_month)}.json"


def build_store_export_path(outputs_dir: Path, month: str, entry: StoreEntry) -> Path:
    return build_archive_dir(outputs_dir, month) / safe_filename(entry.company) / f"{safe_filename(entry.store)}.xlsx"


def build_manager_zip_path(outputs_dir: Path, month: str, manager: str) -> Path:
    return build_archive_dir(outputs_dir, month) / "ASM" / f"Grile - {month} - {safe_filename(manager)}.zip"


def resolve_output_path(month: str, only: str | None, output_dir: Path) -> Path:
    output_path = build_final_export_path(output_dir, month)
    if only:
        output_path = output_path.with_name(
            f"{output_path.stem} - TEST {safe_filename(only)}{output_path.suffix}"
        )
    return output_path


def _is_transient(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status in _TRANSIENT


def retry_api(fn, *, label: str, attempts: int = 4, base_delay: float = 1.0):
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < attempts - 1 and _is_transient(exc):
                time.sleep(base_delay * (2**attempt))
                continue
            raise RuntimeError(f"{label}: {exc}") from exc
    assert last is not None
    raise last


def _company_from_values(registry_key: str | None, fallback: str | None) -> str:
    raw = (registry_key or "").split("/", 1)[0].strip() or (fallback or "").strip()
    if raw.casefold() == "mobicell":
        return "Mobicell"
    return "Mobiup"


def _store_from_values(registry_key: str | None, fallback: str | None) -> str:
    if registry_key and "/" in registry_key:
        return registry_key.split("/", 1)[1].strip()
    return (fallback or "").strip()


async def load_entries(pool: asyncpg.Pool, only: str | None = None) -> list[StoreEntry]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                gs.site_code,
                gs.sheet_id,
                gs.registry_key,
                s.locatie,
                s.firma,
                s.asm
            FROM grile_sheets gs
            JOIN stores s ON s.site_code = gs.site_code
            WHERE gs.is_active = true
            ORDER BY COALESCE(gs.registry_key, s.firma || '/' || s.locatie)
            """
        )

    entries = [
        StoreEntry(
            company=_company_from_values(r["registry_key"], r["firma"]),
            store=_store_from_values(r["registry_key"], r["locatie"]),
            sheet_id=r["sheet_id"],
            site_code=r["site_code"],
            manager=(r["asm"] or "Neatribuit").strip() or "Neatribuit",
        )
        for r in rows
    ]
    if only:
        needle = only.casefold()
        entries = [
            e for e in entries
            if needle in f"{e.company}/{e.store}/{e.site_code}/{e.manager}".casefold()
        ]
    if not entries:
        raise RuntimeError("No active grile matched the requested filter.")
    return entries


def validate_archive_manifest(manifest: dict[str, Any], expected_count: int) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if manifest.get("registry_count") != expected_count:
        errors.append(f"registry_count mismatch: {manifest.get('registry_count')} != {expected_count}")
    if manifest.get("exported_count") != expected_count:
        errors.append(f"exported_count mismatch: {manifest.get('exported_count')} != {expected_count}")
    if manifest.get("error_count") != 0:
        errors.append(f"archive has {manifest.get('error_count')} export errors")

    stores = manifest.get("stores")
    if not isinstance(stores, list) or len(stores) != expected_count:
        count = len(stores) if isinstance(stores, list) else "invalid"
        errors.append(f"stores count mismatch: {count} != {expected_count}")
    else:
        for store in stores:
            company = store.get("company", "?")
            name = store.get("store", "?")
            if store.get("status") != "OK":
                errors.append(f"{company}/{name} status is {store.get('status')}")
            xlsx_path = Path(str(store.get("xlsx_path", "")))
            if not xlsx_path.exists() or xlsx_path.stat().st_size == 0:
                errors.append(f"missing or empty export: {xlsx_path}")

    zip_path = Path(str(manifest.get("zip_path", "")))
    if not zip_path.exists() or zip_path.stat().st_size == 0:
        errors.append(f"missing or empty archive zip: {zip_path}")
    return not errors, errors


def scalar(values: list[list[Any]]) -> Any:
    if not values or not values[0]:
        return ""
    return values[0][0]


def to_number(value: Any) -> float:
    if value in ("", None):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "")
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def sum_scalars(value_ranges: list[dict[str, Any]]) -> float:
    return sum(to_number(scalar(vr.get("values", []))) for vr in value_ranges)


def extract_store_rows(sheets_svc: Any, entry: StoreEntry) -> list[ExtractedAgentRow]:
    def read_values() -> list[dict[str, Any]]:
        ranges = []
        for slot in (1, 2):
            cells = GRILA_CELLS[slot]
            ranges += [
                f"Grila!{cells['agent']}",
                f"Grila!{cells['base_salary']}",
                *[f"Grila!{cell}" for cell in cells["sales_commission_cells"]],
                f"Grila!{cells['extra_location_commission']}",
                f"Grila!{cells['extra_hours_pay']}",
                f"Grila!{cells['bonuri']}",
                cells["worked_hours"],
            ]
        return sheets_svc.spreadsheets().values().batchGet(
            spreadsheetId=entry.sheet_id,
            ranges=ranges,
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()["valueRanges"]

    try:
        value_ranges = retry_api(
            read_values,
            label=f"read {entry.company}/{entry.store}",
            attempts=6,
            base_delay=3.0,
        )
        rows: list[ExtractedAgentRow] = []
        idx = 0
        for slot in (1, 2):
            agent = scalar(value_ranges[idx].get("values", []))
            idx += 1
            base_salary = scalar(value_ranges[idx].get("values", []))
            idx += 1
            sales_commission = sum_scalars(value_ranges[idx : idx + 5])
            idx += 5
            commission = scalar(value_ranges[idx].get("values", []))
            idx += 1
            extra_hours = scalar(value_ranges[idx].get("values", []))
            idx += 1
            bonuri = scalar(value_ranges[idx].get("values", []))
            idx += 1
            worked_hours = scalar(value_ranges[idx].get("values", []))
            idx += 1
            if not agent:
                continue
            rows.append(
                ExtractedAgentRow(
                    company=entry.company,
                    store=entry.store,
                    slot=slot,
                    agent=agent,
                    base_salary=base_salary,
                    sales_commission=sales_commission,
                    extra_location_commission=commission,
                    extra_hours_pay=extra_hours,
                    bonuri=bonuri,
                    worked_hours=worked_hours,
                    status="OK",
                    error="",
                    sheet_id=entry.sheet_id,
                )
            )
        return rows
    except Exception as exc:  # noqa: BLE001
        return [
            ExtractedAgentRow(
                company=entry.company,
                store=entry.store,
                slot=0,
                agent="",
                base_salary="",
                sales_commission="",
                extra_location_commission="",
                extra_hours_pay="",
                bonuri="",
                worked_hours="",
                status="ERROR",
                error=str(exc),
                sheet_id=entry.sheet_id,
            )
        ]


def make_output_row(row: ExtractedAgentRow, nr: int, metadata: dict[str, Any]) -> list[Any]:
    excel_row = nr + 1
    return [
        nr,
        metadata.get("Manager", ""),
        row.store,
        row.agent,
        row.base_salary,
        row.sales_commission,
        metadata.get("Flip", ""),
        row.extra_location_commission,
        metadata.get("Incentive lunar", ""),
        row.extra_hours_pay,
        f"=SUM(E{excel_row}:J{excel_row},M{excel_row})",
        f"=K{excel_row}-M{excel_row}",
        row.bonuri,
        metadata.get("Data angajarii", ""),
        metadata.get("Data plecarii", ""),
        row.worked_hours,
        metadata.get("Zile CO luna in curs", ""),
    ]


def style_sheet(ws) -> None:
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    widths = {
        "A": 8,
        "B": 22,
        "C": 30,
        "D": 30,
        "E": 14,
        "F": 14,
        "G": 14,
        "H": 26,
        "I": 16,
        "J": 18,
        "K": 14,
        "L": 14,
        "M": 14,
        "N": 16,
        "O": 16,
        "P": 16,
        "Q": 16,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width


def build_workbook(
    rows: list[ExtractedAgentRow],
    output_path: Path,
    metadata_by_company_store: dict[tuple[str, str], dict[str, Any]],
) -> None:
    wb = Workbook()
    wb.active.title = "Mobiup"
    wb.create_sheet("Mobicell")
    ws_audit = wb.create_sheet("Audit")

    for ws in (wb["Mobiup"], wb["Mobicell"]):
        ws.append(HEADERS)

    counters = {"Mobiup": 1, "Mobicell": 1}
    for row in rows:
        if row.status != "OK":
            continue
        ws = wb[row.company]
        metadata = metadata_by_company_store.get((row.company, row.store), {})
        ws.append(make_output_row(row, counters[row.company], metadata))
        counters[row.company] += 1

    ws_audit.append(AUDIT_HEADERS)
    for row in rows:
        ws_audit.append(
            [
                row.company,
                row.store,
                row.slot,
                row.agent,
                row.sheet_id,
                row.sales_commission,
                row.extra_location_commission,
                row.extra_hours_pay,
                row.bonuri,
                row.worked_hours,
                f"https://docs.google.com/spreadsheets/d/{row.sheet_id}",
                row.status,
                row.error,
            ]
        )

    for ws in wb.worksheets:
        style_sheet(ws)
        for row_cells in ws.iter_rows():
            for cell in row_cells:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        for col_idx in range(1, ws.max_column + 1):
            col = get_column_letter(col_idx)
            if ws.column_dimensions[col].width is None:
                ws.column_dimensions[col].width = 14

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)


async def finalize_month(pool: asyncpg.Pool, month: str, only: str | None = None, delay: float = 1.1) -> Path:
    entries = await load_entries(pool, only=only)
    metadata = {(e.company, e.store): {"Manager": e.manager} for e in entries}
    sheets_svc, _ = build_google_services()
    all_rows: list[ExtractedAgentRow] = []
    for idx, entry in enumerate(entries, start=1):
        print(f"[{idx:02d}/{len(entries):02d}] Read {entry.company}/{entry.store}", flush=True)
        all_rows.extend(extract_store_rows(sheets_svc, entry))
        if delay > 0 and idx < len(entries):
            time.sleep(delay)

    output_path = resolve_output_path(month, only, OUTPUTS_DIR)
    build_workbook(all_rows, output_path, metadata)

    errors = [row for row in all_rows if row.status != "OK"]
    print(f"Generated: {output_path}")
    print(f"Rows: {sum(1 for row in all_rows if row.status == 'OK')} OK, {len(errors)} errors")
    if errors:
        print("Errors are listed in the Audit sheet.")
    return output_path


def export_sheet_xlsx(drive_service: Any, entry: StoreEntry, output_path: Path) -> dict[str, Any]:
    result = {
        "company": entry.company,
        "store": entry.store,
        "site_code": entry.site_code,
        "manager": entry.manager,
        "sheet_id": entry.sheet_id,
        "status": "OK",
        "xlsx_path": str(output_path),
        "bytes": 0,
        "error": "",
    }
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = drive_service.files().export_media(fileId=entry.sheet_id, mimeType=XLSX_MIME)
        with output_path.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        result["bytes"] = output_path.stat().st_size
        if result["bytes"] == 0:
            result["status"] = "ERROR"
            result["error"] = "exported file is empty"
        return result
    except Exception as exc:  # noqa: BLE001
        result["status"] = "ERROR"
        result["error"] = str(exc)
        result["xlsx_path"] = ""
        return result


def create_archive_zip(zip_path: Path, exported_files: list[Path], archive_dir: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in exported_files:
            zf.write(path, path.relative_to(archive_dir).as_posix())


def create_manager_zips(output_dir: Path, month: str, results: list[dict[str, Any]]) -> dict[str, Path]:
    archive_dir = build_archive_dir(output_dir, month)
    files_by_manager: dict[str, list[Path]] = {}
    for item in results:
        if item.get("status") != "OK":
            continue
        files_by_manager.setdefault(item.get("manager") or "Neatribuit", []).append(Path(item["xlsx_path"]))

    zip_paths: dict[str, Path] = {}
    for manager, files in sorted(files_by_manager.items()):
        zip_path = build_manager_zip_path(output_dir, month, manager)
        create_archive_zip(zip_path, files, archive_dir)
        zip_paths[manager] = zip_path
    return zip_paths


def summarize_archive_results(
    month: str,
    registry_count: int,
    results: list[dict[str, Any]],
    zip_path: Path,
    manager_zip_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    return {
        "month": month,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "registry_count": registry_count,
        "exported_count": sum(1 for item in results if item.get("status") == "OK"),
        "error_count": sum(1 for item in results if item.get("status") != "OK"),
        "zip_path": str(zip_path),
        "manager_zip_paths": {manager: str(path) for manager, path in sorted((manager_zip_paths or {}).items())},
        "stores": results,
    }


async def archive_month(pool: asyncpg.Pool, month: str, only: str | None = None, delay: float = 0.5) -> Path:
    entries = await load_entries(pool, only=only)
    _, drive_service = build_google_services()
    results: list[dict[str, Any]] = []
    exported_files: list[Path] = []
    for idx, entry in enumerate(entries, start=1):
        print(f"[{idx:02d}/{len(entries):02d}] Export {entry.company}/{entry.store}", flush=True)
        output_path = build_store_export_path(OUTPUTS_DIR, month, entry)
        result = retry_api(
            lambda entry=entry, output_path=output_path: export_sheet_xlsx(drive_service, entry, output_path),
            label=f"export {entry.company}/{entry.store}",
            attempts=6,
            base_delay=3.0,
        )
        results.append(result)
        if result["status"] == "OK":
            exported_files.append(Path(result["xlsx_path"]))
        if delay > 0 and idx < len(entries):
            time.sleep(delay)

    zip_path = build_archive_zip_path(OUTPUTS_DIR, month)
    manager_zip_paths: dict[str, Path] = {}
    if len(exported_files) == len(entries):
        create_archive_zip(zip_path, exported_files, build_archive_dir(OUTPUTS_DIR, month))
        manager_zip_paths = create_manager_zips(OUTPUTS_DIR, month, results)

    manifest = summarize_archive_results(month, len(entries), results, zip_path, manager_zip_paths)
    manifest_path = build_archive_manifest_path(OUTPUTS_DIR, month)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    ok, errors = validate_archive_manifest(manifest, expected_count=len(entries))
    print(f"Archive manifest: {manifest_path}")
    print(f"Exports: {manifest['exported_count']}/{manifest['registry_count']}, errors: {manifest['error_count']}")
    if manager_zip_paths:
        print(f"ASM zips: {len(manager_zip_paths)}")
        for manager, path in sorted(manager_zip_paths.items()):
            print(f"  {manager}: {path}")
    if not ok:
        for error in errors:
            print(f"ERROR: {error}")
        raise RuntimeError("Archive is incomplete")
    return manifest_path


def assert_final_export_exists(final_export: Path, force: bool) -> None:
    if final_export.exists() or force:
        return
    raise RuntimeError(f"Final export does not exist: {final_export}. Ruleaza intai Finalizare salarii.")


def assert_archive_complete(output_dir: Path, closing_month: str, expected_count: int, force: bool) -> None:
    if force:
        return
    manifest_path = build_archive_manifest_path(output_dir, closing_month)
    if not manifest_path.exists():
        raise RuntimeError(f"Archive manifest does not exist: {manifest_path}. Ruleaza intai Exporta arhiva.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ok, errors = validate_archive_manifest(manifest, expected_count=expected_count)
    if not ok:
        detail = "\n".join(f"- {error}" for error in errors)
        raise RuntimeError(f"Archive is incomplete for {closing_month}:\n{detail}")


def reset_store(sheets_svc: Any | None, entry: StoreEntry, *, dry_run: bool) -> dict[str, Any]:
    result = {
        "company": entry.company,
        "store": entry.store,
        "site_code": entry.site_code,
        "sheet_id": entry.sheet_id,
        "status": "DRY_RUN" if dry_run else "OK",
        "error": "",
        "ranges": list(RESET_RANGES),
    }
    if dry_run:
        return result

    assert sheets_svc is not None
    try:
        def clear() -> dict[str, Any]:
            return sheets_svc.spreadsheets().values().batchClear(
                spreadsheetId=entry.sheet_id,
                body={"ranges": list(RESET_RANGES)},
            ).execute()

        retry_api(clear, label=f"reset {entry.company}/{entry.store}", attempts=6, base_delay=3.0)
        return result
    except Exception as exc:  # noqa: BLE001
        result["status"] = "ERROR"
        result["error"] = str(exc)
        return result


async def reset_month(
    pool: asyncpg.Pool,
    closing_month: str,
    next_month: str,
    only: str | None = None,
    dry_run: bool = True,
    force: bool = False,
) -> Path:
    entries = await load_entries(pool, only=only)
    final_export = build_final_export_path(OUTPUTS_DIR, closing_month)
    assert_final_export_exists(final_export, force=force)
    assert_archive_complete(OUTPUTS_DIR, closing_month, expected_count=len(entries), force=force)

    sheets_svc = None
    if not dry_run:
        sheets_svc, _ = build_google_services()

    report: dict[str, Any] = {
        "closing_month": closing_month,
        "next_month": next_month,
        "dry_run": dry_run,
        "forced": force,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "stores": [],
    }
    for idx, entry in enumerate(entries, start=1):
        suffix = " (dry-run)" if dry_run else ""
        print(f"[{idx:02d}/{len(entries):02d}] Reset {entry.company}/{entry.store}{suffix}", flush=True)
        report["stores"].append(reset_store(sheets_svc, entry, dry_run=dry_run))

    report_path = build_reset_report_path(OUTPUTS_DIR, next_month)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    errors = [store for store in report["stores"] if store["status"] == "ERROR"]
    print(f"Reset report: {report_path}")
    print(f"Stores: {len(report['stores'])}, errors: {len(errors)}")
    if errors and not dry_run:
        raise RuntimeError(f"Reset finished with {len(errors)} errors")
    return report_path


async def run_monthly_op(
    *,
    op: str,
    month: str,
    only: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    if op not in VALID_OPS:
        raise ValueError(f"Operatie necunoscuta: {op}")

    from db.connection import get_pool

    month_label = ro_month_label(month)
    buffer = io.StringIO()
    status = "success"
    exit_code = 0

    async def _run() -> None:
        pool = await get_pool()
        if op == "finalize":
            await finalize_month(pool, month_label, only=only)
        elif op == "archive":
            await archive_month(pool, month_label, only=only)
        else:
            await reset_month(
                pool,
                closing_month=month_label,
                next_month=ro_month_label(next_ym(month)),
                only=only,
                dry_run=dry_run,
            )

    try:
        with contextlib.redirect_stdout(buffer):
            await _run()
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        exit_code = -1
        print(f"ERROR: {exc}", file=buffer)

    return {
        "op": op,
        "month_label": month_label,
        "status": status,
        "output": buffer.getvalue(),
        "exit_code": exit_code,
        "dry_run": dry_run if op == "reset" else None,
    }


async def fetch_download(kind: str, month: str) -> tuple[bytes, str, str]:
    if kind not in VALID_DOWNLOADS:
        raise ValueError(f"Tip download necunoscut: {kind}")
    month_label = ro_month_label(month)
    if kind == "final":
        path = build_final_export_path(OUTPUTS_DIR, month_label)
        filename = f"Tabel Salarii - {month_label}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        path = build_archive_zip_path(OUTPUTS_DIR, month_label)
        filename = f"Arhiva Grile - {month_label}.zip"
        media_type = "application/zip"

    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Fisierul {kind} pentru {month_label} nu exista inca.")
    return await asyncio.to_thread(path.read_bytes), filename, media_type
