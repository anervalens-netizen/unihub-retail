#!/usr/bin/env python3
"""Seed `grile_sheets` din grile-salarii (read-only copy a linkurilor).

Citeste `/opt/Mobiup/grile-salarii/sheets_registry.json` (Company/Store ->
sheet_id) + `store_metadata.json` (Company/Store -> cod_locatie) si mapeaza
fiecare grila la `stores.site_code` (= cod_locatie). NU modifica nimic in
grile-salarii si NU atinge Google. Default dry-run; `--apply` face upsert.

source_hash = sha256 al registry-ului -> detecteaza drift la reseed (linkurile
NU ar trebui sa se schimbe).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ROOT_DIR.parent
load_dotenv(REPO_DIR / ".env")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.connection import close_db_pool, ensure_schema_current, get_pool, init_db_pool

GRILE_ROOT = Path("/opt/Mobiup/grile-salarii")
REGISTRY_FILE = GRILE_ROOT / "sheets_registry.json"
METADATA_FILE = GRILE_ROOT / "store_metadata.json"


def load_mapping() -> tuple[list[dict], str, list[str]]:
    registry_raw = REGISTRY_FILE.read_text(encoding="utf-8")
    registry = json.loads(registry_raw)
    metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(registry_raw.encode("utf-8")).hexdigest()

    rows: list[dict] = []
    warnings: list[str] = []
    for key, sheet_id in registry.items():
        if key.startswith("_") or "/" not in key:
            continue
        meta = metadata.get(key, {})
        cod = str(meta.get("cod_locatie") or "").strip()
        if not cod:
            warnings.append(f"fara cod_locatie in metadata: {key}")
            continue
        if not isinstance(sheet_id, str) or not sheet_id.strip():
            warnings.append(f"sheet_id invalid: {key}")
            continue
        rows.append({"site_code": cod, "sheet_id": sheet_id.strip(), "registry_key": key})
    return rows, source_hash, warnings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed grile_sheets din grile-salarii (read-only).")
    parser.add_argument("--apply", action="store_true", help="Aplica upsert (default: dry-run)")
    args = parser.parse_args()

    rows, source_hash, warnings = load_mapping()
    for w in warnings:
        print(f"  WARN: {w}")
    print(f"mapari valide din registry: {len(rows)}  | source_hash={source_hash[:12]}")

    await init_db_pool()
    await ensure_schema_current()
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            valid_codes = {r["site_code"] for r in await conn.fetch("SELECT site_code FROM stores")}
            matched = [r for r in rows if r["site_code"] in valid_codes]
            skipped = [r for r in rows if r["site_code"] not in valid_codes]
            for r in skipped:
                print(f"  SKIP (site_code lipsa in stores): {r['registry_key']} -> {r['site_code']}")
            print(f"de upsertat: {len(matched)}  | skipped: {len(skipped)}")

            if not args.apply:
                print("DRY-RUN. Foloseste --apply pentru a scrie in DB.")
                return

            async with conn.transaction():
                for r in matched:
                    await conn.execute(
                        """
                        INSERT INTO grile_sheets (site_code, sheet_id, registry_key, source_hash, updated_at)
                        VALUES ($1, $2, $3, $4, now())
                        ON CONFLICT (site_code) DO UPDATE SET
                            sheet_id = EXCLUDED.sheet_id,
                            registry_key = EXCLUDED.registry_key,
                            source_hash = EXCLUDED.source_hash,
                            is_active = true,
                            updated_at = now()
                        """,
                        r["site_code"], r["sheet_id"], r["registry_key"], source_hash,
                    )
            print(f"APPLIED: {len(matched)} grile_sheets upsertate.")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
