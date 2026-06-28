#!/usr/bin/env python3
"""
Import monthly historical store totals from the legacy 2018-2023 workbook.

The source file has no site_code, so stores are matched by normalized
firma + location. A leading/in-name "Inchis" marker is removed for matching,
but kept as metadata. TR rows are skipped because normal Retail KPIs exclude
TR locations.

Default mode is dry-run. Use --apply to write to historical_monthly_sales.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import openpyxl

BASE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "vanzari 2022, 2023 si 2024"
)
SOURCE_FILES = [
    BASE_DIR / "Mobiup-istoric.xlsx",
    BASE_DIR / "mobicell-istoric-bun.xlsx",
]

VALUE_TYPE = "Accesorii Valoare"
QTY_TYPE = "Accesorii cantitate"
MONTH_COLUMNS = {
    5: 1,
    6: 2,
    7: 3,
    8: 4,
    9: 5,
    10: 6,
    11: 7,
    12: 8,
    13: 9,
    14: 10,
    15: 11,
    16: 12,
}


@dataclass(frozen=True)
class SourceKey:
    firma: str
    year: int
    store_name: str


@dataclass
class SourceRecord:
    firma: str
    year: int
    store_name: str
    manager: str | None
    source_file: str
    had_inchis_prefix: bool
    values: dict[int, float]
    quantities: dict[int, int]


def normalize_text(value: object) -> str:
    text = str(value or "").upper().strip()
    text = re.sub(r"\bINCHIS\b", " ", text)
    text = re.sub(r"\bOBO1\b", " OBOR 1 ", text)
    text = (
        text.replace("Ș", "S")
        .replace("Ş", "S")
        .replace("Ț", "T")
        .replace("Ţ", "T")
        .replace("Ă", "A")
        .replace("Â", "A")
        .replace("Î", "I")
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_year(value: object) -> int | None:
    text = str(value or "").strip().upper()
    if not text.startswith("A"):
        return None
    try:
        return int(text[1:])
    except ValueError:
        return None


def numeric(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    return float(text) if text else 0.0


def load_source_files() -> tuple[dict[SourceKey, SourceRecord], list[str]]:
    records: dict[SourceKey, SourceRecord] = {}
    duplicate_files: list[str] = []

    for path in SOURCE_FILES:
        if not path.exists():
            continue
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        worksheet = workbook.active
        seen_in_file = 0

        for row in worksheet.iter_rows(min_row=3, values_only=True):
            year = parse_year(row[0] if row else None)
            firma = str(row[1] or "").strip()
            data_type = str(row[2] or "").strip()
            store_name = str(row[4] or "").strip()
            if not year or not firma or not store_name:
                continue
            if normalize_text(store_name).startswith("TR "):
                continue
            if data_type not in {VALUE_TYPE, QTY_TYPE}:
                continue

            key = SourceKey(firma=normalize_text(firma), year=year, store_name=normalize_text(store_name))
            record = records.get(key)
            if record is None:
                record = SourceRecord(
                    firma=firma,
                    year=year,
                    store_name=store_name,
                    manager=str(row[3]).strip() if row[3] else None,
                    source_file=path.name,
                    had_inchis_prefix="INCHIS" in store_name.upper(),
                    values={},
                    quantities={},
                )
                records[key] = record
            elif record.source_file != path.name:
                duplicate_files.append(f"{path.name}: {firma} / {year} / {store_name}")

            for column_index, month_number in MONTH_COLUMNS.items():
                amount = numeric(row[column_index])
                if data_type == QTY_TYPE:
                    record.quantities[month_number] = int(round(amount))
                else:
                    record.values[month_number] = amount
            seen_in_file += 1

        workbook.close()
        print(f"{path.name}: {seen_in_file} source rows read")

    return records, duplicate_files


async def build_store_map(conn: asyncpg.Connection) -> dict[tuple[str, str], list[asyncpg.Record]]:
    rows = await conn.fetch(
        """
        SELECT site_code, firma, locatie
        FROM stores
        WHERE locatie NOT ILIKE 'TR %'
        """
    )
    mapping: dict[tuple[str, str], list[asyncpg.Record]] = defaultdict(list)
    for row in rows:
        mapping[(normalize_text(row["firma"]), normalize_text(row["locatie"]))].append(row)
    return mapping


def build_import_rows(
    records: dict[SourceKey, SourceRecord],
    store_map: dict[tuple[str, str], list[asyncpg.Record]],
) -> tuple[list[tuple], list[str], list[str]]:
    rows: list[tuple] = []
    unmatched: list[str] = []
    ambiguous: list[str] = []

    for key, record in sorted(records.items(), key=lambda item: (item[0].year, item[0].firma, item[0].store_name)):
        matches = store_map.get((key.firma, key.store_name), [])
        if not matches:
            unmatched.append(f"{record.firma} / {record.year} / {record.store_name}")
            continue
        if len(matches) > 1:
            ambiguous.append(
                f"{record.firma} / {record.year} / {record.store_name}: "
                + ", ".join(f"{row['site_code']}={row['locatie']}" for row in matches)
            )
            continue
        store = matches[0]
        for month_number in range(1, 13):
            value = round(record.values.get(month_number, 0.0), 2)
            qty = int(record.quantities.get(month_number, 0))
            if value == 0 and qty == 0:
                continue
            import_month = f"{record.year:04d}-{month_number:02d}"
            rows.append((
                store["site_code"],
                import_month,
                store["firma"],
                value,
                qty,
                record.source_file,
                record.store_name,
                record.manager,
                record.had_inchis_prefix,
            ))

    return rows, unmatched, ambiguous


async def main(apply: bool) -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("EROARE: DATABASE_URL lipseste din .env")
        sys.exit(1)

    source_records, duplicate_files = load_source_files()
    print(f"Unique source store-years: {len(source_records)}")
    if duplicate_files:
        print(f"Duplicate rows skipped across source files: {len(duplicate_files)}")

    conn = await asyncpg.connect(database_url)
    try:
        store_map = await build_store_map(conn)
        rows, unmatched, ambiguous = build_import_rows(source_records, store_map)

        print(f"Prepared rows: {len(rows)}")
        print(f"Unmatched source store-years: {len(unmatched)}")
        for item in unmatched[:80]:
            print(f"  UNMATCHED {item}")
        print(f"Ambiguous source store-years: {len(ambiguous)}")
        for item in ambiguous[:40]:
            print(f"  AMBIGUOUS {item}")

        by_year: dict[int, dict[str, float]] = defaultdict(lambda: {"rows": 0, "value": 0.0, "qty": 0})
        for _, import_month, _, value, qty, *_ in rows:
            year = int(import_month[:4])
            by_year[year]["rows"] += 1
            by_year[year]["value"] += float(value)
            by_year[year]["qty"] += int(qty)
        print("Summary by year:")
        for year, data in sorted(by_year.items()):
            print(
                f"  {year}: {int(data['rows'])} rows | "
                f"{data['value']:,.2f} RON | {int(data['qty']):,} buc"
            )

        if not apply:
            print("*** DRY RUN - no database writes. Use --apply to import. ***")
            return
        if ambiguous:
            raise RuntimeError("Refuz importul: exista potriviri ambigue.")

        async with conn.transaction():
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS historical_monthly_sales (
                    site_code TEXT NOT NULL REFERENCES stores(site_code),
                    import_month TEXT NOT NULL,
                    firma TEXT NOT NULL,
                    total_value NUMERIC(14, 2) NOT NULL DEFAULT 0,
                    total_qty INTEGER NOT NULL DEFAULT 0,
                    source_file TEXT NOT NULL,
                    source_store_name TEXT NOT NULL,
                    source_manager TEXT,
                    had_inchis_prefix BOOLEAN NOT NULL DEFAULT false,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (site_code, import_month, firma)
                )
                """
            )
            await conn.executemany(
                """
                INSERT INTO historical_monthly_sales (
                    site_code, import_month, firma, total_value, total_qty,
                    source_file, source_store_name, source_manager, had_inchis_prefix
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (site_code, import_month, firma) DO UPDATE
                SET total_value = EXCLUDED.total_value,
                    total_qty = EXCLUDED.total_qty,
                    source_file = EXCLUDED.source_file,
                    source_store_name = EXCLUDED.source_store_name,
                    source_manager = EXCLUDED.source_manager,
                    had_inchis_prefix = EXCLUDED.had_inchis_prefix
                """,
                rows,
            )
            count = await conn.fetchval("SELECT COUNT(*) FROM historical_monthly_sales")
        print(f"Import complete. historical_monthly_sales rows: {count}")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import monthly historical store totals")
    parser.add_argument("--apply", action="store_true", help="Write rows to the database")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
