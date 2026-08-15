from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import asyncpg
import pandas as pd

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
from services.sales_import_parsing import (
    IMPORT_COMPRESSED_BYTES,
    IMPORT_DATAFRAME_BYTES,
    IMPORT_EXPANDED_BYTES,
    IMPORT_PARSE_SECONDS,
    IMPORT_PEAK_RSS_BYTES,
    IMPORT_ROWS,
    SALES_COLUMNS,
    _load_sales_dataframe_impl,
    _raise_structural_contradiction,
    build_import_coverage_report,
    detect_month,
    filter_asm_rows,
    is_month_final,
    load_sales_dataframe,
    normalize_firma,
    upsert_stores,
    validate_sales_dataframe,
)
from services.sales_import_recovery import (
    _reconcile_sales_artifacts,
    reconcile_interrupted_imports,
)
from services.sales_import_storage import (
    ImportAlreadyRunningError,
    _to_decimal,
    insert_transactions,
    record_coverage_report,
    reserve_snapshot,
)
from services.spreadsheet_safety import (
    TARGETS_SPREADSHEET_LIMITS,
    SpreadsheetParserMeasurement,
    SpreadsheetUploadError,
    validate_spreadsheet_upload,
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


async def _validate_and_stage_generation(
    conn: asyncpg.Connection,
    df: pd.DataFrame,
    *,
    import_month: str,
    declared_cutoff: date,
    digest: str,
    rows_in_file: int,
    rows_filtered: int,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    parser_resource_stats: dict[str, int | float | str | None] | None,
) -> tuple[int, dict[str, Any], str, dict[str, Any]]:
    coverage_report = await build_import_coverage_report(conn, df)
    _, previous_manifest = await load_current_sales_manifest(conn, import_month)
    manifest = build_sales_generation_manifest(
        df,
        source_sha256=digest,
        cutoff_date=declared_cutoff,
        rows_in_file=rows_in_file,
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
                (
                    "Rândurile fără ASM valid sunt excluse din Retail și "
                    "păstrate ca anomalie informativă."
                ),
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
    return rows_imported, manifest, manifest_sha256, coverage_report


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
        (
            rows_imported,
            manifest,
            manifest_sha256,
            coverage_report,
        ) = await _validate_and_stage_generation(
            conn,
            df,
            import_month=import_month,
            declared_cutoff=declared_cutoff,
            digest=digest,
            rows_in_file=rows_in_file_total,
            rows_filtered=rows_filtered,
            snapshot_id=snapshot_id,
            generation_token=generation_token,
            owner_id=owner_id,
            parser_resource_stats=parser_resource_stats,
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
