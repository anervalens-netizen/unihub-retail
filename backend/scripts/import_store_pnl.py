#!/usr/bin/env python3
"""Auditeaza si importa P&L-urile lunare pe magazin.

Implicit ruleaza read-only. Foloseste ``--apply`` numai dupa verificarea
raportului; scriptul importa exclusiv valori reale si nu genereaza estimari.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import asyncpg
import xlrd
from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_DIR / "data" / "P&L"
VALID_CODES = {"v1", "v11", "v2", "v3", "c1", "c11", "c2", "c3", "c4", "c5", "c6", "a1"}


@dataclass(frozen=True)
class PnlRow:
    company_name: str
    period: date
    source_site_code: str
    source_location_name: str
    category_code: str
    category_name: str
    amount: Decimal
    source_file: str
    source_sha256: str


@dataclass(frozen=True)
class WorkbookData:
    path: Path
    sha256: str
    company_name: str
    periods: tuple[date, ...]
    rows: tuple[PnlRow, ...]
    populated_months: int
    numeric_cells: int


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def company_from_title(value: object) -> str:
    title = str(value).upper()
    if "MOBICELL" in title:
        return "Mobicell"
    if "MOBIUP" in title:
        return "Mobiup"
    raise ValueError(f"Companie necunoscuta in titlul P&L: {value!r}")


def parse_workbook(path: Path, root: Path) -> WorkbookData:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    workbook = xlrd.open_workbook(path)
    summary = workbook.sheet_by_name("P&L Magazine")
    detail = workbook.sheet_by_name("Detaliere")
    company = company_from_title(summary.cell_value(0, 1))

    periods: list[date] = []
    for column in range(5, 17):
        value = summary.cell_value(1, column)
        moment = xlrd.xldate_as_datetime(value, workbook.datemode)
        periods.append(date(moment.year, moment.month, 1))

    source_file = str(path.relative_to(root))
    rows: list[PnlRow] = []
    months_with_values: set[date] = set()
    for row_index in range(1, detail.nrows):
        category = str(detail.cell_value(row_index, 1)).strip().lower()
        if category not in VALID_CODES:
            continue
        site_code = str(detail.cell_value(row_index, 2)).strip()
        location = str(detail.cell_value(row_index, 3)).strip()
        category_name = str(detail.cell_value(row_index, 4)).strip()
        if not site_code or not location:
            continue
        for month_index, period in enumerate(periods):
            value = detail.cell_value(row_index, 6 + month_index)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            # A month containing only template zeroes is not an actual month.
            if abs(float(value)) > 1e-9:
                months_with_values.add(period)
            rows.append(
                PnlRow(
                    company_name=company,
                    period=period,
                    source_site_code=site_code,
                    source_location_name=location,
                    category_code=category,
                    category_name=category_name,
                    amount=money(float(value)),
                    source_file=source_file,
                    source_sha256=digest,
                )
            )

    # Remove template cells from months without any real amount.
    rows = [row for row in rows if row.period in months_with_values]
    return WorkbookData(
        path=path,
        sha256=digest,
        company_name=company,
        periods=tuple(periods),
        rows=tuple(rows),
        populated_months=len(months_with_values),
        numeric_cells=len(rows),
    )


def discover(input_dir: Path) -> tuple[list[WorkbookData], list[tuple[Path, Path]]]:
    unique: dict[str, WorkbookData] = {}
    duplicates: list[tuple[Path, Path]] = []
    for path in sorted(input_dir.rglob("*.xls")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in unique:
            duplicates.append((path, unique[digest].path))
            continue
        unique[digest] = parse_workbook(path, input_dir)
    return list(unique.values()), duplicates


def select_snapshots(workbooks: list[WorkbookData]) -> tuple[list[WorkbookData], list[WorkbookData]]:
    groups: dict[tuple[str, int], list[WorkbookData]] = defaultdict(list)
    for workbook in workbooks:
        years = {period.year for period in workbook.periods}
        if len(years) != 1:
            raise ValueError(f"Fisier cu ani amestecati: {workbook.path}")
        groups[(workbook.company_name, next(iter(years)))].append(workbook)

    selected: list[WorkbookData] = []
    superseded: list[WorkbookData] = []
    for candidates in groups.values():
        candidates.sort(key=lambda item: (item.populated_months, item.numeric_cells, str(item.path)))
        selected.append(candidates[-1])
        superseded.extend(candidates[:-1])
    return sorted(selected, key=lambda item: (item.company_name, item.periods[0])), superseded


def merged_rows(selected: list[WorkbookData]) -> list[PnlRow]:
    result: dict[tuple[str, date, str, str], PnlRow] = {}
    for workbook in selected:
        for row in workbook.rows:
            key = (row.company_name, row.period, row.source_site_code, row.category_code)
            if key in result:
                previous = result[key]
                result[key] = PnlRow(
                    company_name=row.company_name,
                    period=row.period,
                    source_site_code=row.source_site_code,
                    source_location_name=previous.source_location_name,
                    category_code=row.category_code,
                    category_name=previous.category_name,
                    amount=previous.amount + row.amount,
                    source_file=row.source_file,
                    source_sha256=row.source_sha256,
                )
            else:
                result[key] = row
    return sorted(result.values(), key=lambda row: (row.period, row.company_name, row.source_site_code, row.category_code))


def print_audit(selected: list[WorkbookData], superseded: list[WorkbookData], duplicates: list[tuple[Path, Path]], rows: list[PnlRow]) -> None:
    print(f"Duplicate binare: {len(duplicates)}")
    for duplicate, original in duplicates:
        print(f"  DUPLICAT {duplicate} == {original}")
    print(f"Snapshot-uri depasite: {len(superseded)}")
    for workbook in sorted(superseded, key=lambda item: str(item.path)):
        print(f"  DEPASIT {workbook.path.name}: {workbook.populated_months} luni")
    print("Snapshot-uri selectate:")
    for workbook in selected:
        periods = sorted({row.period for row in workbook.rows})
        span = f"{periods[0]:%Y-%m}..{periods[-1]:%Y-%m}" if periods else "fara date"
        print(f"  {workbook.company_name}: {workbook.path.name} ({span}, {len(workbook.rows)} valori)")

    by_period: dict[date, list[PnlRow]] = defaultdict(list)
    for row in rows:
        by_period[row.period].append(row)
    print("Acoperire extrasa:")
    for period, period_rows in sorted(by_period.items()):
        companies = sorted({row.company_name for row in period_rows})
        sites = len({(row.company_name, row.source_site_code) for row in period_rows})
        print(f"  {period:%Y-%m}: {len(period_rows)} valori, {sites} magazine, {', '.join(companies)}")


async def apply_rows(rows: list[PnlRow]) -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste din .env")
    connection = await asyncpg.connect(database_url)
    try:
        async with connection.transaction():
            await connection.executemany(
                """
                INSERT INTO store_pnl_monthly (
                    company_name, period, source_site_code, source_location_name,
                    category_code, category_name, amount, data_kind, source_file, source_sha256
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'actual', $8, $9)
                ON CONFLICT (company_name, period, source_site_code, category_code, data_kind)
                DO UPDATE SET
                    source_location_name = EXCLUDED.source_location_name,
                    category_name = EXCLUDED.category_name,
                    amount = EXCLUDED.amount,
                    source_file = EXCLUDED.source_file,
                    source_sha256 = EXCLUDED.source_sha256,
                    imported_at = now()
                """,
                [
                    (
                        row.company_name, row.period, row.source_site_code, row.source_location_name,
                        row.category_code, row.category_name, row.amount, row.source_file, row.source_sha256,
                    )
                    for row in rows
                ],
            )
        print(f"Import finalizat: {len(rows)} valori actuale.")
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditeaza/importa P&L lunar pe magazin.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--apply", action="store_true", help="Scrie valorile in PostgreSQL.")
    args = parser.parse_args()
    load_dotenv(REPO_DIR / ".env")

    workbooks, duplicates = discover(args.input_dir)
    selected, superseded = select_snapshots(workbooks)
    rows = merged_rows(selected)
    print_audit(selected, superseded, duplicates, rows)
    if args.apply:
        asyncio.run(apply_rows(rows))
    else:
        print("Dry-run: baza de date nu a fost modificata. Foloseste --apply dupa aplicarea migrarii 021.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, xlrd.XLRDError) as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        raise SystemExit(1)
