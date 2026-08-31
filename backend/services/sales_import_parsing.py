from __future__ import annotations

from dataclasses import replace
from datetime import date
from hashlib import sha256
import math
from pathlib import Path
from typing import Any

import asyncpg
import pandas as pd
from prometheus_client import Gauge, Histogram

from business_clock import BusinessClock, business_today
from services.legacy_xls import limits_from_upload_policy
from services.spreadsheet_readers import read_spreadsheet_frame
from services.sales_generation import (
    SalesAnomalyClassification,
    SalesPolicyValidationError,
    make_sales_anomaly,
)
from services.spreadsheet_safety import (
    SALES_SPREADSHEET_LIMITS,
    SpreadsheetParserMeasurement,
    SpreadsheetUploadError,
    SpreadsheetUploadStats,
    validate_spreadsheet_upload,
)

SALES_COLUMNS = [
    "Data", "SiteCode", "ItemCode", "ItemName", "Cantitate", "Brand",
    "Pret", "Valoare", "Locatie", "Firma", "ASM", "Regional", "Nr",
    "Categorie", "SubCategorie", "Agent",
]
IMPORT_COMPRESSED_BYTES = Gauge(
    "sales_import_compressed_bytes",
    "Source bytes parsed by the sales import loader.",
)
IMPORT_EXPANDED_BYTES = Gauge(
    "sales_import_expanded_bytes",
    "Actual uncompressed XLSX entry bytes accepted by the sales import loader.",
)
IMPORT_DATAFRAME_BYTES = Gauge(
    "sales_import_dataframe_bytes",
    "In-memory DataFrame bytes produced by the sales import loader.",
)
IMPORT_ROWS = Gauge("sales_import_rows", "Rows produced by the sales import loader.")
IMPORT_PARSE_SECONDS = Histogram(
    "sales_import_parse_seconds",
    "Sales workbook parse and validation duration.",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
IMPORT_PEAK_RSS_BYTES = Gauge(
    "sales_import_peak_rss_bytes",
    "Peak RSS observed by the sales import loader.",
)
SALES_IMPORT_SPREADSHEET_LIMITS = replace(
    SALES_SPREADSHEET_LIMITS,
    max_member_bytes=128 * 1024 * 1024,
)


def _raise_structural_contradiction(
    code: str,
    message: str,
    **details: Any,
) -> None:
    raise SalesPolicyValidationError(
        make_sales_anomaly(
            code,
            SalesAnomalyClassification.STRUCTURAL_CONTRADICTION,
            message,
            **details,
        )
    )


def _sales_source(
    source: str | Path | bytes,
    source_filename: str | None,
) -> tuple[bytes, str]:
    content = source if isinstance(source, bytes) else Path(source).read_bytes()
    source_name = source_filename or (
        str(source) if not isinstance(source, bytes) else ""
    )
    suffix = Path(source_name).suffix
    if not suffix:
        suffix = (
            ".xls"
            if content.startswith(bytes.fromhex("d0cf11e0a1b11ae1"))
            else ".xlsx"
        )
    return content, suffix


def _read_sales_sheet(
    content: bytes,
    suffix: str,
) -> tuple[pd.DataFrame, SpreadsheetUploadStats]:
    try:
        stats = validate_spreadsheet_upload(
            content,
            suffix,
            limits=SALES_IMPORT_SPREADSHEET_LIMITS,
        )
    except SpreadsheetUploadError as exc:
        _raise_structural_contradiction("invalid_workbook", str(exc))
        raise AssertionError("unreachable") from exc
    sheet = read_spreadsheet_frame(
        content,
        suffix=suffix,
        header=None,
        limits=limits_from_upload_policy(SALES_IMPORT_SPREADSHEET_LIMITS),
    )
    if sheet.empty:
        _raise_structural_contradiction(
            "empty_workbook",
            "Fișierul nu conține date.",
        )
    return sheet, stats


def _sales_columns(sheet: pd.DataFrame) -> list[str]:
    columns = [
        "" if pd.isna(value) else str(value).strip()
        for value in sheet.iloc[0].tolist()
    ]
    duplicates = sorted(
        {
            column
            for column in columns
            if column and columns.count(column) > 1
        }
    )
    if duplicates:
        _raise_structural_contradiction(
            "duplicate_headers",
            "Fișierul conține antete duplicate.",
            headers=duplicates,
        )
    missing = [column for column in SALES_COLUMNS if column not in columns]
    if missing:
        _raise_structural_contradiction(
            "missing_required_columns",
            f"Lipsesc coloane obligatorii: {', '.join(missing)}",
            columns=missing,
        )
    return columns


def _parse_sales_dates(frame: pd.DataFrame) -> None:
    try:
        frame["Data"] = pd.to_datetime(
            frame["Data"],
            format="%d.%m.%Y",
            errors="raise",
        ).dt.date
    except (TypeError, ValueError) as exc:
        try:
            _raise_structural_contradiction(
                "invalid_sale_date",
                "Coloana Data conține valori invalide.",
            )
        except SalesPolicyValidationError as validation_error:
            raise validation_error from exc


def _parse_sales_quantity(frame: pd.DataFrame) -> None:
    quantity = pd.to_numeric(frame["Cantitate"], errors="coerce")
    invalid = quantity.isna() | ~quantity.map(
        lambda value: math.isfinite(float(value))
    )
    fractional = ~quantity.map(
        lambda value: bool(pd.isna(value)) or float(value).is_integer()
    )
    if bool((invalid | fractional | (quantity.abs() > 2_147_483_647)).any()):
        _raise_structural_contradiction(
            "invalid_quantity",
            "Coloana Cantitate conține valori invalide.",
        )
    frame["Cantitate"] = quantity.astype("int64")


def _parse_sales_money(frame: pd.DataFrame) -> None:
    for column in ("Pret", "Valoare"):
        numeric = pd.to_numeric(frame[column], errors="coerce")
        invalid = numeric.isna() | ~numeric.map(
            lambda value: math.isfinite(float(value))
        )
        if bool((invalid | (numeric.abs() > 99_999_999.99)).any()):
            _raise_structural_contradiction(
                "invalid_money",
                f"Coloana {column} conține valori monetare invalide.",
                column=column,
            )
        frame[column] = numeric


def _normalize_sales_frame(frame: pd.DataFrame) -> None:
    frame["Nr"] = frame["Nr"].fillna("").map(
        lambda value: str(value).strip()
    )
    for column in (
        "SiteCode", "ItemCode", "ItemName", "Locatie",
        "Firma", "ASM", "Regional", "Agent",
    ):
        frame[column] = frame[column].fillna("").map(
            lambda value: str(value).strip()
        )
    frame["Firma"] = frame["Firma"].map(normalize_firma)
    for column in ("Brand", "Categorie", "SubCategorie"):
        frame[column] = frame[column].where(pd.notna(frame[column]), None)
        frame[column] = frame[column].map(
            lambda value: (
                str(value).strip() if isinstance(value, str) else value
            )
        )
    frame["is_cartela"] = frame["Categorie"].isna() | (
        frame["Categorie"].astype(str).str.strip() == ""
    )
    frame["is_return"] = frame["Cantitate"] < 0


def _load_sales_dataframe_impl(
    source: str | Path | bytes,
    *,
    source_filename: str | None = None,
) -> tuple[pd.DataFrame, SpreadsheetUploadStats]:
    content, suffix = _sales_source(source, source_filename)
    sheet, stats = _read_sales_sheet(content, suffix)
    frame = sheet.iloc[1:].copy().reset_index(drop=True)
    frame.columns = _sales_columns(sheet)
    frame = frame[SALES_COLUMNS].copy()
    _parse_sales_dates(frame)
    _parse_sales_quantity(frame)
    _parse_sales_money(frame)
    _normalize_sales_frame(frame)
    validate_sales_dataframe(frame)
    return frame, stats


def load_sales_dataframe(
    source: str | Path | bytes,
    *,
    source_filename: str | None = None,
) -> pd.DataFrame:
    """Parse one sales workbook in the import process after a SHA check.

    The web boundary performs a cheap untrusted-upload preflight.  This second
    validation is intentional: the worker re-establishes trust after reading
    the content-addressed spool and verifying its SHA-256.
    """

    measurement = SpreadsheetParserMeasurement("sales")
    with measurement:
        df, archive_stats = _load_sales_dataframe_impl(
            source,
            source_filename=source_filename,
        )
        measurement.set_preflight(archive_stats)
        measurement.set_rows(len(df))
    resource_stats = measurement.as_dict()
    df.attrs["parser_resource_stats"] = resource_stats

    # Backward-compatible sales metric names remain available in the worker
    # registry; durable evidence is also copied into the generation manifest.
    IMPORT_COMPRESSED_BYTES.set(max(0, archive_stats.compressed_bytes or 0))
    IMPORT_EXPANDED_BYTES.set(max(0, archive_stats.uncompressed_bytes or 0))
    IMPORT_DATAFRAME_BYTES.set(int(df.memory_usage(deep=True).sum()))
    IMPORT_ROWS.set(len(df))
    IMPORT_PARSE_SECONDS.observe(float(resource_stats["parse_seconds"] or 0))
    IMPORT_PEAK_RSS_BYTES.set(int(resource_stats["peak_rss_bytes"] or 0))
    return df


def validate_sales_dataframe(df: pd.DataFrame) -> None:
    """Reject ambiguous or lossy input before reserving or mutating a snapshot."""
    duplicate_columns = sorted(
        {str(column) for column in df.columns if list(df.columns).count(column) > 1}
    )
    if duplicate_columns:
        _raise_structural_contradiction(
            "duplicate_headers",
            "Fișierul conține antete duplicate.",
            headers=duplicate_columns,
        )
    missing_columns = [column for column in SALES_COLUMNS if column not in df.columns]
    if missing_columns:
        _raise_structural_contradiction(
            "missing_required_columns",
            f"Lipsesc coloane obligatorii: {', '.join(missing_columns)}",
            columns=missing_columns,
        )

    if df["Data"].isna().any():
        _raise_structural_contradiction(
            "invalid_sale_date",
            "Coloana Data conține valori invalide.",
        )
    quantity = pd.to_numeric(df["Cantitate"], errors="coerce")
    invalid_quantity = quantity.isna() | ~quantity.map(
        lambda value: math.isfinite(float(value))
    )
    fractional_quantity = ~quantity.map(
        lambda value: bool(pd.isna(value)) or float(value).is_integer()
    )
    if bool(
        (
            invalid_quantity
            | fractional_quantity
            | (quantity.abs() > 2_147_483_647)
        ).any()
    ):
        _raise_structural_contradiction(
            "invalid_quantity",
            "Coloana Cantitate conține valori invalide.",
        )
    for column in ("Pret", "Valoare"):
        numeric = pd.to_numeric(df[column], errors="coerce")
        invalid = numeric.isna() | ~numeric.map(
            lambda value: math.isfinite(float(value))
        )
        if bool((invalid | (numeric.abs() > 99_999_999.99)).any()):
            _raise_structural_contradiction(
                "invalid_money",
                f"Coloana {column} conține valori monetare invalide.",
                column=column,
            )

    # Rows without an assigned ASM are deliberately excluded from Retail
    # imports (TR locations / unallocated agents).  Do not make an ignored row
    # fail identifier validation, but keep numeric validation on the complete
    # source file above.
    importable_rows = df[
        ~df["ASM"].fillna("").astype(str).str.strip().isin(["", "-"])
    ]
    required_identifiers = (
        "SiteCode",
        "ItemCode",
        "ItemName",
        "Locatie",
        "Firma",
        "Regional",
        "Nr",
        "Agent",
    )
    invalid_required = [
        column
        for column in required_identifiers
        if importable_rows[column]
        .map(lambda value: bool(pd.isna(value)) or not str(value).strip())
        .any()
    ]
    if invalid_required:
        _raise_structural_contradiction(
            "missing_required_identifiers",
            "Fișierul conține identificatori obligatorii lipsă: "
            + ", ".join(invalid_required),
            columns=invalid_required,
        )

    # The source export has no stable line identifier.  Equal values across the
    # visible columns can represent separate units sold on the same receipt, so
    # row equality is not a valid business key.  Preserve multiplicity and never
    # reject or drop these rows.  See docs/adr/004-sales-row-multiplicity.md.

    metadata_columns = ["Locatie", "Firma", "Regional", "ASM"]
    valid_structure = importable_rows
    conflicting_sites = 0
    if not valid_structure.empty:
        grouped = valid_structure.groupby("SiteCode", dropna=False)[metadata_columns]
        conflicting_sites = int((grouped.nunique(dropna=False) > 1).any(axis=1).sum())
    if conflicting_sites:
        conflicting_site_codes = sorted(
            str(site_code)
            for site_code, group in valid_structure.groupby("SiteCode", dropna=False)
            if (group[metadata_columns].nunique(dropna=False) > 1).any()
        )
        _raise_structural_contradiction(
            "contradictory_store_metadata",
            f"Fișierul conține metadate contradictorii pentru {conflicting_sites} magazine.",
            store_count=conflicting_sites,
            store_codes=conflicting_site_codes,
        )


def _site_set_digest(site_codes: set[str]) -> str:
    payload = "\n".join(sorted(site_codes)).encode("utf-8")
    return sha256(payload).hexdigest()


async def build_import_coverage_report(
    conn: asyncpg.Connection,
    df: pd.DataFrame,
) -> dict[str, Any]:
    incoming = {str(value) for value in df["SiteCode"].unique()}
    active_rows = await conn.fetch(
        "SELECT site_code, locatie, firma, regional, asm FROM stores WHERE is_active = true"
    )
    all_rows = await conn.fetch(
        "SELECT site_code, locatie, firma, regional, asm FROM stores"
    )
    prior_rows = await conn.fetch(
        """
        SELECT DISTINCT st.site_code
        FROM sales_transactions st
        WHERE st.snapshot_id = (
            SELECT id
            FROM import_snapshots
            WHERE status = 'completed'
            ORDER BY import_month DESC, created_at DESC
            LIMIT 1
        )
        """
    )
    active = {str(row["site_code"]) for row in active_rows}
    existing = {str(row["site_code"]) for row in all_rows}
    prior = {str(row["site_code"]) for row in prior_rows}
    missing_active = active - incoming
    missing_prior = prior - incoming
    new_sites = incoming - existing

    existing_metadata = {
        str(row["site_code"]): (
            row["locatie"],
            row["firma"],
            row["regional"],
            row["asm"],
        )
        for row in all_rows
    }
    incoming_metadata = {
        str(row.SiteCode): (row.Locatie, row.Firma, row.Regional, row.ASM)
        for row in df[["SiteCode", "Locatie", "Firma", "Regional", "ASM"]]
        .drop_duplicates(subset=["SiteCode"])
        .itertuples(index=False)
    }
    metadata_changes = sum(
        existing_metadata[site_code] != metadata
        for site_code, metadata in incoming_metadata.items()
        if site_code in existing_metadata
    )

    def coverage(numerator: int, denominator: int) -> float | None:
        if denominator == 0:
            return None
        return round(numerator / denominator * 100, 2)

    report: dict[str, Any] = {
        "incoming_store_count": len(incoming),
        "company_count": int(df["Firma"].nunique()),
        "active_store_count_before": len(active),
        "prior_snapshot_store_count": len(prior),
        "active_store_coverage_pct": coverage(len(incoming & active), len(active)),
        "prior_snapshot_coverage_pct": coverage(len(incoming & prior), len(prior)),
        "missing_active_store_count": len(missing_active),
        "missing_prior_store_count": len(missing_prior),
        "new_store_count": len(new_sites),
        "metadata_change_count": metadata_changes,
        "incoming_set_sha256": _site_set_digest(incoming),
        "missing_active_set_sha256": _site_set_digest(missing_active),
        "missing_prior_set_sha256": _site_set_digest(missing_prior),
        "new_store_set_sha256": _site_set_digest(new_sites),
        "store_activity_writes": 0,
    }
    informational_anomalies: list[dict[str, Any]] = []
    if missing_active:
        informational_anomalies.append(
            make_sales_anomaly(
                "missing_active_stores",
                SalesAnomalyClassification.INFORMATIONAL,
                "Magazine active anterior lipsesc din fișierul cumulativ; nu sunt dezactivate automat.",
                count=len(missing_active),
                set_sha256=report["missing_active_set_sha256"],
            )
        )
    if missing_prior:
        informational_anomalies.append(
            make_sales_anomaly(
                "missing_prior_snapshot_stores",
                SalesAnomalyClassification.INFORMATIONAL,
                "Magazine din snapshotul anterior lipsesc din fișierul curent; necesită review.",
                count=len(missing_prior),
                set_sha256=report["missing_prior_set_sha256"],
            )
        )
    if new_sites:
        informational_anomalies.append(
            make_sales_anomaly(
                "new_stores",
                SalesAnomalyClassification.INFORMATIONAL,
                "Fișierul conține magazine noi față de master data.",
                count=len(new_sites),
                set_sha256=report["new_store_set_sha256"],
            )
        )
    if metadata_changes:
        informational_anomalies.append(
            make_sales_anomaly(
                "master_store_metadata_changed",
                SalesAnomalyClassification.INFORMATIONAL,
                "Metadatele magazinelor diferă de master data activă; actualizarea este auditabilă la promote.",
                count=metadata_changes,
            )
        )
    report["anomalies"] = informational_anomalies
    return report


def normalize_firma(value: str) -> str:
    cleaned = str(value or "").strip()
    lower = cleaned.lower()
    if lower == "mobiup":
        return "Mobiup"
    if lower == "mobicell":
        return "MobiCell"
    return cleaned


def filter_asm_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Filter out rows where ASM is empty, '-', or NaN (TR locations / unallocated agents).
    Returns (filtered_df, rows_removed_count).
    """
    total_before = len(df)
    asm_col = df["ASM"].fillna("").astype(str).str.strip()
    mask_valid = ~asm_col.isin(["", "-"])
    filtered = df[mask_valid].copy()
    return filtered, total_before - len(filtered)


def detect_month(df: pd.DataFrame) -> str:
    months = df["Data"].map(lambda value: value.strftime("%Y-%m")).unique().tolist()
    if len(months) != 1:
        _raise_structural_contradiction(
            "mixed_import_months",
            f"Fișierul conține mai multe luni: {months}",
            months=months,
        )
    return str(months[0])


def is_month_final(import_month: str, *, clock: BusinessClock | None = None) -> bool:
    """A month is final if we're uploading in a later month.
    E.g. uploading 2026-03 data on 2026-04-01 means march is final.
    """
    current = business_today(clock).strftime("%Y-%m")
    return import_month < current


async def upsert_stores(conn: asyncpg.Connection, df: pd.DataFrame, import_month: str) -> None:
    latest_completed_month = await conn.fetchval(
        """
        SELECT MAX(import_month)
        FROM import_snapshots
        WHERE status = 'completed'
        """
    )
    updates_current_structure = latest_completed_month is None or import_month >= latest_completed_month

    records = []
    deduped = (
        df[["SiteCode", "Locatie", "Firma", "Regional", "ASM"]]
        .drop_duplicates(subset=["SiteCode"])
        .sort_values(["SiteCode"])
    )
    for row in deduped.itertuples(index=False):
        records.append(
            (
                row.SiteCode,
                row.Locatie,
                row.Firma,
                row.Regional,
                row.ASM,
                import_month,
                import_month,
                updates_current_structure,
            )
        )

    await conn.executemany(
        """
        INSERT INTO stores (
            site_code, locatie, firma, regional, asm, first_seen_month, last_seen_month, is_active
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (site_code) DO UPDATE
        SET locatie = CASE WHEN $8 THEN EXCLUDED.locatie ELSE stores.locatie END,
            firma = CASE WHEN $8 THEN EXCLUDED.firma ELSE stores.firma END,
            regional = CASE WHEN $8 THEN EXCLUDED.regional ELSE stores.regional END,
            asm = CASE WHEN $8 THEN EXCLUDED.asm ELSE stores.asm END,
            is_active = stores.is_active,
            first_seen_month = LEAST(stores.first_seen_month, EXCLUDED.first_seen_month),
            last_seen_month = GREATEST(stores.last_seen_month, EXCLUDED.last_seen_month),
            updated_at = now()
        """,
        records,
    )
