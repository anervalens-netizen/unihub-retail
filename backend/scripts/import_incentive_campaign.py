#!/usr/bin/env python3
"""
Import o campanie de incentive dintr-un fișier Excel în DB.

Formatul Excel așteptat (Sheet1):
  Col 1: cod produs (Cod / ItemCode / cod_produs etc.)
  Col 2: nume produs (ItemName / Denumire etc.) — opțional
  Col 3: valoare incentive (Incentive / Valoare / Bonus / Reward etc.)

Rulare:
    cd /opt/Mobiup/unihub/backend
    python3 scripts/import_incentive_campaign.py \\
        --month 2026-04 \\
        --title "Incentive Aprilie 2026" \\
        --file "../data/Incentiv Mobiup-Mobicell Aprilie 2026.xlsx" \\
        [--subtitle "..."] [--description "..."] [--sheet Sheet1] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

CODE_ALIASES = {"cod", "itemcode", "cod_produs", "code", "sku"}
NAME_ALIASES = {"itemname", "denumire", "name", "produs", "description", "descriere"}
REWARD_ALIASES = {"incentive", "incentiv", "valoare", "valoare_incentive", "reward", "bonus"}


def normalize(col: str) -> str:
    return col.lower().strip().replace(" ", "_").replace("-", "_")


def load_excel(
    path: Path,
    sheet: str,
    header_row: int = 0,
    reward_overrides: dict[str, float] | None = None,
) -> list[dict]:
    df = pd.read_excel(str(path), sheet_name=sheet, header=header_row)
    df = df.rename(columns=lambda c: normalize(str(c)))

    norm_cols = list(df.columns)
    code_col = next((c for c in norm_cols if c in CODE_ALIASES), None)
    name_col = next((c for c in norm_cols if c in NAME_ALIASES), None)
    reward_col = next((c for c in norm_cols if c in REWARD_ALIASES), None)

    if not code_col:
        raise ValueError(f"Nu am găsit coloana de cod produs. Coloane: {norm_cols}")
    if not reward_col:
        raise ValueError(f"Nu am găsit coloana de valoare incentive. Coloane: {norm_cols}")

    print(f"  Coloane detectate: cod='{code_col}', reward='{reward_col}'"
          + (f", nume='{name_col}'" if name_col else ""))

    records = []
    skipped = 0
    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        if not code or code.lower() == "nan":
            skipped += 1
            continue
        try:
            if pd.isna(row[reward_col]):
                raise ValueError("missing reward")
            reward = float(row[reward_col])
        except (TypeError, ValueError):
            override = (reward_overrides or {}).get(code)
            if override is None:
                skipped += 1
                continue
            reward = override
        name = str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else None
        records.append({
            "item_code": code,
            "item_name": name,
            "reward_value": reward,
            "category": str(row.get("categorie")).strip() if pd.notna(row.get("categorie")) else None,
            "subcategory": str(row.get("subcategorie")).strip() if pd.notna(row.get("subcategorie")) else None,
        })

    print(f"  {len(records)} produse valide, {skipped} rânduri sărite")
    return records


async def main(args: argparse.Namespace) -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("EROARE: DATABASE_URL lipsește din .env")
        sys.exit(1)

    file_path = Path(args.file)
    if not file_path.is_absolute():
        file_path = DATA_DIR / args.file
    if not file_path.exists():
        print(f"EROARE: fișierul nu există: {file_path}")
        sys.exit(1)

    print(f"Citesc fișierul: {file_path.name} [sheet={args.sheet}, header={args.header}]")
    reward_overrides: dict[str, float] = {}
    for value in args.reward_override:
        code, separator, raw_reward = value.partition("=")
        if not separator or not code.strip():
            raise ValueError("--reward-override trebuie sa fie COD=VALOARE")
        reward_overrides[code.strip()] = float(raw_reward)
    records = load_excel(
        file_path,
        args.sheet,
        header_row=args.header,
        reward_overrides=reward_overrides,
    )

    if not records:
        print("EROARE: nicio înregistrare validă în fișier.")
        sys.exit(1)

    reward_vals = sorted(set(r["reward_value"] for r in records))
    print(f"  Valori reward unice: {reward_vals}")
    print(f"  Campanie: {args.month} — {args.title}")

    month_start = date.fromisoformat(f"{args.month}-01")
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    valid_from = date.fromisoformat(args.valid_from) if args.valid_from else month_start
    valid_to = date.fromisoformat(args.valid_to) if args.valid_to else date.fromordinal(next_month.toordinal() - 1)
    if valid_from.month != month_start.month or valid_from.year != month_start.year:
        raise ValueError("--valid-from trebuie sa fie in luna campaniei")
    if valid_to.month != month_start.month or valid_to.year != month_start.year or valid_to < valid_from:
        raise ValueError("--valid-to trebuie sa fie in luna campaniei si dupa --valid-from")
    print(f"  Perioada: {valid_from} - {valid_to}")

    if args.dry_run:
        print("\n*** DRY RUN — nu se scrie nimic ***")
        return

    conn = await asyncpg.connect(db_url)
    try:
        # Creează tabelele dacă nu există (înainte de restart backend)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incentive_campaigns (
                id SERIAL PRIMARY KEY,
                month TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                subtitle TEXT,
                description TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incentive_products (
                id SERIAL PRIMARY KEY,
                campaign_id INTEGER NOT NULL REFERENCES incentive_campaigns(id) ON DELETE CASCADE,
                item_code TEXT NOT NULL,
                item_name TEXT,
                reward_value NUMERIC(10, 2) NOT NULL,
                valid_from DATE NOT NULL,
                valid_to DATE NOT NULL,
                category TEXT,
                subcategory TEXT,
                source_file TEXT,
                UNIQUE (campaign_id, item_code, valid_from, valid_to)
            )
            """
        )

        async with conn.transaction():
            # Upsert campanie
            campaign_id = await conn.fetchval(
                """
                INSERT INTO incentive_campaigns (month, title, subtitle, description)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (month) DO UPDATE
                SET title = EXCLUDED.title,
                    subtitle = EXCLUDED.subtitle,
                    description = EXCLUDED.description
                RETURNING id
                """,
                args.month,
                args.title,
                args.subtitle or None,
                args.description or None,
            )

            # Inlocuieste doar perioada importata, pastrand celelalte mecanisme ale lunii.
            await conn.execute(
                "DELETE FROM incentive_products WHERE campaign_id = $1 AND valid_from = $2 AND valid_to = $3",
                campaign_id,
                valid_from,
                valid_to,
            )
            await conn.executemany(
                """
                INSERT INTO incentive_products (
                    campaign_id, item_code, item_name, reward_value,
                    valid_from, valid_to, category, subcategory, source_file
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                [
                    (
                        campaign_id, r["item_code"], r["item_name"], r["reward_value"],
                        valid_from, valid_to, r["category"], r["subcategory"], str(file_path),
                    )
                    for r in records
                ],
            )

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM incentive_products WHERE campaign_id = $1 AND valid_from = $2 AND valid_to = $3",
            campaign_id,
            valid_from,
            valid_to,
        )
        print(f"\nImportat cu succes! Campanie ID={campaign_id}, {count} produse.")

    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import campanie incentive din Excel")
    parser.add_argument("--month", required=True, help="Luna (ex: 2026-04)")
    parser.add_argument("--title", required=True, help="Titlu campanie")
    parser.add_argument("--file", required=True, help="Cale fișier Excel (relativ la data/ sau absolut)")
    parser.add_argument("--subtitle", default="", help="Subtitlu")
    parser.add_argument("--description", default="", help="Descriere")
    parser.add_argument("--sheet", default="Sheet1", help="Numele sheet-ului (default: Sheet1)")
    parser.add_argument("--header", type=int, default=0, help="Rândul cu header (0=primul, 1=al doilea etc.)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--valid-from", default="", help="Prima zi de valabilitate (YYYY-MM-DD)")
    parser.add_argument("--valid-to", default="", help="Ultima zi de valabilitate (YYYY-MM-DD)")
    parser.add_argument(
        "--reward-override",
        action="append",
        default=[],
        help="Completeaza explicit o valoare lipsa: COD=VALOARE",
    )
    asyncio.run(main(parser.parse_args()))
