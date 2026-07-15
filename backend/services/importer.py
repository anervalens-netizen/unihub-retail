from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import re
from typing import Any

import asyncpg
import pandas as pd

from services.reporting_refresh import (
    rebuild_agent_lifecycle_reporting,
    rebuild_reporting_month,
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


class ImportAlreadyRunningError(RuntimeError):
    pass


async def reconcile_interrupted_imports(pool: asyncpg.Pool) -> list[int]:
    """Close leases left by a worker stop before ARQ retries queued imports.

    The import transaction is bound to the worker connection, so PostgreSQL
    rolls it back when that process stops. Only the reservation row survives
    because it is intentionally committed before the destructive replacement.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE import_snapshots
            SET status = 'failed',
                rows_imported = 0,
                error_message = 'Import intrerupt de restartul workerului; retry permis',
                heartbeat_at = now()
            WHERE status = 'processing'
            RETURNING id
            """
        )
    return [int(row["id"]) for row in rows]


def load_sales_dataframe(source: str | Path | bytes) -> pd.DataFrame:
    if isinstance(source, bytes):
        header_content: str | BytesIO = BytesIO(source)
        content: str | BytesIO = BytesIO(source)
    else:
        header_content = content = str(source)

    # pandas mangles duplicate labels before exposing ``df.columns`` (for
    # example ``SiteCode`` / ``SiteCode.1``).  Inspect the raw first row so a
    # contradictory workbook cannot bypass the duplicate-header gate.
    raw_header = pd.read_excel(header_content, header=None, nrows=1, engine=None)
    raw_columns = [
        "" if pd.isna(value) else str(value).strip()
        for value in raw_header.iloc[0].tolist()
    ]
    duplicate_headers = sorted(
        {
            column
            for column in raw_columns
            if column and raw_columns.count(column) > 1
        }
    )
    if duplicate_headers:
        raise ValueError("Fișierul conține antete duplicate.")

    df = pd.read_excel(content, engine=None)
    normalized_columns = [str(value).strip() for value in df.columns]
    df.columns = normalized_columns
    missing = [column for column in SALES_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Lipsesc coloane obligatorii: {', '.join(missing)}")

    df = df[SALES_COLUMNS].copy()
    try:
        df["Data"] = pd.to_datetime(
            df["Data"], format="%d.%m.%Y", errors="raise"
        ).dt.date
    except (TypeError, ValueError) as exc:
        raise ValueError("Coloana Data conține valori invalide.") from exc

    quantity = pd.to_numeric(df["Cantitate"], errors="coerce")
    invalid_quantity = quantity.isna() | ~quantity.map(
        lambda value: math.isfinite(float(value))
    )
    fractional_quantity = ~quantity.map(
        lambda value: bool(pd.isna(value)) or float(value).is_integer()
    )
    out_of_range_quantity = quantity.abs() > 2_147_483_647
    if bool((invalid_quantity | fractional_quantity | out_of_range_quantity).any()):
        raise ValueError("Coloana Cantitate conține valori invalide.")
    df["Cantitate"] = quantity.astype("int64")

    for column in ("Pret", "Valoare"):
        numeric = pd.to_numeric(df[column], errors="coerce")
        invalid = numeric.isna() | ~numeric.map(
            lambda value: math.isfinite(float(value))
        )
        out_of_range = numeric.abs() > 99_999_999.99
        if bool((invalid | out_of_range).any()):
            raise ValueError(f"Coloana {column} conține valori monetare invalide.")
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
    return df


def validate_sales_dataframe(df: pd.DataFrame) -> None:
    """Reject ambiguous or lossy input before reserving or mutating a snapshot."""
    missing_columns = [column for column in SALES_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Lipsesc coloane obligatorii: {', '.join(missing_columns)}")

    if df["Data"].isna().any():
        raise ValueError("Coloana Data conține valori invalide.")
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
        raise ValueError("Coloana Cantitate conține valori invalide.")
    for column in ("Pret", "Valoare"):
        numeric = pd.to_numeric(df[column], errors="coerce")
        invalid = numeric.isna() | ~numeric.map(
            lambda value: math.isfinite(float(value))
        )
        if bool((invalid | (numeric.abs() > 99_999_999.99)).any()):
            raise ValueError(f"Coloana {column} conține valori monetare invalide.")

    # Rows without an assigned ASM are deliberately excluded from Retail
    # imports (TR locations / unallocated agents).  Do not make an ignored row
    # fail identifier validation, but keep numeric and duplicate validation on
    # the complete source file above.
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
        raise ValueError(
            "Fișierul conține identificatori obligatorii lipsă: "
            + ", ".join(invalid_required)
        )

    if df.duplicated(subset=SALES_COLUMNS, keep=False).any():
        raise ValueError("Fișierul conține rânduri duplicate.")

    metadata_columns = ["Locatie", "Firma", "Regional", "ASM"]
    valid_structure = importable_rows
    conflicting_sites = 0
    if not valid_structure.empty:
        grouped = valid_structure.groupby("SiteCode", dropna=False)[metadata_columns]
        conflicting_sites = int((grouped.nunique(dropna=False) > 1).any(axis=1).sum())
    if conflicting_sites:
        raise ValueError(
            f"Fișierul conține metadate contradictorii pentru {conflicting_sites} magazine."
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

    return {
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
        raise ValueError(f"Fișierul conține mai multe luni: {months}")
    return str(months[0])


def is_month_final(import_month: str) -> bool:
    """A month is final if we're uploading in a later month.
    E.g. uploading 2026-03 data on 2026-04-01 means march is final.
    """
    now = datetime.now(timezone.utc)
    current = now.strftime("%Y-%m")
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


async def replace_month_snapshot(conn: asyncpg.Connection, import_month: str) -> None:
    await conn.execute("SELECT replace_month_snapshot($1)", import_month)


async def reserve_snapshot(
    conn: asyncpg.Connection,
    import_month: str,
    filename: str,
    rows_in_file: int,
) -> int:
    async with conn.transaction():
        await conn.execute(
            """
            UPDATE import_snapshots
            SET status = 'failed',
                rows_imported = 0,
                error_message = 'Import processing abandonat si inchis automat',
                heartbeat_at = now()
            WHERE import_month = $1
              AND status = 'processing'
              AND COALESCE(heartbeat_at, created_at) < now() - interval '1 hour'
            """,
            import_month,
        )
        row = await conn.fetchrow(
            """
            INSERT INTO import_snapshots (
                import_month, filename, rows_in_file, status,
                is_month_final, heartbeat_at
            )
            VALUES ($1, $2, $3, 'processing', $4, now())
            ON CONFLICT (import_month)
                WHERE status = 'processing'
            DO NOTHING
            RETURNING id
            """,
            import_month,
            filename,
            rows_in_file,
            is_month_final(import_month),
        )
    if row is None:
        raise ImportAlreadyRunningError(
            f"Exista deja un import in curs pentru luna {import_month}"
        )
    return int(row["id"])


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def insert_transactions(conn: asyncpg.Connection, df: pd.DataFrame, snapshot_id: int, import_month: str) -> int:
    records = []
    for row in df.itertuples(index=False):
        records.append(
            (
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
        records=records,
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
    return len(records)


async def import_sales_dataframe(
    conn: asyncpg.Connection,
    df: pd.DataFrame,
    filename: str,
) -> ImportResult:
    validate_sales_dataframe(df)
    rows_in_file_total = len(df)

    # Filter out non-ASM rows (TR locations, unallocated agents)
    df, rows_filtered = filter_asm_rows(df)
    if df.empty:
        raise ValueError("Fișierul nu conține rânduri cu ASM valid după filtrare.")

    import_month = detect_month(df)
    month_final = is_month_final(import_month)

    snapshot_id = await reserve_snapshot(
        conn,
        import_month=import_month,
        filename=filename,
        rows_in_file=rows_in_file_total,
    )
    try:
        coverage_report = await build_import_coverage_report(conn, df)
        await record_coverage_report(conn, snapshot_id, coverage_report)
        async with conn.transaction():
            await upsert_stores(conn, df, import_month)
            await replace_month_snapshot(conn, import_month)
            rows_imported = await insert_transactions(conn, df, snapshot_id, import_month)
            await rebuild_reporting_month(conn, import_month)
            await rebuild_agent_lifecycle_reporting(conn)

            # If month is final, mark it
            await conn.execute(
                """
                UPDATE import_snapshots
                SET status = 'completed',
                    rows_imported = $2,
                    is_month_final = $3,
                    error_message = NULL,
                    heartbeat_at = now()
                WHERE id = $1
                """,
                snapshot_id,
                rows_imported,
                month_final,
            )
    except Exception as exc:
        await conn.execute(
            """
            UPDATE import_snapshots
            SET status = 'failed',
                rows_imported = 0,
                error_message = $2,
                heartbeat_at = now()
            WHERE id = $1
            """,
            snapshot_id,
            str(exc)[:500],
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
    )


async def import_sales_file(
    conn: asyncpg.Connection,
    source: str | Path | bytes,
    filename: str,
) -> ImportResult:
    df = load_sales_dataframe(source)
    return await import_sales_dataframe(conn, df, filename=filename)


def load_targets_dataframe(source: str | Path) -> list[dict[str, Any]]:
    df = pd.read_excel(source, header=1)
    df = df.rename(columns=lambda value: str(value).strip() if value is not None else "")
    raw_header = pd.read_excel(source, header=None, nrows=2)
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
