#!/usr/bin/env python3
"""Stage Finance-authorized P&L generations; P0-B promotion is disabled.

This tool deliberately has no filename/density selection and never consults
``DATABASE_URL``.  A staged bundle is accepted only when every observed source
matches the external authority manifest byte-for-byte.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Sequence
from uuid import UUID

import asyncpg
import xlrd
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db.connection import connect_database_url, verify_database_connection_authority  # noqa: E402

from services.store_pnl_import import (  # noqa: E402
    AuthorityManifest,
    PnlImportError,
    PnlRow,
    PnlScope,
    apply_generation,
    parse_authority_manifest,
    rollback_generation,
    stage_generation,
    validate_scope_candidate,
)


REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_DIR / "data" / "P&L"
VALID_CODES = {"v1", "v11", "v2", "v3", "c1", "c11", "c2", "c3", "c4", "c5", "c6", "a1"}
REVENUE_CODES = {"v1", "v11", "v2", "v3"}
UNALLOCATED_SOURCE = "__FINANCE_UNALLOCATED__"
UNALLOCATED_LOCATION = "Diferenta consolidat Finance nealocata pe magazine"


@dataclass(frozen=True)
class WorkbookData:
    path: Path
    source_file: str
    sha256: str
    company_name: str
    periods: tuple[date, ...]
    rows: tuple[PnlRow, ...]
    consolidated_rows: tuple[PnlRow, ...]


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def company_from_title(value: object) -> str:
    title = str(value).upper()
    if "MOBICELL" in title:
        return "Mobicell"
    if "MOBIUP" in title:
        return "Mobiup"
    raise PnlImportError(f"Companie necunoscuta in titlul P&L: {value!r}")


def detail_category(detail: xlrd.sheet.Sheet, row_index: int) -> str:
    direct = str(detail.cell_value(row_index, 1)).strip().lower()
    if direct in VALID_CODES:
        return direct
    composite = str(detail.cell_value(row_index, 5)).strip().lower()
    inferred = composite.split("-", 1)[0]
    return inferred if inferred in VALID_CODES else direct


def parse_workbook(path: Path, root: Path) -> WorkbookData:
    """Parse the exact bytes whose digest is compared with authority.

    ``xlrd`` receives the already-hashed bytes, so a concurrent file mutation
    cannot make the parser consume different content than the authenticated
    source hash.
    """
    if path.is_symlink() or not path.is_file():
        raise PnlImportError(f"Sursa Finance trebuie sa fie fisier regulat: {path}")
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    workbook = xlrd.open_workbook(file_contents=payload)
    summary = workbook.sheet_by_name("P&L Magazine")
    detail = workbook.sheet_by_name("Detaliere")
    company = company_from_title(summary.cell_value(0, 1))

    periods: list[date] = []
    for column in range(5, 17):
        value = summary.cell_value(1, column)
        moment = xlrd.xldate_as_datetime(value, workbook.datemode)
        periods.append(date(moment.year, moment.month, 1))

    source_file = path.relative_to(root).as_posix()
    rows: list[PnlRow] = []
    months_with_values: set[date] = set()
    for row_index in range(1, detail.nrows):
        category = detail_category(detail, row_index)
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
    rows = [row for row in rows if row.period in months_with_values]
    consolidated_rows = parse_consolidated_rows(
        summary, company, periods, source_file, digest, months_with_values
    )
    return WorkbookData(
        path=path,
        source_file=source_file,
        sha256=digest,
        company_name=company,
        periods=tuple(periods),
        rows=tuple(rows),
        consolidated_rows=tuple(consolidated_rows),
    )


def summary_category_code(code_value: object, name_value: object) -> str | None:
    code = str(code_value).strip().lower()
    if code in VALID_CODES:
        return code
    if code and not code.replace(".", "", 1).isdigit():
        return None
    normalized = " ".join(str(name_value).lower().split())
    labels = (
        ("venituri din vanzari cartele", "v1"), ("venituri din accesor", "v11"),
        ("venituri din incarcare", "v2"), ("alte venituri", "v3"),
        ("marfa cartele", "c1"), ("marfa accesori", "c11"),
        ("cheltuieli cu incarcare", "c2"), ("cost salari", "c3"),
        ("chirii", "c4"), ("utilit", "c5"), ("alte costuri", "c6"),
        ("amortizare", "a1"),
    )
    return next((category for label, category in labels if label in normalized), None)


def parse_consolidated_rows(
    summary: xlrd.sheet.Sheet,
    company: str,
    periods: Sequence[date],
    source_file: str,
    digest: str,
    populated_months: set[date],
) -> list[PnlRow]:
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
                company_name=company, period=period, source_site_code=UNALLOCATED_SOURCE,
                source_location_name=UNALLOCATED_LOCATION, category_code=category,
                category_name=category_name, amount=money(float(value)),
                source_file=source_file, source_sha256=digest,
            ))
    return rows


def discover(input_dir: Path) -> list[WorkbookData]:
    root = input_dir.resolve()
    if not root.is_dir():
        raise PnlImportError(f"Director Finance inexistent: {input_dir}")
    paths = sorted(root.rglob("*.xls"))
    if not paths:
        raise PnlImportError("Nu exista fisiere .xls in directorul Finance declarat.")
    return [parse_workbook(path, root) for path in paths]


def merged_rows(rows: Sequence[PnlRow]) -> list[PnlRow]:
    result: dict[tuple[str, date, str, str], PnlRow] = {}
    for row in rows:
        key = (row.company_name, row.period, row.source_site_code, row.category_code)
        previous = result.get(key)
        if previous is None:
            result[key] = row
            continue
        if (previous.source_file, previous.source_sha256) != (row.source_file, row.source_sha256):
            raise PnlImportError("Nu sunt permise linii P&L mixate intre surse.")
        result[key] = PnlRow(
            company_name=row.company_name, period=row.period,
            source_site_code=row.source_site_code,
            source_location_name=previous.source_location_name,
            category_code=row.category_code, category_name=previous.category_name,
            amount=previous.amount + row.amount, source_file=row.source_file,
            source_sha256=row.source_sha256,
        )
    return sorted(result.values(), key=lambda row: (row.company_name, row.period, row.source_site_code, row.category_code))


def unallocated_rows(detail_rows: Sequence[PnlRow], workbook: WorkbookData, scope: PnlScope) -> list[PnlRow]:
    """Calculate only a same-bundle consolidated-minus-detail delta.

    A summary lower than its own detail is not silently ignored: that bundle is
    invalid as a complete Finance snapshot.
    """
    company, period = scope
    detailed_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for row in detail_rows:
        detailed_totals[row.category_code] += row.amount
    totals = [row for row in workbook.consolidated_rows if (row.company_name, row.period) == scope]
    if not totals:
        return []
    summary_revenue = sum((row.amount for row in totals if row.category_code in REVENUE_CODES), Decimal("0.00"))
    detail_revenue = sum((detailed_totals[code] for code in REVENUE_CODES), Decimal("0.00"))
    if summary_revenue + Decimal("0.01") < detail_revenue:
        raise PnlImportError(f"Consolidatul Finance este sub detaliu pentru {company} {period:%Y-%m}.")
    result: list[PnlRow] = []
    for total in totals:
        delta = total.amount - detailed_totals[total.category_code]
        if abs(delta) <= Decimal("0.01"):
            continue
        result.append(PnlRow(
            company_name=total.company_name, period=total.period,
            source_site_code=UNALLOCATED_SOURCE,
            source_location_name=UNALLOCATED_LOCATION,
            category_code=total.category_code, category_name=total.category_name,
            amount=delta, source_file=total.source_file, source_sha256=total.source_sha256,
        ))
    return result


def materialize_authority_rows(
    workbooks: Sequence[WorkbookData], authority: AuthorityManifest
) -> dict[PnlScope, list[PnlRow]]:
    """Return one complete, non-mixed candidate for every declared scope."""
    by_source: dict[tuple[str, str], WorkbookData] = {}
    for workbook in workbooks:
        source_key = (workbook.source_file, workbook.sha256)
        if source_key in by_source:
            raise PnlImportError("Authority nu permite duplicate binare ori cai ambigue.")
        by_source[source_key] = workbook
    declared = {(scope.source_path, scope.source_sha256) for scope in authority.scopes}
    if set(by_source) != declared:
        raise PnlImportError("Sursele observate nu sunt exact sursele declarate de Finance.")

    scopes_by_source: dict[tuple[str, str], list[PnlScope]] = defaultdict(list)
    authority_by_scope = {scope.key: scope for scope in authority.scopes}
    for scope in authority.scopes:
        scopes_by_source[(scope.source_path, scope.source_sha256)].append(scope.key)
    candidates: dict[PnlScope, list[PnlRow]] = {}
    for source_key, workbook in by_source.items():
        declared_scopes = set(scopes_by_source[source_key])
        observed_scopes = {(row.company_name, row.period) for row in workbook.rows}
        if observed_scopes != declared_scopes:
            raise PnlImportError("Fisierul Finance contine luni neaprobate sau lipsesc luni declarate.")
        for scope_key in declared_scopes:
            scope = authority_by_scope[scope_key]
            if workbook.company_name != scope.company_name:
                raise PnlImportError("Compania din sursa Finance nu corespunde authority manifest.")
            detail = merged_rows([row for row in workbook.rows if (row.company_name, row.period) == scope_key])
            candidate = [*detail, *unallocated_rows(detail, workbook, scope_key)]
            validate_scope_candidate(scope, candidate)
            candidates[scope_key] = candidate
    return candidates


def read_authority_manifest(path: Path) -> AuthorityManifest:
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PnlImportError(f"Authority manifest invalid: {path}") from exc
    return parse_authority_manifest(payload)


async def connect_finance() -> asyncpg.Connection:
    dsn = os.environ.get("FINANCE_PNL_DATABASE_URL", "")
    if not dsn or dsn == os.environ.get("DATABASE_URL"):
        raise PnlImportError("Este necesar FINANCE_PNL_DATABASE_URL dedicat, diferit de DATABASE_URL.")
    connection = await connect_database_url(
        dsn, application_name="unihub-retail-finance-import"
    )
    try:
        await verify_database_connection_authority(connection, "finance_import")
        return connection
    except RuntimeError as exc:
        await connection.close()
        raise PnlImportError(
            "Conexiunea P&L trebuie sa foloseasca exclusiv principalul Finance dedicat."
        ) from exc
    except BaseException:
        await connection.close()
        raise


def operational_apply_no_go() -> None:
    raise PnlImportError(
        "P0-B operational NO-GO: promote/rollback P&L raman dezactivate pana la aprobarea live separata."
    )


async def run_stage(input_dir: Path, authority_path: Path) -> None:
    authority = read_authority_manifest(authority_path)
    candidates = materialize_authority_rows(discover(input_dir), authority)
    connection = await connect_finance()
    try:
        result = await stage_generation(connection, authority, candidates)
    finally:
        await connection.close()
    print(json.dumps({
        "generation_id": str(result.generation_id),
        "generation_manifest_sha256": result.generation_manifest_sha256,
        "authority_manifest_sha256": authority.sha256,
        "scopes": [f"{company}:{period.isoformat()}" for company, period in sorted(candidates)],
    }, sort_keys=True))


async def run_apply(generation_id: UUID, expected_manifest_sha256: str) -> None:
    operational_apply_no_go()
    connection = await connect_finance()
    try:
        print(json.dumps(await apply_generation(connection, generation_id, expected_manifest_sha256), sort_keys=True))
    finally:
        await connection.close()


async def run_rollback(generation_id: UUID, expected_manifest_sha256: str) -> None:
    operational_apply_no_go()
    connection = await connect_finance()
    try:
        result = await rollback_generation(connection, generation_id, expected_manifest_sha256)
    finally:
        await connection.close()
    print(json.dumps({"generation_id": str(result.generation_id), "generation_manifest_sha256": result.generation_manifest_sha256}, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stageaza bundle-uri P&L explicit aprobate de Finance.")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--stage", action="store_true", help="Stage immutable din authority manifest.")
    operation.add_argument("--apply-generation", type=UUID, metavar="UUID", help="Promoveaza generatie staged (P0-B NO-GO).")
    operation.add_argument("--rollback-generation", type=UUID, metavar="UUID", help="Publica generatie inversa (P0-B NO-GO).")
    parser.add_argument("--authority-manifest", type=Path)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--expected-manifest-sha", metavar="SHA256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(REPO_DIR / ".env")
    if args.stage:
        if args.authority_manifest is None:
            raise PnlImportError("--stage necesita --authority-manifest.")
        if args.expected_manifest_sha is not None:
            raise PnlImportError("--expected-manifest-sha se foloseste numai pentru promote/rollback.")
        asyncio.run(run_stage(args.input_dir, args.authority_manifest))
    else:
        if args.authority_manifest is not None:
            raise PnlImportError("Authority manifest se foloseste numai la --stage.")
        if not args.expected_manifest_sha:
            raise PnlImportError("Promote/rollback necesita --expected-manifest-sha.")
        generation_id = args.apply_generation or args.rollback_generation
        assert generation_id is not None
        if args.apply_generation:
            asyncio.run(run_apply(generation_id, args.expected_manifest_sha))
        else:
            asyncio.run(run_rollback(generation_id, args.expected_manifest_sha))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PnlImportError, ValueError, xlrd.XLRDError) as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        raise SystemExit(1)
