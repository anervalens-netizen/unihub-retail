#!/usr/bin/env python3
"""
Import rezumat anual din 'vanzari 2022 si 2023.xlsx' în historical_annual_sales.

Logică:
  - 2022: importăm totalul anual complet (valoare + cantitate) per magazin per firmă
  - 2023: calculăm Jan-Aug = total_din_fisier - (Sep+Oct+Nov+Dec din sales_transactions)
          is_partial_year=True; valorile negative (inconsistențe fișier) sunt setate la 0

Matching magazin: exact pe locatie+firma (100% match verificat).

Rulare:
    cd /opt/Mobiup/unihub/backend
    python3 scripts/import_annual_summary.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import openpyxl

SUMMARY_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "vanzari 2022, 2023 si 2024"
    / "vanzari 2022 si 2023.xlsx"
)

# Sheet → (firma, tip_date)
SHEETS = {
    "Mobiup Valoare":   ("MobiUp",   "value"),
    "Mobiup Buc":       ("MobiUp",   "qty"),
    "Mobicell Valoare": ("MobiCell", "value"),
    "Mobicell Buc":     ("MobiCell", "qty"),
}


def load_summary() -> dict[tuple[str, str], dict[int, dict[str, float]]]:
    """
    Returnează: {(firma, locatie_upper): {2022: {value, qty}, 2023: {value, qty}}}
    """
    wb = openpyxl.load_workbook(str(SUMMARY_FILE), read_only=True)
    # data[(firma, locatie)] = {2022: {value, qty}, 2023: {value, qty}}
    data: dict[tuple[str, str], dict[int, dict[str, float]]] = defaultdict(
        lambda: {2022: {"value": 0.0, "qty": 0.0}, 2023: {"value": 0.0, "qty": 0.0}}
    )

    for sheet_name, (firma, tip) in SHEETS.items():
        ws = wb[sheet_name]
        for row in ws.iter_rows(values_only=True):
            if row[0] != firma:
                continue
            magazin = str(row[3]).upper().strip()
            val_2024 = row[4]  # coloana E — ignorăm, avem date detaliate
            val_2023 = row[5]  # coloana F
            val_2022 = row[6]  # coloana G
            key = (firma, magazin)
            if isinstance(val_2022, (int, float)):
                data[key][2022][tip] = float(val_2022)
            if isinstance(val_2023, (int, float)):
                data[key][2023][tip] = float(val_2023)

    wb.close()
    return dict(data)


async def build_site_code_map(
    conn: asyncpg.Connection,
) -> dict[tuple[str, str], str]:
    """
    Construiește {(firma, locatie_upper): site_code} din tabelul stores.
    Dacă există două site_code-uri cu aceeași locatie+firma, le grupăm
    și avertizăm (vom folosi primul alfabetic).
    """
    rows = await conn.fetch("SELECT site_code, locatie, firma FROM stores")
    mapping: dict[tuple[str, str], str] = {}
    duplicates: dict[tuple[str, str], list[str]] = defaultdict(list)

    for r in rows:
        key = (r["firma"], r["locatie"].upper().strip())
        duplicates[key].append(r["site_code"])

    for key, codes in duplicates.items():
        if len(codes) > 1:
            print(f"  ATENTIE: locatie duplicată {key} → {codes}, folosim {sorted(codes)[0]}")
        mapping[key] = sorted(codes)[0]

    return mapping


async def fetch_q4_2023(
    conn: asyncpg.Connection,
) -> dict[tuple[str, str], dict[str, float]]:
    """
    Returnează totalurile Sep-Dec 2023 din sales_transactions per (site_code, firma).
    {(site_code, firma): {value, qty}}
    """
    rows = await conn.fetch(
        """
        SELECT st.site_code, s.firma,
               COALESCE(SUM(st.total_value), 0)  AS total_value,
               COALESCE(SUM(CASE WHEN st.quantity > 0 THEN st.quantity ELSE 0 END), 0) AS total_qty
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        WHERE st.import_month IN ('2023-09','2023-10','2023-11','2023-12')
          AND NOT st.is_cartela
        GROUP BY st.site_code, s.firma
        """
    )
    return {
        (r["site_code"], r["firma"]): {
            "value": float(r["total_value"]),
            "qty":   float(r["total_qty"]),
        }
        for r in rows
    }


async def main(dry_run: bool) -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("EROARE: DATABASE_URL lipsește din .env")
        sys.exit(1)

    conn = await asyncpg.connect(db_url)
    try:
        print("Încarc datele din fișier...")
        summary = load_summary()
        print(f"  {len(summary)} înregistrări (firma, magazin) citite\n")

        print("Construiesc mapping locatie → site_code...")
        site_map = await build_site_code_map(conn)
        print()

        print("Încarc Q4 2023 din transactions (pentru calcul Jan-Aug)...")
        q4_2023 = await fetch_q4_2023(conn)
        print(f"  {len(q4_2023)} magazine cu date Q4 2023\n")

        records: list[tuple] = []
        unmatched: list[str] = []

        for (firma, magazin), years in summary.items():
            site_code = site_map.get((firma, magazin))
            if not site_code:
                unmatched.append(f"{firma} / {magazin}")
                continue

            # 2022 — an complet
            v2022 = years[2022]["value"]
            q2022 = int(round(years[2022]["qty"]))
            records.append((site_code, 2022, firma, v2022, q2022, False))

            # 2023 — Jan-Aug = annual_total - Q4_din_transactions
            v2023_annual = years[2023]["value"]
            q2023_annual = years[2023]["qty"]
            q4 = q4_2023.get((site_code, firma), {"value": 0.0, "qty": 0.0})
            v2023_jan_aug = max(0.0, v2023_annual - q4["value"])
            q2023_jan_aug = max(0, int(round(q2023_annual - q4["qty"])))
            records.append((site_code, 2023, firma, v2023_jan_aug, q2023_jan_aug, True))

        print(f"Înregistrări pregătite: {len(records)} ({len(records)//2} magazine × 2 ani)")
        if unmatched:
            print(f"NEMATCHED ({len(unmatched)}):")
            for u in unmatched:
                print(f"  {u}")
        print()

        # Preview
        print("Preview (primele 6 înregistrări):")
        print(f"  {'site_code':<14} {'year':<6} {'firma':<10} {'value':>12} {'qty':>8} {'partial'}")
        for r in records[:6]:
            print(f"  {r[0]:<14} {r[1]:<6} {r[2]:<10} {r[3]:>12,.2f} {r[4]:>8,} {r[5]}")
        print()

        if dry_run:
            print("*** DRY RUN — nu se scrie nimic ***")
            return

        async with conn.transaction():
            # Compatibilitate cu instalari vechi; schema canonica include tabela.
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS historical_annual_sales (
                    site_code TEXT NOT NULL REFERENCES stores(site_code),
                    year INTEGER NOT NULL,
                    firma TEXT NOT NULL,
                    total_value NUMERIC(14, 2) NOT NULL DEFAULT 0,
                    total_qty INTEGER NOT NULL DEFAULT 0,
                    is_partial_year BOOLEAN NOT NULL DEFAULT false,
                    PRIMARY KEY (site_code, year, firma)
                )
                """
            )

            await conn.executemany(
                """
                INSERT INTO historical_annual_sales
                    (site_code, year, firma, total_value, total_qty, is_partial_year)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (site_code, year, firma) DO UPDATE
                SET total_value      = EXCLUDED.total_value,
                    total_qty        = EXCLUDED.total_qty,
                    is_partial_year  = EXCLUDED.is_partial_year
                """,
                records,
            )

            count = await conn.fetchval(
                "SELECT COUNT(*) FROM historical_annual_sales"
            )
        print(f"Importat cu succes. Înregistrări în historical_annual_sales: {count}")

        # Sumar pe ani
        rows = await conn.fetch(
            """
            SELECT year, is_partial_year,
                   COUNT(*) AS magazine,
                   SUM(total_value)::BIGINT AS total_value,
                   SUM(total_qty) AS total_qty
            FROM historical_annual_sales
            GROUP BY year, is_partial_year
            ORDER BY year
            """
        )
        print("\nSumar:")
        for r in rows:
            label = "Jan-Aug" if r["is_partial_year"] else "an complet"
            print(f"  {r['year']} ({label}): {r['magazine']} magazine | {r['total_value']:,} RON | {r['total_qty']:,} buc")

    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import rezumat anual vânzări 2022-2023")
    parser.add_argument("--dry-run", action="store_true", help="Simulează fără a scrie în DB")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
