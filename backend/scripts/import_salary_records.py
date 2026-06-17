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
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
import pandas as pd
from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parents[2]
load_dotenv(REPO_DIR / ".env")


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
    return re.sub(r"\D", "", text)


def decimal_value(value: Any) -> Decimal:
    if value is None or pd.isna(value):
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def company_key(value: str) -> str:
    return normalize_text(value).replace(" ", "")


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
) -> list[SalaryRecord]:
    df = pd.read_excel(path, sheet_name=0)
    cnp_col = "CNP" if "CNP" in df.columns else "cnp"
    meal_col = next((col for col in df.columns if normalize_text(col).startswith("BONURI MASA")), None)
    required = {"Denumire locatie", cnp_col, "Nume Prenume", "TOTAL SALARIU"}
    missing = [col for col in required if col not in df.columns]
    if missing or meal_col is None:
        raise ValueError(f"{path.name}: coloane lipsa: {missing}; meal_col={meal_col!r}")

    records: list[SalaryRecord] = []
    for _, row in df.iterrows():
        full_name = str(row["Nume Prenume"]).strip() if pd.notna(row["Nume Prenume"]) else ""
        if not full_name or normalize_text(full_name).startswith("TOTAL"):
            continue
        cnp = format_cnp(row[cnp_col])
        if not cnp:
            continue

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
            )
        )
    return records


def validate_records(records: list[SalaryRecord]) -> None:
    seen: set[tuple[int, int, str, str, str]] = set()
    duplicates: list[SalaryRecord] = []
    for record in records:
        key = (record.year, record.month, record.cnp, record.full_name, record.company_name)
        if key in seen:
            duplicates.append(record)
        seen.add(key)
    if duplicates:
        sample = ", ".join(f"{r.company_name}:{r.full_name}:{r.cnp}" for r in duplicates[:5])
        raise ValueError(f"Duplicate pe cheia salary_records: {sample}")


async def insert_records(conn: asyncpg.Connection, records: list[SalaryRecord]) -> None:
    await conn.execute(
        "DELETE FROM salary_records WHERE year = $1 AND month = $2 AND company_name = ANY($3::text[])",
        records[0].year,
        records[0].month,
        sorted({r.company_name for r in records}),
    )
    await conn.executemany(
        """
        INSERT INTO salary_records (
            year, month, full_name, cnp, total_salary, company_name, site_code, locatie
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        [
            (
                r.year,
                r.month,
                r.full_name,
                r.cnp,
                r.total_salary,
                r.company_name,
                r.site_code,
                r.locatie,
            )
            for r in records
        ],
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
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("EROARE: DATABASE_URL lipseste din .env", file=sys.stderr)
        sys.exit(1)

    for file_path in (args.mobiup_file, args.mobicell_file):
        if not file_path.exists():
            print(f"EROARE: fisierul nu exista: {file_path}", file=sys.stderr)
            sys.exit(1)

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
            ),
            *parse_file(
                args.mobicell_file,
                year=args.year,
                month=args.month,
                company_name="Mobicell",
                store_map=store_map,
            ),
        ]
        validate_records(records)
        print_summary(records)
        if not args.apply:
            print("DRY RUN: nu s-a scris nimic. Adauga --apply pentru import.")
            return
        if not records:
            raise ValueError("Nu exista randuri valide de importat.")
        async with conn.transaction():
            await insert_records(conn, records)
        print(f"Import finalizat pentru {args.year}-{args.month:02d}: {len(records)} randuri.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
