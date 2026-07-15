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
REVENUE_CODES = {"v1", "v11", "v2", "v3"}
UNALLOCATED_SOURCE = "__FINANCE_UNALLOCATED__"
UNALLOCATED_LOCATION = "Diferenta consolidat Finance nealocata pe magazine"


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
    consolidated_rows: tuple[PnlRow, ...]
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
    consolidated_rows = parse_consolidated_rows(
        summary,
        company,
        periods,
        source_file,
        digest,
        months_with_values,
    )
    return WorkbookData(
        path=path,
        sha256=digest,
        company_name=company,
        periods=tuple(periods),
        rows=tuple(rows),
        consolidated_rows=tuple(consolidated_rows),
        populated_months=len(months_with_values),
        numeric_cells=len(rows),
    )


def summary_category_code(code_value: object, name_value: object) -> str | None:
    code = str(code_value).strip().lower()
    if code in VALID_CODES:
        return code
    # Summary-only subtotals (for example v10 "alte venituri din exploatare")
    # are not store P&L accounting categories and must not overwrite v3.
    if code and not code.replace(".", "", 1).isdigit():
        return None
    normalized = " ".join(str(name_value).lower().split())
    if "venituri din vanzari cartele" in normalized:
        return "v1"
    if "venituri din accesor" in normalized:
        return "v11"
    if "venituri din incarcare" in normalized:
        return "v2"
    if "alte venituri" in normalized:
        return "v3"
    if "marfa cartele" in normalized:
        return "c1"
    if "marfa accesori" in normalized:
        return "c11"
    if "cheltuieli cu incarcare" in normalized:
        return "c2"
    if "cost salari" in normalized:
        return "c3"
    if "chirii" in normalized:
        return "c4"
    if "utilit" in normalized:
        return "c5"
    if "alte costuri" in normalized:
        return "c6"
    if "amortizare" in normalized:
        return "a1"
    return None


def parse_consolidated_rows(
    summary: xlrd.sheet.Sheet,
    company: str,
    periods: list[date],
    source_file: str,
    digest: str,
    populated_months: set[date],
) -> list[PnlRow]:
    """Read the Finance consolidated totals without rewriting store detail.

    Some workbooks reconcile to company totals that contain locations absent
    from ``Detaliere``. The delta is persisted as an explicit unallocated
    Finance bucket so company P&L remains faithful to the supplied workbook.
    """
    rows: list[PnlRow] = []
    for row_index in range(summary.nrows):
        category = summary_category_code(summary.cell_value(row_index, 2), summary.cell_value(row_index, 3))
        if category is None:
            continue
        category_name = str(summary.cell_value(row_index, 3)).strip() or category
        for month_index, period in enumerate(periods):
            value = summary.cell_value(row_index, 5 + month_index)
            if period not in populated_months or not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            rows.append(PnlRow(
                company_name=company,
                period=period,
                source_site_code=UNALLOCATED_SOURCE,
                source_location_name=UNALLOCATED_LOCATION,
                category_code=category,
                category_name=category_name,
                amount=money(float(value)),
                source_file=source_file,
                source_sha256=digest,
            ))
    return rows


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


def unallocated_rows(detail_rows: list[PnlRow], workbooks: list[WorkbookData]) -> list[PnlRow]:
    """Return trustworthy Finance consolidated-minus-detail deltas.

    ``P&L Magazine`` is driven by an Excel location selector. Some supplied
    snapshots were saved with one store selected, while ``Detaliere`` still
    contains the complete company data. A summary can therefore be used as a
    company total only when its revenue is at least the selected detail total.
    Among valid snapshots, prefer the most complete one for that month.
    """
    detailed_totals: dict[tuple[str, date, str], Decimal] = defaultdict(Decimal)
    for row in detail_rows:
        detailed_totals[(row.company_name, row.period, row.category_code)] += row.amount

    candidates: dict[tuple[str, date], list[tuple[WorkbookData, list[PnlRow]]]] = defaultdict(list)
    for workbook in workbooks:
        by_period: dict[date, list[PnlRow]] = defaultdict(list)
        for total in workbook.consolidated_rows:
            by_period[total.period].append(total)
        for period, totals in by_period.items():
            detail_revenue = sum(
                detailed_totals[(workbook.company_name, period, code)]
                for code in REVENUE_CODES
            )
            summary_revenue = sum(
                total.amount for total in totals if total.category_code in REVENUE_CODES
            )
            # A lower summary is a store-filtered worksheet, not a consolidated
            # company total. The one-cent tolerance only absorbs Excel rounding.
            if summary_revenue + Decimal("0.01") < detail_revenue:
                continue
            candidates[(workbook.company_name, period)].append((workbook, totals))

    result: list[PnlRow] = []
    for period_candidates in candidates.values():
        workbook, totals = max(
            period_candidates,
            key=lambda item: (item[0].populated_months, item[0].numeric_cells, str(item[0].path)),
        )
        for total in totals:
            delta = total.amount - detailed_totals[(total.company_name, total.period, total.category_code)]
            if abs(delta) <= Decimal("0.01"):
                continue
            result.append(PnlRow(
                company_name=total.company_name,
                period=total.period,
                source_site_code=UNALLOCATED_SOURCE,
                source_location_name=UNALLOCATED_LOCATION,
                category_code=total.category_code,
                category_name=total.category_name,
                amount=delta,
                source_file=total.source_file,
                source_sha256=total.source_sha256,
            ))
    return sorted(result, key=lambda row: (row.period, row.company_name, row.category_code))


def print_audit(selected: list[WorkbookData], superseded: list[WorkbookData], duplicates: list[tuple[Path, Path]], rows: list[PnlRow], reconciliation: list[PnlRow]) -> None:
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
    print(f"Diferente consolidat Finance nealocate pe magazine: {len(reconciliation)} valori")


async def apply_rows(rows: list[PnlRow], reconciliation: list[PnlRow]) -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste din .env")
    connection = await asyncpg.connect(database_url)
    try:
        async with connection.transaction():
            imported_years = sorted({(row.company_name, row.period.year) for row in rows})
            for company, year in imported_years:
                await connection.execute(
                    """
                    DELETE FROM store_pnl_monthly
                    WHERE data_kind = 'actual'
                      AND company_name = $1
                      AND period >= make_date($2, 1, 1)
                      AND period < make_date($2 + 1, 1, 1)
                    """,
                    company,
                    year,
                )
            await connection.execute(
                "DELETE FROM store_pnl_monthly WHERE data_kind = 'actual' AND source_site_code = $1",
                UNALLOCATED_SOURCE,
            )
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
                    for row in [*rows, *reconciliation]
                ],
            )
            await connection.execute(
                """
                DELETE FROM store_pnl_monthly estimate
                WHERE estimate.data_kind = 'estimated'
                  AND EXISTS (
                      SELECT 1
                      FROM store_pnl_monthly actual
                      WHERE actual.data_kind = 'actual'
                        AND actual.company_name = estimate.company_name
                        AND actual.period = estimate.period
                  )
                """
            )
        print(f"Import finalizat: {len(rows)} valori detaliate + {len(reconciliation)} diferente consolidate actuale.")
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
    # Consolidated totals may come from an older, still trustworthy snapshot
    # even when a newer detail snapshot was saved with one store selected.
    reconciliation = unallocated_rows(rows, workbooks)
    print_audit(selected, superseded, duplicates, rows, reconciliation)
    if args.apply:
        asyncio.run(apply_rows(rows, reconciliation))
    else:
        print("Dry-run: baza de date nu a fost modificata. Foloseste --apply dupa aplicarea migrarii 021.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, xlrd.XLRDError) as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        raise SystemExit(1)
