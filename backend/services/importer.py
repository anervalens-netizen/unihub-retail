from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
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


def load_sales_dataframe(source: str | Path | bytes) -> pd.DataFrame:
    if isinstance(source, bytes):
        content: str | BytesIO = BytesIO(source)
    else:
        content = str(source)

    df = pd.read_excel(content, engine=None)
    df = df.rename(columns=lambda value: str(value).strip())
    missing = [column for column in SALES_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Lipsesc coloane obligatorii: {', '.join(missing)}")

    df = df[SALES_COLUMNS].copy()
    df["Data"] = pd.to_datetime(df["Data"], format="%d.%m.%Y", errors="raise").dt.date
    df["Cantitate"] = pd.to_numeric(df["Cantitate"], errors="raise").astype(int)
    df["Pret"] = pd.to_numeric(df["Pret"], errors="coerce").fillna(0)
    df["Valoare"] = pd.to_numeric(df["Valoare"], errors="coerce").fillna(0)
    df["Nr"] = df["Nr"].fillna("").map(lambda value: str(value).strip())
    for column in ["SiteCode", "ItemCode", "ItemName", "Locatie", "Firma", "ASM", "Regional", "Agent"]:
        df[column] = df[column].fillna("").map(lambda value: str(value).strip())
    for column in ["Brand", "Categorie", "SubCategorie"]:
        df[column] = df[column].where(pd.notna(df[column]), None)
        df[column] = df[column].map(lambda value: str(value).strip() if isinstance(value, str) else value)

    df["is_cartela"] = df["Categorie"].isna() | (df["Categorie"].astype(str).str.strip() == "")
    df["is_return"] = df["Cantitate"] < 0
    return df


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
            )
        )

    await conn.executemany(
        """
        INSERT INTO stores (
            site_code, locatie, firma, regional, asm, first_seen_month, last_seen_month
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (site_code) DO UPDATE
        SET locatie = EXCLUDED.locatie,
            firma = EXCLUDED.firma,
            regional = EXCLUDED.regional,
            asm = EXCLUDED.asm,
            is_active = true,
            first_seen_month = LEAST(stores.first_seen_month, EXCLUDED.first_seen_month),
            last_seen_month = GREATEST(stores.last_seen_month, EXCLUDED.last_seen_month),
            updated_at = now()
        """,
        records,
    )


async def replace_month_snapshot(conn: asyncpg.Connection, import_month: str) -> None:
    await conn.execute("SELECT replace_month_snapshot($1)", import_month)


async def insert_snapshot(
    conn: asyncpg.Connection,
    import_month: str,
    filename: str,
    rows_in_file: int,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO import_snapshots (
            import_month, filename, rows_in_file, status, is_month_final
        )
        VALUES ($1, $2, $3, 'processing', $4)
        RETURNING id
        """,
        import_month,
        filename,
        rows_in_file,
        is_month_final(import_month),
    )
    if row is None:
        raise RuntimeError("Nu s-a putut crea snapshot-ul de import")
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
    rows_in_file_total = len(df)

    # Filter out non-ASM rows (TR locations, unallocated agents)
    df, rows_filtered = filter_asm_rows(df)
    if df.empty:
        raise ValueError("Fișierul nu conține rânduri cu ASM valid după filtrare.")

    import_month = detect_month(df)
    month_final = is_month_final(import_month)

    snapshot_id = await insert_snapshot(
        conn,
        import_month=import_month,
        filename=filename,
        rows_in_file=rows_in_file_total,
    )
    try:
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
                    error_message = NULL
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
                error_message = $2
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
        site_code = str(row.get("SiteCode", "")).strip()
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
