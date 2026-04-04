#!/usr/bin/env python3
"""
Import batch pentru fișierele istorice de vânzări 2023 Q4 + 2024.

Fișierele vechi (pre-2025) nu au coloanele Agent, Categorie, SubCategorie:
  - Agent      → '-'  (agent necunoscut pentru date istorice)
  - Categorie  → None
  - SubCategorie → None
  - is_cartela → False (nu putem detecta fără Categorie; presupunem vânzare normală)

Optimizare batch: rebuild_agent_lifecycle_reporting se apelează o singură dată la final,
nu la fiecare lună ca în importerul normal.

Rulare:
    cd /opt/Mobiup/unihub/backend
    python scripts/import_historical.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Încarcă .env înainte de orice import local
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import pandas as pd

from services.importer import (
    filter_asm_rows,
    detect_month,
    is_month_final,
    insert_snapshot,
    upsert_stores,
    replace_month_snapshot,
    insert_transactions,
)
from services.reporting_refresh import (
    rebuild_reporting_month,
    rebuild_agent_lifecycle_reporting,
)

BASE = Path(__file__).resolve().parent.parent.parent / "data" / "vanzari 2022, 2023 si 2024"

OLD_COLUMNS = [
    "Data", "SiteCode", "ItemCode", "ItemName", "Cantitate", "Brand",
    "Pret", "Valoare", "Locatie", "Firma", "ASM", "Regional", "Nr",
]


def load_historical_df(path: Path) -> pd.DataFrame:
    """Citește un fișier vechi (fără Agent/Categorie/SubCategorie) și adaugă coloanele lipsă."""
    df = pd.read_excel(str(path), sheet_name="MobiUp_MobiCell", engine=None)
    df = df.rename(columns=lambda v: str(v).strip())

    missing = [c for c in OLD_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Lipsesc coloane obligatorii: {missing}")

    df = df[OLD_COLUMNS].copy()
    df["Data"] = pd.to_datetime(df["Data"], format="%d.%m.%Y", errors="raise").dt.date
    df["Cantitate"] = pd.to_numeric(df["Cantitate"], errors="raise").astype(int)
    df["Pret"] = pd.to_numeric(df["Pret"], errors="coerce").fillna(0)
    df["Valoare"] = pd.to_numeric(df["Valoare"], errors="coerce").fillna(0)
    df["Nr"] = df["Nr"].fillna("").map(lambda v: str(v).strip())
    for col in ["SiteCode", "ItemCode", "ItemName", "Locatie", "Firma", "ASM", "Regional"]:
        df[col] = df[col].fillna("").map(lambda v: str(v).strip())

    # Brand: NaN din celule goale → None (altfel asyncpg primește float pe coloană TEXT)
    df["Brand"] = df["Brand"].where(pd.notna(df["Brand"]), None)
    df["Brand"] = df["Brand"].map(lambda v: str(v).strip() if isinstance(v, str) else v)

    # Coloane lipsă față de formatul curent (post-2025)
    df["Agent"] = "-"
    df["Categorie"] = None
    df["SubCategorie"] = None
    # is_cartela=False: fără Categorie nu putem detecta; presupunem vânzare normală
    # (is_cartela=True ar exclude rândurile din toate rapoartele)
    df["is_cartela"] = False
    df["is_return"] = df["Cantitate"] < 0

    return df


def collect_files() -> list[Path]:
    """Colectează fișierele din 2023/ și 2024/, sortate cronologic după folder + nume."""
    files: list[Path] = []
    for year_dir in [BASE / "2023", BASE / "2024"]:
        if year_dir.exists():
            files.extend(sorted(year_dir.glob("*.xlsx")))
    return files


async def import_one(
    conn: asyncpg.Connection,
    path: Path,
    imported_months: set[str],
    dry_run: bool,
) -> tuple[str | None, int]:
    """
    Importă un fișier istoric.
    Returnează (import_month, rows_imported) sau (None, 0) dacă sărit.
    NU apelează rebuild_agent_lifecycle_reporting — se face o singură dată la final.
    """
    df = load_historical_df(path)
    rows_total = len(df)

    df, rows_filtered = filter_asm_rows(df)
    if df.empty:
        print(f"  SKIP — nicio linie cu ASM valid după filtrare")
        return None, 0

    import_month = detect_month(df)

    if import_month in imported_months:
        print(f"  SKIP — {import_month} deja importat în DB")
        return None, 0

    print(f"  Luna detectată: {import_month} | {rows_total:,} total | {rows_filtered:,} filtrate | {len(df):,} de importat")

    if dry_run:
        print(f"  [DRY RUN] s-ar importa {len(df):,} rânduri")
        return import_month, len(df)

    snapshot_id = await insert_snapshot(
        conn,
        import_month=import_month,
        filename=path.name,
        rows_in_file=rows_total,
        imported_by=None,
    )

    try:
        async with conn.transaction():
            await upsert_stores(conn, df, import_month)
            await replace_month_snapshot(conn, import_month)
            rows_imported = await insert_transactions(conn, df, snapshot_id, import_month)
            await rebuild_reporting_month(conn, import_month)

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
                is_month_final(import_month),
            )
    except Exception as exc:
        await conn.execute(
            """
            UPDATE import_snapshots
            SET status = 'failed', rows_imported = 0, error_message = $2
            WHERE id = $1
            """,
            snapshot_id,
            str(exc)[:500],
        )
        raise

    return import_month, rows_imported


async def main(dry_run: bool) -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("EROARE: DATABASE_URL lipsește din .env")
        sys.exit(1)

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            "SELECT import_month FROM import_snapshots WHERE status = 'completed'"
        )
        imported_months: set[str] = {r["import_month"] for r in rows}
        print(f"Luni deja în DB: {sorted(imported_months)}\n")

        files = collect_files()
        print(f"Fișiere găsite: {len(files)}")
        if dry_run:
            print("  *** MOD DRY RUN — nu se scrie nimic în DB ***")
        print()

        results: list[tuple[str, int]] = []
        errors: list[tuple[str, str]] = []

        for path in files:
            print(f"[{path.parent.name}/{path.name}]")
            try:
                month, rows_imported = await import_one(conn, path, imported_months, dry_run)
                if month:
                    imported_months.add(month)
                    results.append((month, rows_imported))
                    print(f"  {'[DRY RUN] ' if dry_run else ''}OK — {rows_imported:,} rânduri")
            except Exception as exc:
                print(f"  EROARE — {exc}")
                errors.append((path.name, str(exc)))
            print()

        if results and not dry_run:
            print("Reconstruiesc reporting lifecycle (o singură dată pentru toți agenții)...")
            await rebuild_agent_lifecycle_reporting(conn)
            print("  Done.\n")

        print("=" * 50)
        print(f"Importate: {len(results)} luni | Erori: {len(errors)}")
        print(f"Total rânduri: {sum(r for _, r in results):,}")
        if results:
            print("\nLuni importate:")
            for month, r in sorted(results):
                print(f"  {month}: {r:,} rânduri")
        if errors:
            print(f"\nErori:")
            for fname, err in errors:
                print(f"  {fname}: {err}")

    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import batch fișiere istorice vânzări 2023-2024")
    parser.add_argument("--dry-run", action="store_true", help="Simulează fără a scrie în DB")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
