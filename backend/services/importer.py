from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import asyncpg
import pandas as pd
from prometheus_client import Gauge, Histogram

from business_clock import BusinessClock, business_today
from services.legacy_xls import limits_from_upload_policy
from services.spreadsheet_readers import read_spreadsheet_frame
from services.reporting_refresh import (
    rebuild_agent_lifecycle_reporting,
    rebuild_reporting_month,
)
from services.sales_generation import (
    SalesAnomalyClassification,
    SalesPolicyValidationError,
    build_sales_generation_manifest,
    canonical_sales_stage_rows_sha256,
    canonical_json_sha256,
    compare_sales_generation_manifests,
    fenced_generation_heartbeat,
    make_sales_anomaly,
    stage_sales_generation_rows,
)
from services.sales_generation_flow import (
    fail_sales_generation,
    load_current_sales_manifest,
    persist_validated_sales_generation,
    promote_sales_generation,
)
from services.jobs import (
    SalesImportArtifactConflictError,
    SalesImportArtifactError,
    cleanup_sales_import_retained_artifacts,
    retain_sales_import_spool_file,
    verify_sales_import_artifact,
)
from services.spreadsheet_safety import (
    SALES_SPREADSHEET_LIMITS,
    TARGETS_SPREADSHEET_LIMITS,
    SpreadsheetParserMeasurement,
    SpreadsheetUploadError,
    SpreadsheetUploadStats,
    validate_spreadsheet_upload,
)
SALES_COLUMNS = [
    "Data",
    "SiteCode",
    "ItemCode",
    "ItemName",
    "Cantitate",
    "Brand",
    "Pret",
    "Valoare",
    "Locatie",
    "Firma",
    "ASM",
    "Regional",
    "Nr",
    "Categorie",
    "SubCategorie",
    "Agent",
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


@dataclass(slots=True)
class ImportResult:
    import_month: str
    rows_in_file: int
    rows_imported: int
    rows_filtered: int
    store_count: int
    agent_count: int
    snapshot_id: int
    filename: str
    is_month_final: bool
    coverage_report: dict[str, Any]
    generation_state: str = "promoted"
    generation_token: str | None = None
    owner_id: str | None = None
    manifest_sha256: str | None = None
    manifest: dict[str, Any] | None = None


class ImportAlreadyRunningError(RuntimeError):
    pass


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


async def reconcile_interrupted_imports(pool: asyncpg.Pool) -> list[int]:
    """Close leases left by a worker stop before ARQ retries queued imports.
    Startup only closes an expired staging lease (or a legacy reservation stale
    for more than one hour). A validated generation is deliberately retained
    for explicit promotion after a worker restart; a stale promoting claim is
    returned to validated so the operator can retry it safely.
    """
    artifact_recovered = await _reconcile_sales_artifacts(pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            recovered = await conn.fetch(
                """
                UPDATE import_snapshots
                SET owner_id = gen_random_uuid(),
                    lease_until = now() + interval '2 hours',
                    heartbeat_at = now(),
                    finished_at = NULL,
                    error_message = 'Promovarea a fost întreruptă de restart; retry permis',
                    rows_imported = COALESCE(NULLIF(manifest->>'rows_imported', '')::integer, rows_imported),
                    manifest = jsonb_set(manifest, '{generation_state}', '"validated"'::jsonb, true)
                WHERE status = 'processing'
                  AND manifest->>'generation_state' = 'promoting'
                  AND source_artifact_state IS NULL
                  AND (
                        (lease_until IS NOT NULL AND lease_until <= now())
                        OR (lease_until IS NULL AND COALESCE(heartbeat_at, created_at) < now() - interval '1 hour')
                  )
                RETURNING id
                """
            )
            closed = await conn.fetch(
                """
                UPDATE import_snapshots
                SET status = 'failed',
                    rows_imported = 0,
                    error_message = 'Import intrerupt de restartul workerului; retry permis',
                    heartbeat_at = now(),
                    finished_at = now()
                WHERE status = 'processing'
                  AND COALESCE(manifest->>'generation_state', '') NOT IN ('validated', 'promoting')
                  AND COALESCE(source_artifact_state, '') NOT IN ('artifact_retaining', 'artifact_retained')
                  AND (
                        (lease_until IS NOT NULL AND lease_until <= now())
                        OR (lease_until IS NULL AND COALESCE(heartbeat_at, created_at) < now() - interval '1 hour')
                  )
                RETURNING id
                """
            )
    return [*artifact_recovered, *[int(row["id"]) for row in [*recovered, *closed]]]


async def _reconcile_sales_artifacts(pool: asyncpg.Pool) -> list[int]:
    """Retry only fenced artifact work; never promote a generation at startup."""
    async with pool.acquire() as conn:
        candidates = await conn.fetch(
            """
            SELECT id, generation_token, owner_id, import_month, source_spool_path,
                   source_sha256, source_artifact_bytes
            FROM import_snapshots
            WHERE status = 'processing'
              AND source_artifact_state IN ('artifact_retaining', 'artifact_retained')
            """
        )
    reconciled: list[int] = []
    for candidate in candidates:
        snapshot_id = int(candidate["id"])
        try:
            retained = await asyncio.to_thread(
                retain_sales_import_spool_file,
                str(candidate["source_spool_path"]),
                import_month=str(candidate["import_month"]),
                snapshot_id=snapshot_id,
                expected_digest=str(candidate["source_sha256"]),
                expected_bytes=(
                    int(candidate["source_artifact_bytes"])
                    if candidate["source_artifact_bytes"] is not None
                    else None
                ),
            )
            size = await asyncio.to_thread(
                verify_sales_import_artifact,
                str(retained),
                str(candidate["source_sha256"]),
                int(candidate["source_artifact_bytes"])
                if candidate["source_artifact_bytes"] is not None
                else None,
            )
            async with pool.acquire() as conn:
                updated = await conn.fetchval(
                    """
                    UPDATE import_snapshots
                    SET source_spool_path = $4,
                        source_artifact_retained_path = $4,
                        source_artifact_state = 'artifact_retained',
                        source_artifact_sha256 = $5,
                        source_artifact_bytes = $6,
                        source_artifact_retained_at = COALESCE(source_artifact_retained_at, now()),
                        heartbeat_at = now(),
                        manifest = CASE
                            WHEN manifest->>'generation_state' = 'promoting'
                            THEN jsonb_set(manifest, '{generation_state}', '"validated"'::jsonb, true)
                            ELSE manifest
                        END,
                        status = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN status ELSE 'failed'
                        END,
                        rows_imported = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN rows_imported ELSE 0
                        END,
                        error_message = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN error_message
                            ELSE 'Import interrupted before validation; exact-source retry permitted'
                        END,
                        finished_at = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN finished_at ELSE now()
                        END,
                        lease_until = CASE
                            WHEN manifest->>'generation_state' IN ('validated', 'promoting')
                            THEN now() + interval '2 hours' ELSE now()
                        END
                    WHERE id = $1 AND generation_token = $2::uuid
                      AND owner_id = $3::uuid AND status = 'processing'
                      AND source_artifact_state IN ('artifact_retaining', 'artifact_retained')
                    RETURNING id
                    """,
                    snapshot_id,
                    str(candidate["generation_token"]),
                    str(candidate["owner_id"]),
                    str(retained),
                    str(candidate["source_sha256"]),
                    size,
                )
            if updated is not None:
                reconciled.append(snapshot_id)
        except (SalesImportArtifactConflictError, SalesImportArtifactError) as exc:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE import_snapshots
                    SET status = 'failed', rows_imported = 0,
                        error_message = $4, finished_at = now(), heartbeat_at = now(),
                        lease_until = now(), source_artifact_state = 'recovery_required'
                    WHERE id = $1 AND generation_token = $2::uuid
                      AND owner_id = $3::uuid AND status = 'processing'
                    """,
                    snapshot_id,
                    str(candidate["generation_token"]),
                    str(candidate["owner_id"]),
                    f"Sales artifact recovery required: {type(exc).__name__}",
                )
            reconciled.append(snapshot_id)
        except OSError as exc:
            # Transient filesystem failures leave the validated candidate
            # retryable through an exact-source re-upload. No auto-promotion.
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE import_snapshots
                    SET source_artifact_state = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_state ELSE NULL
                        END,
                        source_artifact_sha256 = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_sha256 ELSE NULL
                        END,
                        source_artifact_bytes = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_bytes ELSE NULL
                        END,
                        source_artifact_retained_at = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_retained_at ELSE NULL
                        END,
                        source_artifact_retained_path = CASE
                            WHEN source_artifact_state = 'artifact_retained'
                            THEN source_artifact_retained_path ELSE NULL
                        END,
                        manifest = CASE
                            WHEN manifest->>'generation_state' = 'promoting'
                            THEN jsonb_set(manifest, '{generation_state}', '"validated"'::jsonb, true)
                            ELSE manifest
                        END,
                        error_message = $4,
                        heartbeat_at = now(),
                        lease_until = now()
                    WHERE id = $1 AND generation_token = $2::uuid
                      AND owner_id = $3::uuid AND status = 'processing'
                    """,
                    snapshot_id,
                    str(candidate["generation_token"]),
                    str(candidate["owner_id"]),
                    f"Sales artifact retain retryable: {type(exc).__name__}",
                )
            reconciled.append(snapshot_id)

    async with pool.acquire() as conn:
        roots = await conn.fetch(
            """
            SELECT DISTINCT COALESCE(s.source_artifact_retained_path, s.source_spool_path) AS path
            FROM import_snapshots s
            WHERE s.id IN (
                SELECT snapshot_id FROM sales_generation_heads
                UNION SELECT previous_snapshot_id FROM sales_generation_heads
                UNION SELECT from_snapshot_id FROM sales_generation_promotions
                UNION SELECT to_snapshot_id FROM sales_generation_promotions
                UNION SELECT id FROM import_snapshots
                      WHERE status = 'processing'
                        AND source_artifact_state = 'artifact_retained'
            )
              AND COALESCE(s.source_artifact_retained_path, s.source_spool_path) IS NOT NULL
            """
        )
    keep_paths = {str(row["path"]) for row in roots}
    await asyncio.to_thread(cleanup_sales_import_retained_artifacts, keep_paths)
    return reconciled


def _load_sales_dataframe_impl(
    source: str | Path | bytes,
    *,
    source_filename: str | None = None,
) -> tuple[pd.DataFrame, SpreadsheetUploadStats]:
    raw_content = source if isinstance(source, bytes) else Path(source).read_bytes()
    suffix = Path(source_filename or (str(source) if not isinstance(source, bytes) else "")).suffix
    if not suffix:
        suffix = ".xls" if raw_content.startswith(bytes.fromhex("d0cf11e0a1b11ae1")) else ".xlsx"
    try:
        archive_stats = validate_spreadsheet_upload(
            raw_content,
            suffix,
            limits=SALES_SPREADSHEET_LIMITS,
        )
    except SpreadsheetUploadError as exc:
        _raise_structural_contradiction("invalid_workbook", str(exc))
        raise AssertionError("unreachable") from exc
    # Parse once; legacy OLE2/XLS is isolated behind the bounded child.
    raw_sheet = read_spreadsheet_frame(
        raw_content,
        suffix=suffix,
        header=None,
        limits=limits_from_upload_policy(SALES_SPREADSHEET_LIMITS),
    )
    if raw_sheet.empty:
        _raise_structural_contradiction("empty_workbook", "Fișierul nu conține date.")
    raw_header = raw_sheet.iloc[0]
    raw_columns = [
        "" if pd.isna(value) else str(value).strip()
        for value in raw_header.tolist()
    ]
    duplicate_headers = sorted(
        {
            column
            for column in raw_columns
            if column and raw_columns.count(column) > 1
        }
    )
    if duplicate_headers:
        _raise_structural_contradiction(
            "duplicate_headers",
            "Fișierul conține antete duplicate.",
            headers=duplicate_headers,
        )
    df = raw_sheet.iloc[1:].copy().reset_index(drop=True)
    df.columns = raw_columns
    missing = [column for column in SALES_COLUMNS if column not in df.columns]
    if missing:
        _raise_structural_contradiction(
            "missing_required_columns",
            f"Lipsesc coloane obligatorii: {', '.join(missing)}",
            columns=missing,
        )

    df = df[SALES_COLUMNS].copy()
    try:
        df["Data"] = pd.to_datetime(
            df["Data"], format="%d.%m.%Y", errors="raise"
        ).dt.date
    except (TypeError, ValueError) as exc:
        try:
            _raise_structural_contradiction(
                "invalid_sale_date",
                "Coloana Data conține valori invalide.",
            )
        except SalesPolicyValidationError as validation_error:
            raise validation_error from exc

    quantity = pd.to_numeric(df["Cantitate"], errors="coerce")
    invalid_quantity = quantity.isna() | ~quantity.map(
        lambda value: math.isfinite(float(value))
    )
    fractional_quantity = ~quantity.map(
        lambda value: bool(pd.isna(value)) or float(value).is_integer()
    )
    out_of_range_quantity = quantity.abs() > 2_147_483_647
    if bool((invalid_quantity | fractional_quantity | out_of_range_quantity).any()):
        _raise_structural_contradiction(
            "invalid_quantity",
            "Coloana Cantitate conține valori invalide.",
        )
    df["Cantitate"] = quantity.astype("int64")

    for column in ("Pret", "Valoare"):
        numeric = pd.to_numeric(df[column], errors="coerce")
        invalid = numeric.isna() | ~numeric.map(
            lambda value: math.isfinite(float(value))
        )
        out_of_range = numeric.abs() > 99_999_999.99
        if bool((invalid | out_of_range).any()):
            _raise_structural_contradiction(
                "invalid_money",
                f"Coloana {column} conține valori monetare invalide.",
                column=column,
            )
        df[column] = numeric
    df["Nr"] = df["Nr"].fillna("").map(lambda value: str(value).strip())
    for column in ["SiteCode", "ItemCode", "ItemName", "Locatie", "Firma", "ASM", "Regional", "Agent"]:
        df[column] = df[column].fillna("").map(lambda value: str(value).strip())
    df["Firma"] = df["Firma"].map(normalize_firma)
    for column in ["Brand", "Categorie", "SubCategorie"]:
        df[column] = df[column].where(pd.notna(df[column]), None)
        df[column] = df[column].map(lambda value: str(value).strip() if isinstance(value, str) else value)

    df["is_cartela"] = df["Categorie"].isna() | (df["Categorie"].astype(str).str.strip() == "")
    df["is_return"] = df["Cantitate"] < 0
    validate_sales_dataframe(df)
    return df, archive_stats


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


async def record_coverage_report(
    conn: asyncpg.Connection,
    snapshot_id: int,
    coverage_report: dict[str, Any],
) -> None:
    await conn.execute(
        """
        UPDATE import_snapshots
        SET coverage_report = $2::jsonb,
            heartbeat_at = now()
        WHERE id = $1 AND status = 'processing'
        """,
        snapshot_id,
        json.dumps(coverage_report, ensure_ascii=False),
    )


async def reserve_snapshot(
    conn: asyncpg.Connection,
    import_month: str,
    filename: str,
    rows_in_file: int,
    *,
    source_sha256: str | None = None,
    cutoff_date: date | None = None,
    generation_token: str | None = None,
    owner_id: str | None = None,
    source_artifact_required: bool = False,
    source_artifact_path: str | None = None,
    source_artifact_bytes: int | None = None,
    lease_seconds: int = 2 * 60 * 60,
) -> int:
    generation_token = generation_token or str(uuid4())
    owner_id = owner_id or str(uuid4())
    if lease_seconds < 60:
        raise ValueError("Sales generation lease must be at least 60 seconds")
    if source_artifact_required and (
        not source_artifact_path
        or source_sha256 is None
        or source_artifact_bytes is None
        or source_artifact_bytes < 0
    ):
        raise ValueError("Required sales artifact metadata is incomplete")
    async with conn.transaction():
        await conn.execute(
            """
            UPDATE import_snapshots
            SET status = 'failed',
                rows_imported = 0,
                error_message = 'Import processing abandonat si inchis automat',
                heartbeat_at = now(),
                finished_at = now()
            WHERE import_month = $1
              AND status = 'processing'
              AND COALESCE(manifest->>'generation_state', '') NOT IN ('validated', 'promoting')
              AND (
                    (lease_until IS NOT NULL AND lease_until <= now())
                    OR (lease_until IS NULL AND COALESCE(heartbeat_at, created_at) < now() - interval '1 hour')
              )
            """,
            import_month,
        )
        head = await conn.fetchrow(
            "SELECT snapshot_id, revision FROM sales_generation_heads WHERE import_month = $1",
            import_month,
        )
        previous_snapshot_id = int(head["snapshot_id"]) if head is not None else None
        expected_head_revision = int(head["revision"]) if head is not None else 0
        row = await conn.fetchrow(
            """
            INSERT INTO import_snapshots (
                import_month, filename, rows_in_file, status,
                is_month_final, heartbeat_at, source_sha256, cutoff_date,
                generation_token, owner_id, lease_until,
                expected_head_revision, previous_snapshot_id
                , source_artifact_required, source_spool_path,
                source_artifact_state, source_artifact_sha256, source_artifact_bytes
            )
            VALUES (
                $1, $2, $3, 'processing', $4, now(), $5, $6,
                $7::uuid, $8::uuid, now() + make_interval(secs => $9),
                $10, $11, $12, $13,
                CASE WHEN $12 THEN 'artifact_retaining' ELSE NULL END,
                CASE WHEN $12 THEN $5 ELSE NULL END, $14
            )
            ON CONFLICT (import_month)
                WHERE status = 'processing'
            DO NOTHING
            RETURNING id
            """,
            import_month,
            filename,
            rows_in_file,
            is_month_final(import_month),
            source_sha256,
            cutoff_date,
            generation_token,
            owner_id,
            lease_seconds,
            expected_head_revision,
            previous_snapshot_id,
            source_artifact_required,
            source_artifact_path,
            source_artifact_bytes,
        )
    if row is None:
        raise ImportAlreadyRunningError(
            f"Exista deja un import in curs pentru luna {import_month}"
        )
    return int(row["id"])


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def insert_transactions(conn: asyncpg.Connection, df: pd.DataFrame, snapshot_id: int, import_month: str) -> int:
    row_count = len(df)

    def records():
        # asyncpg consumes the iterable synchronously while encoding COPY data.
        # Keeping this lazy avoids duplicating the entire DataFrame in memory.
        for row in df.itertuples(index=False):
            yield (
                import_month,
                row.Data,
                row.SiteCode,
                row.Nr,
                row.ItemCode,
                row.ItemName,
                row.Brand,
                row.Categorie,
                row.SubCategorie,
                int(row.Cantitate),
                _to_decimal(row.Pret),
                _to_decimal(row.Valoare),
                row.Agent,
                bool(row.is_cartela),
                bool(row.is_return),
                snapshot_id,
            )

    await conn.execute(
        """
        CREATE TEMP TABLE tmp_sales_transactions (
            import_month TEXT NOT NULL,
            sale_date DATE NOT NULL,
            site_code TEXT NOT NULL,
            bon_nr TEXT NOT NULL,
            item_code TEXT NOT NULL,
            item_name TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            subcategory TEXT,
            quantity INTEGER NOT NULL,
            unit_price NUMERIC(10, 2) NOT NULL,
            total_value NUMERIC(10, 2) NOT NULL,
            agent TEXT NOT NULL,
            is_cartela BOOLEAN NOT NULL,
            is_return BOOLEAN NOT NULL,
            snapshot_id INTEGER NOT NULL
        ) ON COMMIT DROP
        """
    )
    await conn.copy_records_to_table(
        "tmp_sales_transactions",
        records=records(),
        columns=[
            "import_month",
            "sale_date",
            "site_code",
            "bon_nr",
            "item_code",
            "item_name",
            "brand",
            "category",
            "subcategory",
            "quantity",
            "unit_price",
            "total_value",
            "agent",
            "is_cartela",
            "is_return",
            "snapshot_id",
        ],
    )
    await conn.execute(
        """
        INSERT INTO sales_transactions (
            import_month,
            sale_date,
            site_code,
            bon_nr,
            item_code,
            item_name,
            brand,
            category,
            subcategory,
            quantity,
            unit_price,
            total_value,
            agent,
            is_cartela,
            is_return,
            snapshot_id
        )
        SELECT
            import_month,
            sale_date,
            site_code,
            bon_nr,
            item_code,
            item_name,
            brand,
            category,
            subcategory,
            quantity,
            unit_price,
            total_value,
            agent,
            is_cartela,
            is_return,
            snapshot_id
        FROM tmp_sales_transactions
        """,
    )
    return row_count


async def import_sales_dataframe(
    conn: asyncpg.Connection,
    df: pd.DataFrame,
    filename: str,
    *,
    source_sha256: str | None = None,
    cutoff_date: date | None = None,
    stage_only: bool = False,
    requested_by_sub: str = "direct-execution",
    override_reason: str | None = None,
    source_artifact_required: bool = False,
    source_artifact_path: str | None = None,
    source_artifact_bytes: int | None = None,
    parser_resource_stats: dict[str, int | float | str | None] | None = None,
) -> ImportResult:
    validate_sales_dataframe(df)
    rows_in_file_total = len(df)

    df, rows_filtered = filter_asm_rows(df)
    if df.empty:
        _raise_structural_contradiction(
            "empty_after_filter",
            "Fișierul nu conține rânduri cu ASM valid după filtrare.",
            rows_filtered=rows_filtered,
        )

    import_month = detect_month(df)
    month_final = is_month_final(import_month)
    declared_cutoff = cutoff_date or max(df["Data"])
    digest = source_sha256 or canonical_json_sha256(
        {
            "filename": filename,
            "rows": df[SALES_COLUMNS].astype(str).values.tolist(),
        }
    )
    generation_token = str(uuid4())
    owner_id = str(uuid4())

    snapshot_id = await reserve_snapshot(
        conn,
        import_month=import_month,
        filename=filename,
        rows_in_file=rows_in_file_total,
        source_sha256=digest,
        cutoff_date=declared_cutoff,
        generation_token=generation_token,
        owner_id=owner_id,
        source_artifact_required=source_artifact_required,
        source_artifact_path=source_artifact_path,
        source_artifact_bytes=source_artifact_bytes,
    )
    validated = False
    try:
        coverage_report = await build_import_coverage_report(conn, df)
        _, previous_manifest = await load_current_sales_manifest(conn, import_month)
        manifest = build_sales_generation_manifest(
            df,
            source_sha256=digest,
            cutoff_date=declared_cutoff,
            rows_in_file=rows_in_file_total,
            rows_filtered=rows_filtered,
        )
        if parser_resource_stats is not None:
            manifest["parser_resources"] = dict(parser_resource_stats)
        manifest["anomalies"] = compare_sales_generation_manifests(
            manifest,
            previous_manifest,
        )
        if rows_filtered:
            manifest["anomalies"].append(
                make_sales_anomaly(
                    "rows_filtered",
                    SalesAnomalyClassification.INFORMATIONAL,
                    "Rândurile fără ASM valid sunt excluse din Retail și păstrate ca anomalie informativă.",
                    count=rows_filtered,
                )
            )
        manifest["anomalies"].extend(coverage_report.get("anomalies", []))
        manifest["generation_state"] = "validated"
        manifest["stage_rows_sha256"] = canonical_sales_stage_rows_sha256(
            df,
            import_month=import_month,
        )
        manifest_sha256 = canonical_json_sha256(manifest)
        async with conn.transaction():
            await fenced_generation_heartbeat(
                conn,
                snapshot_id=snapshot_id,
                generation_token=generation_token,
                owner_id=owner_id,
                lease_seconds=2 * 60 * 60,
            )
            rows_imported = await stage_sales_generation_rows(
                conn,
                df,
                snapshot_id=snapshot_id,
                import_month=import_month,
            )
            await persist_validated_sales_generation(
                conn,
                snapshot_id=snapshot_id,
                generation_token=generation_token,
                owner_id=owner_id,
                manifest=manifest,
                manifest_sha256=manifest_sha256,
                coverage_report=coverage_report,
            )
        validated = True
        generation_state = "validated"
        if not stage_only:
            rows_imported, _ = await promote_sales_generation(
                conn,
                snapshot_id=snapshot_id,
                generation_token=generation_token,
                owner_id=owner_id,
                expected_manifest_sha256=manifest_sha256,
                requested_by_sub=requested_by_sub,
                override_reason=override_reason,
            )
            generation_state = "promoted"
            manifest = {**manifest, "generation_state": "promoted"}
    except Exception as exc:
        if not validated:
            await fail_sales_generation(
                conn,
                snapshot_id=snapshot_id,
                generation_token=generation_token,
                owner_id=owner_id,
                error=str(exc),
            )
        raise

    return ImportResult(
        import_month=import_month,
        rows_in_file=rows_in_file_total,
        rows_imported=rows_imported,
        rows_filtered=rows_filtered,
        store_count=int(df["SiteCode"].nunique()),
        agent_count=int(df["Agent"].nunique()),
        snapshot_id=snapshot_id,
        filename=filename,
        is_month_final=month_final,
        coverage_report=coverage_report,
        generation_state=generation_state,
        generation_token=generation_token,
        owner_id=owner_id,
        manifest_sha256=manifest_sha256,
        manifest=manifest,
    )


async def import_sales_file(
    conn: asyncpg.Connection,
    source: str | Path | bytes,
    filename: str,
    *,
    cutoff_date: date | None = None,
    stage_only: bool = False,
    requested_by_sub: str = "direct-execution",
    override_reason: str | None = None,
    source_artifact_required: bool = False,
    source_artifact_path: str | None = None,
    source_artifact_bytes: int | None = None,
) -> ImportResult:
    if isinstance(source, bytes):
        digest = sha256(source).hexdigest()
    else:
        digest = sha256(Path(source).read_bytes()).hexdigest()
    df = load_sales_dataframe(source, source_filename=filename)
    return await import_sales_dataframe(
        conn,
        df,
        filename=filename,
        source_sha256=digest,
        cutoff_date=cutoff_date,
        stage_only=stage_only,
        requested_by_sub=requested_by_sub,
        override_reason=override_reason,
        source_artifact_required=source_artifact_required,
        source_artifact_path=source_artifact_path,
        source_artifact_bytes=source_artifact_bytes,
        parser_resource_stats=dict(df.attrs.get("parser_resource_stats") or {}),
    )


def load_targets_dataframe(source: str | Path) -> list[dict[str, Any]]:
    source_path = Path(source)
    content = source_path.read_bytes()
    measurement = SpreadsheetParserMeasurement("targets")
    with measurement:
        try:
            stats = validate_spreadsheet_upload(
                content,
                source_path.suffix,
                limits=TARGETS_SPREADSHEET_LIMITS,
            )
        except SpreadsheetUploadError as exc:
            raise ValueError(str(exc)) from exc
        measurement.set_preflight(stats)
        with pd.ExcelFile(BytesIO(content)) as workbook:
            raw_sheet = workbook.parse(header=None)
        if len(raw_sheet.index) < 2:
            measurement.set_rows(0)
            return []
        raw_header = raw_sheet.iloc[:2]
        df = raw_sheet.iloc[2:].copy()
        df.columns = [
            str(value).strip() if pd.notna(value) else ""
            for value in raw_header.iloc[1].tolist()
        ]
        month_columns: list[tuple[int, str, int, int]] = []
        current_year: int | None = None
        for idx, column in enumerate(df.columns):
            column_name = str(column).strip()
            header_year = raw_header.iloc[0, idx]
            if pd.notna(header_year):
                current_year = int(header_year)
            if not column_name.startswith("TG L"):
                continue
            if current_year is None:
                continue
            match = re.search(r"TG L(\d{2})", column_name)
            if not match:
                continue
            month = int(match.group(1))
            month_columns.append((idx, column_name, current_year, month))

        target_rows: list[dict[str, Any]] = []
        for row in df.to_dict(orient="records"):
            raw_site_code = row.get("SiteCode")
            if pd.isna(raw_site_code):
                continue
            site_code = str(raw_site_code).strip()
            if not site_code:
                continue
            for _, column_name, year, month in month_columns:
                value = row.get(column_name)
                if pd.isna(value):
                    continue
                target_rows.append(
                    {
                        "site_code": site_code,
                        "import_month": f"{year}-{month:02d}",
                        "target_value": _to_decimal(value),
                    }
                )
        measurement.set_rows(len(target_rows))
        return target_rows


async def upsert_store_targets(
    conn: asyncpg.Connection,
    targets: list[dict[str, Any]],
    source_file: str,
) -> int:
    if not targets:
        return 0
    await conn.executemany(
        """
        INSERT INTO store_targets (site_code, import_month, target_value, source_file)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (import_month, site_code) DO UPDATE
        SET target_value = EXCLUDED.target_value,
            source_file = EXCLUDED.source_file,
            created_at = now()
        """,
        [
            (
                target["site_code"],
                target["import_month"],
                target["target_value"],
                source_file,
            )
            for target in targets
        ],
    )
    return len(targets)
