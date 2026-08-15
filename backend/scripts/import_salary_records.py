#!/usr/bin/env python3
"""Importa fisierele lunare HR de salarii in `salary_records`.
Exemplu:
    cd /opt/Mobiup/unihub-retail
    backend/venv/bin/python backend/scripts/import_salary_records.py \
        --year 2026 --month 5 \
        --mobiup-file "/opt/Mobiup/docs/comisioane/MOBI COMISIOANE AGENTI MAI.xls" \
        --mobicell-file "/opt/Mobiup/docs/comisioane/COMISIOANE AGENTI Mobicell mai.xls" \
        --apply
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

CNP_WEIGHTS = (2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9)
REQUIRED_COMPANIES = ("Mobiup", "Mobicell")

import asyncpg
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.spreadsheet_readers import read_spreadsheet_frame
from salary_import_approval import (
    SalaryImportApprovalError,
    ValidatedApproval,
    canonical_json_sha256,
    load_and_validate_approval_artifact,
    require_apply_inputs,
    scan_runtime_salary_surfaces,
    validate_audit_envelope,
    validate_dry_run_manifest,
)
from salary_identity import get_salary_person_id_key, make_salary_person_id
from salary_import_persistence import persist_salary_records

REPO_DIR = Path(__file__).resolve().parents[2]


LOCATION_ALIASES: dict[tuple[str, str], str | None] = {
    ("Mobiup", "AFI BRASOV"): "BVAFIPLC",
    ("Mobiup", "AFI COTROCENI"): "COTROCENI",
    ("Mobiup", "ALBA CAROLINA"): "CAROLINAMALL",
    ("Mobiup", "ARAD"): "AFIARAD",
    ("Mobiup", "AUCHAN MILITARI"): "AUCHMIL2",
    ("Mobiup", "BALOTESTI"): "MCRFBAL",
    ("Mobiup", "BRAILA"): "BRCRF",
    ("Mobiup", "BRASOV CORESI"): "CORESI",
    ("Mobiup", "BUZAU"): "BUZAURORA",
    ("Mobiup", "CARREFOUR FEERIA"): "CRFFEER",
    ("Mobiup", "CLUJ"): "CJPPOL",
    ("Mobiup", "CONSTANTA CITY"): "CTCITYPRK",
    ("Mobiup", "CONSTANTA TOM CARREFOUR"): "CTCRFTOM",
    ("Mobiup", "CONSTANTA VIVO"): "CTAUCH",
    ("Mobiup", "CRAIOVA ELECTROPUTERE"): "CRELECTRO",
    ("Mobiup", "DEVA"): "DVSHP",
    ("Mobiup", "IASI FELICIA"): "ISCRFEL",
    ("Mobiup", "IASI MOLDOVA MALL"): "ISMOLDMALL",
    ("Mobiup", "MEGA MALL"): "MEGAMALL",
    ("Mobiup", "ORADEA AUCHAN"): "ORAUCH",
    ("Mobiup", "PARK LAKE"): "PRKLK",
    ("Mobiup", "PIATRA NEAMT"): "PITRNMT",
    ("Mobiup", "PITESTI MALL"): "ARGMLL",
    ("Mobiup", "PLOIESTI AFI"): "PLAFI",
    ("Mobiup", "PLOIESTI CARREFOUR"): "PLCRF",
    ("Mobiup", "PROMENDADA"): "PROM",
    ("Mobiup", "PROMENADA"): "PROM",
    ("Mobiup", "SIBIU CARREFOUR"): "SBCRF",
    ("Mobiup", "SIBIU PROMENADA"): "MSBFEST",
    ("Mobiup", "SUCEAVA IULIUS"): "SVIULMALL",
    ("Mobiup", "SUCEAVA SHOPPING CITY"): "SVCITY",
    ("Mobiup", "SUN PLAZA"): "SUNPLZ",
    ("Mobiup", "TARGOVISTE"): "TGVMLL",
    ("Mobiup", "TEAM LEADER"): None,
    ("Mobiup", "TG MURES"): "TGMUSHO",
    ("Mobiup", "TIMISOARA AUCHAN NORD"): "TMACUH",
    ("Mobiup", "UNIREA"): "UNIRII",
    ("Mobiup", "VULCAN"): "CRFVUL",
    ("Mobicell", "AFI COTROCENI"): "AFICOTRO",
    ("Mobicell", "ALBA IULIA"): "ALBACAROLINA",
    ("Mobicell", "AUCHAN MILITARI"): "AUCHMILI",
    ("Mobicell", "BAIA MARE"): "BAIAMAREMC",
    ("Mobicell", "BIRLAD CARREFOUR"): "MBARLAD",
    ("Mobicell", "BRAILA"): "BRPROM",
    ("Mobicell", "BRASOV CARREFOUR"): "CBRASOV",
    ("Mobicell", "BRASOV MAGNOLIA"): "BVMAGNO",
    ("Mobicell", "BUZAU AURORA"): "BZAURORA",
    ("Mobicell", "CLUJ IULIUS MALL"): "CJIULMALL",
    ("Mobicell", "CLUJ POLUS"): "CLUJCFPOL",
    ("Mobicell", "CONSTANTA CITY"): "CCTCIT",
    ("Mobicell", "CONSTANTA CORA"): "CTCORA",
    ("Mobicell", "CONSTANTA VIVO"): "CTVIVO",
    ("Mobicell", "CORA ALEXANDRIEI"): "CORALEX",
    ("Mobicell", "CRAIOVA PROMENADA"): "CRPEOM",
    ("Mobicell", "DEVA"): "CDVCHOP",
    ("Mobicell", "ELECTROPUTERE CRAIOVA"): "CRELECTROP",
    ("Mobicell", "FOCSANI"): "FOCCRARF",
    ("Mobicell", "GALATI CARREFOUR"): "GLCRFA",
    ("Mobicell", "GRAND ARENA"): "CRFARENA",
    ("Mobicell", "MEGA MALL"): "MC-MEGAMALL",
    ("Mobicell", "ORADEA AUCHAN"): "ORAUCHAN",
    ("Mobicell", "ORADEA CARREFOUR"): "CRFORADEA",
    ("Mobicell", "PIATRA NEAMT"): "PIATRANEAMT",
    ("Mobicell", "PLOIESTI AFI"): "PLAFIPL",
    ("Mobicell", "PLOIESTI CARREFOUR"): "PLSHOP",
    ("Mobicell", "PROMENADA"): "PROMEN",
    ("Mobicell", "RM SARAT"): "RMSARAT",
    ("Mobicell", "ROMAN"): "ROMAN",
    ("Mobicell", "SATU MARE"): "SATUMARE",
    ("Mobicell", "SEVERIN CARREFOUR"): "SEVCRF",
    ("Mobicell", "SF GHEORGHE"): "SFGHEORGHE",
    ("Mobicell", "SIBIU PROMENADA"): "SBFESTIV",
    ("Mobicell", "SUCEAVA IULIUS"): "SVIULIUS",
    ("Mobicell", "TARGOVISTE"): "DBMALL",
    ("Mobicell", "TG MURES"): "MURSHOP",
    ("Mobicell", "TIMISOARA SHOPPING CITY"): "TMSHOPCITY",
    ("Mobicell", "TRICODAVA"): "AUCHTRIC",
    ("Mobicell", "ZALAU"): "CRFZAL",
}


@dataclass(frozen=True)
class SalaryRecord:
    year: int
    month: int
    full_name: str
    cnp: str
    total_salary: Decimal
    company_name: str
    site_code: str | None
    locatie: str
    source_file: str = ""
    source_sheet: str = "0"
    source_row: int | None = None
    source_sha256: str = ""


def normalize_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", " ", text.upper()).strip()
    return re.sub(r"\s+", " ", text)


def format_cnp(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if re.fullmatch(r"\d+(\.0+)?", text):
        return str(int(float(text)))
    return text


def validate_cnp(value: Any) -> str:
    cnp = format_cnp(value)
    if not re.fullmatch(r"\d{13}", cnp):
        raise ValueError("CNP invalid: sunt necesare exact 13 cifre")
    checksum = sum(int(digit) * weight for digit, weight in zip(cnp[:12], CNP_WEIGHTS)) % 11
    if checksum == 10:
        checksum = 1
    if int(cnp[-1]) != checksum:
        raise ValueError("CNP invalid: checksum invalid")
    return cnp


def decimal_value(value: Any) -> Decimal:
    if value is None or pd.isna(value):
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def company_key(value: str) -> str:
    return normalize_text(value).replace(" ", "")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def load_store_map(conn: asyncpg.Connection) -> dict[tuple[str, str], str | None]:
    rows = await conn.fetch("SELECT site_code, locatie, firma FROM stores")
    mapping: dict[tuple[str, str], str | None] = {}
    for row in rows:
        key = (company_key(row["firma"]), normalize_text(row["locatie"]))
        if key in mapping:
            mapping[key] = None
        else:
            mapping[key] = row["site_code"]
    return mapping


def parse_file(
    path: Path,
    *,
    year: int,
    month: int,
    company_name: str,
    store_map: dict[tuple[str, str], str | None],
    source_sha256: str | None = None,
) -> list[SalaryRecord]:
    source_path = Path(path)
    source_name = source_path.name
    source_digest = source_sha256 or (sha256_file(source_path) if source_path.is_file() else "")
    df = read_spreadsheet_frame(source_path, sheet_name=0)
    cnp_col = "CNP" if "CNP" in df.columns else "cnp"
    meal_col = next((col for col in df.columns if normalize_text(col).startswith("BONURI MASA")), None)
    required = {"Denumire locatie", cnp_col, "Nume Prenume", "TOTAL SALARIU"}
    missing = [col for col in required if col not in df.columns]
    if missing or meal_col is None:
        raise ValueError(f"{source_name}: coloane lipsa: {missing}; meal_col={meal_col!r}")

    records: list[SalaryRecord] = []
    for source_row, (_, row) in enumerate(df.iterrows(), start=2):
        full_name = str(row["Nume Prenume"]).strip() if pd.notna(row["Nume Prenume"]) else ""
        if not full_name or normalize_text(full_name).startswith("TOTAL"):
            continue
        try:
            cnp = validate_cnp(row[cnp_col])
        except ValueError as exc:
            raise ValueError(f"{source_name}, randul {source_row}: {exc}") from exc

        locatie = str(row["Denumire locatie"]).strip() if pd.notna(row["Denumire locatie"]) else ""
        normalized_location = normalize_text(locatie)
        site_code = LOCATION_ALIASES.get((company_name, normalized_location))
        if (company_name, normalized_location) not in LOCATION_ALIASES:
            site_code = store_map.get((company_key(company_name), normalized_location))
        total_salary = decimal_value(row["TOTAL SALARIU"]) + decimal_value(row[meal_col])

        records.append(
            SalaryRecord(
                year=year,
                month=month,
                full_name=full_name,
                cnp=cnp,
                total_salary=total_salary,
                company_name=company_name,
                site_code=site_code,
                locatie=locatie,
                source_file=source_name,
                source_sheet="0",
                source_row=source_row,
                source_sha256=source_digest,
            )
        )
    return records


def validate_records(records: list[SalaryRecord]) -> None:
    seen_source_rows: set[tuple[str, int]] = set()
    names_by_cnp: dict[str, set[str]] = {}
    for record in records:
        cnp = validate_cnp(record.cnp)
        names_by_cnp.setdefault(cnp, set()).add(normalize_text(record.full_name))
        if record.source_file and record.source_row is not None:
            source_key = (record.source_sha256 or record.source_file, record.source_row)
            if source_key in seen_source_rows:
                raise ValueError("Duplicate source row in salary batch")
            seen_source_rows.add(source_key)

    if any(len(names) > 1 for names in names_by_cnp.values()):
        raise ValueError("Conflict identitate: acelasi CNP are nume normalizate diferite")


def build_dry_run_manifest(
    records: list[SalaryRecord],
    *,
    year: int,
    month: int,
    source_files: list[tuple[str, Path]],
    source_hashes: dict[str, str],
) -> dict[str, Any]:
    companies: list[dict[str, Any]] = []
    for company_name, path in source_files:
        company_records = [record for record in records if record.company_name == company_name]
        total = sum((record.total_salary for record in company_records), Decimal("0"))
        companies.append(
            {
                "company_name": company_name,
                "source_file": path.name,
                "source_sha256": source_hashes[company_name],
                "row_count": len(company_records),
                "control_total": f"{total:.2f}",
                "mapped_site_rows": sum(1 for record in company_records if record.site_code),
                "unmapped_locations": sorted(
                    {record.locatie for record in company_records if not record.site_code}
                ),
            }
        )
    grand_total = sum((record.total_salary for record in records), Decimal("0"))
    return {
        "manifest_version": 1,
        "year": year,
        "month": month,
        "companies": companies,
        "row_count": len(records),
        "control_total": f"{grand_total:.2f}",
    }


def _validate_records_match_manifest(records: list[SalaryRecord], manifest: Mapping[str, Any]) -> None:
    if tuple(sorted({record.company_name for record in records})) != tuple(sorted(REQUIRED_COMPANIES)):
        raise ValueError("Batchul salarial nu acopera exact ambele companii")
    manifest_companies = {
        str(company["company_name"]): company
        for company in manifest["companies"]
    }
    for company_name in REQUIRED_COMPANIES:
        company_records = [record for record in records if record.company_name == company_name]
        company_manifest = manifest_companies[company_name]
        if len(company_records) != company_manifest["row_count"]:
            raise ValueError("Manifestul nu corespunde numarului de randuri")
        if any(record.source_file != company_manifest["source_file"] for record in company_records):
            raise ValueError("Manifestul nu corespunde fisierului sursa")
        if any(record.source_sha256 != company_manifest["source_sha256"] for record in company_records):
            raise ValueError("Manifestul nu corespunde hashului sursei")
        total = sum((record.total_salary for record in company_records), Decimal("0"))
        if f"{total:.2f}" != company_manifest["control_total"]:
            raise ValueError("Manifestul nu corespunde totalului de control")
        if sum(1 for record in company_records if record.site_code) != company_manifest.get("mapped_site_rows"):
            raise ValueError("Manifestul nu corespunde maparii magazinelor")
        unmapped = sorted({record.locatie for record in company_records if not record.site_code})
        if unmapped != company_manifest.get("unmapped_locations", []):
            raise ValueError("Manifestul nu corespunde locatiilor nemapate")



async def insert_records(
    conn: asyncpg.Connection,
    records: list[SalaryRecord],
    *,
    manifest: dict[str, Any] | None = None,
    applied_by: str = "test:salary-import",
    approval: ValidatedApproval | None = None,
) -> None:
    if not records:
        raise ValueError("Nu exista randuri valide de importat.")
    validate_records(records)
    if len({(record.year, record.month) for record in records}) != 1:
        raise ValueError("Batchul salarial trebuie sa contina o singura perioada")
    if not applied_by.strip():
        raise ValueError("applied_by este obligatoriu")
    for record in records:
        if (
            not record.source_file
            or not record.source_sheet
            or record.source_row is None
            or not re.fullmatch(r"[0-9a-f]{64}", record.source_sha256)
        ):
            raise ValueError("Provenance salariala incompleta; batchul nu poate fi aplicat")

    batch_id = str(uuid4())
    if manifest is None:
        sources = []
        for company_name in sorted({record.company_name for record in records}):
            company_records = [record for record in records if record.company_name == company_name]
            sources.append(
                {
                    "company_name": company_name,
                    "source_file": company_records[0].source_file,
                    "source_sha256": company_records[0].source_sha256,
                    "row_count": len(company_records),
                    "control_total": f"{sum((item.total_salary for item in company_records), Decimal('0')):.2f}",
                }
            )
        manifest = {
            "manifest_version": 1,
            "year": records[0].year,
            "month": records[0].month,
            "companies": sources,
            "row_count": len(records),
            "control_total": f"{sum((item.total_salary for item in records), Decimal('0')):.2f}",
        }
    safe_manifest = validate_dry_run_manifest(manifest)
    manifest_sha256 = canonical_json_sha256(safe_manifest)
    if not isinstance(approval, ValidatedApproval):
        raise SalaryImportApprovalError("A cryptographically validated approval is required for writes")
    approval.require_cryptographic_validation()
    safe_envelope = validate_audit_envelope(
        approval.envelope(),
        manifest=safe_manifest,
        manifest_sha256=manifest_sha256,
        applied_by=applied_by,
    )
    _validate_records_match_manifest(records, safe_manifest)
    person_id_key = get_salary_person_id_key()
    identified_records = [
        (record, make_salary_person_id(record.cnp, record.full_name, person_id_key))
        for record in records
    ]
    manifest_json = json.dumps(safe_envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    envelope_sha256 = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()

    await persist_salary_records(
        conn,
        records=records,
        identified_records=identified_records,
        batch_id=batch_id,
        manifest_json=manifest_json,
        envelope_sha256=envelope_sha256,
        applied_by=applied_by,
        safe_envelope=safe_envelope,
        normalize_name=normalize_text,
    )


def print_summary(records: list[SalaryRecord]) -> None:
    for company in sorted({r.company_name for r in records}):
        company_records = [r for r in records if r.company_name == company]
        total = sum((r.total_salary for r in company_records), Decimal("0"))
        mapped = sum(1 for r in company_records if r.site_code)
        unmapped_locations = sorted({r.locatie for r in company_records if not r.site_code})
        print(
            f"{company}: {len(company_records)} randuri, total={total:.2f}, "
            f"site_code={mapped}/{len(company_records)}"
        )
        if unmapped_locations:
            print(f"  Fara site_code: {', '.join(unmapped_locations)}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Importa salarii HR in salary_records.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--mobiup-file", type=Path, required=True)
    parser.add_argument("--mobicell-file", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Scrie in DB. Fara flag ruleaza dry-run.")
    parser.add_argument("--applied-by", required=True, help="Identitatea operatorului pentru manifestul auditabil.")
    parser.add_argument("--expected-manifest-sha256", help="SHA-256 exact al manifestului dry-run aprobat.")
    parser.add_argument("--approval-artifact", type=Path, help="Artifactul JSON de aprobare independenta.")
    args = parser.parse_args()

    if args.apply:
        require_apply_inputs(args.expected_manifest_sha256, args.approval_artifact)
    scan_runtime_salary_surfaces(REPO_DIR)

    load_dotenv(REPO_DIR / ".env.migrations")
    load_dotenv(REPO_DIR / ".env")

    db_url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("EROARE: DATABASE_URL lipseste", file=sys.stderr)
        sys.exit(1)

    for file_path in (args.mobiup_file, args.mobicell_file):
        if not file_path.exists():
            print(f"EROARE: fisierul nu exista: {file_path}", file=sys.stderr)
            sys.exit(1)

    source_files = [
        ("Mobiup", args.mobiup_file),
        ("Mobicell", args.mobicell_file),
    ]
    source_hashes = {company_name: sha256_file(path) for company_name, path in source_files}

    conn = await asyncpg.connect(db_url)
    try:
        store_map = await load_store_map(conn)
        records = [
            *parse_file(
                args.mobiup_file,
                year=args.year,
                month=args.month,
                company_name="Mobiup",
                store_map=store_map,
                source_sha256=source_hashes["Mobiup"],
            ),
            *parse_file(
                args.mobicell_file,
                year=args.year,
                month=args.month,
                company_name="Mobicell",
                store_map=store_map,
                source_sha256=source_hashes["Mobicell"],
            ),
        ]
        validate_records(records)
        manifest = build_dry_run_manifest(
            records,
            year=args.year,
            month=args.month,
            source_files=source_files,
            source_hashes=source_hashes,
        )
        print_summary(records)
        missing_companies = [
            company_name
            for company_name in REQUIRED_COMPANIES
            if not any(record.company_name == company_name for record in records)
        ]
        if not args.apply:
            print("DRY RUN MANIFEST: " + json.dumps(manifest, ensure_ascii=False, sort_keys=True))
            print("DRY RUN MANIFEST SHA-256: " + canonical_json_sha256(manifest))
            if missing_companies:
                raise ValueError("Batch HR incomplet: ambele firme sunt obligatorii")
            print("DRY RUN: nu s-a scris nimic. Adauga --apply pentru import.")
            return
        if missing_companies:
            raise ValueError("Batch HR incomplet: ambele firme sunt obligatorii")
        if not records:
            raise ValueError("Nu exista randuri valide de importat.")
        validated_approval = load_and_validate_approval_artifact(
            args.approval_artifact,
            manifest=manifest,
            expected_manifest_sha256=args.expected_manifest_sha256,
            applied_by=args.applied_by,
        )
        await insert_records(
            conn,
            records,
            manifest=manifest,
            applied_by=args.applied_by,
            approval=validated_approval,
        )
        print(f"Import finalizat pentru {args.year}-{args.month:02d}: {len(records)} randuri.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
