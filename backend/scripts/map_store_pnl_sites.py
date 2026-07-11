#!/usr/bin/env python3
"""Mapeaza codurile istorice din P&L la master-data Retail."""

from __future__ import annotations

import argparse
import asyncio
import difflib
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parents[2]

MANUAL_ALIASES: dict[tuple[str, str], str] = {
    ("Mobiup", "PITBRA"): "AUCHBR",
    ("Mobiup", "ORHID"): "CRFORH1",
    ("Mobiup", "CARRGL"): "GLCRF",
    ("Mobiup", "FCCARRF"): "FOCSCRARF",
    ("Mobiup", "SIBCY"): "SBPROMEN",
    ("Mobiup", "SBPFV"): "MSBFEST",
    ("Mobiup", "MGML"): "MEGAMALL",
    ("Mobiup", "DEVA"): "DVSHP",
    ("Mobicell", "BRAILAPROMENADA"): "BRPRMALL",
    ("Mobicell", "SIBIUFESTIBAL"): "SBFESTIV",
    ("Mobicell", "CARRFORERA"): "CRFORADEA",
    ("Mobicell", "CSTTOM"): "CRFTOMCT",
    ("Mobicell", "IASIFELICIA"): "ISFELICIA",
    ("Mobicell", "PLVL"): "PLVALUE",
    ("Mobicell", "PROMDMALL"): "PROMEN",
    ("Mobicell", "SBPR"): "SBPROM",
    ("Mobiup", "BAIAMARE"): "BMAREVIVO",
    ("Mobiup", "OBOR1"): "OBO1",
}


@dataclass(frozen=True)
class SiteLink:
    company_name: str
    source_site_code: str
    source_location_name: str
    site_code: str
    match_method: str
    confidence: float
    reviewed: bool


def company_name(firma: str) -> str | None:
    normalized = firma.upper()
    if "MOBICELL" in normalized:
        return "Mobicell"
    if "MOBIUP" in normalized:
        return "Mobiup"
    return None


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").upper()
    text = re.sub(r"\b(FOST|LOCATIE|INCHISA|INCHIS|MAGAZIN)\b", " ", text)
    return re.sub(r"[^A-Z0-9]+", "", text)


def build_links(source_rows: list[asyncpg.Record], stores: list[asyncpg.Record]) -> tuple[list[SiteLink], list[str]]:
    stores_by_company: dict[str, list[asyncpg.Record]] = {"Mobicell": [], "Mobiup": []}
    stores_by_code = {row["site_code"].upper(): row for row in stores}
    for store in stores:
        company = company_name(store["firma"] or "")
        if company:
            stores_by_company[company].append(store)

    links: list[SiteLink] = []
    unresolved: list[str] = []
    for source in source_rows:
        company = source["company_name"]
        source_code = source["source_site_code"].strip()
        location = source["source_location_name"].strip()
        candidates = stores_by_company[company]

        exact_code = next((row for row in candidates if row["site_code"].upper() == source_code.upper()), None)
        if exact_code:
            links.append(SiteLink(company, source_code, location, exact_code["site_code"], "exact_code", 1.0, True))
            continue

        manual_code = MANUAL_ALIASES.get((company, source_code.upper()))
        if manual_code:
            target = stores_by_code.get(manual_code)
            if not target or company_name(target["firma"] or "") != company:
                raise ValueError(f"Alias invalid pentru {company}/{source_code}: {manual_code}")
            links.append(SiteLink(company, source_code, location, target["site_code"], "manual_alias", 1.0, True))
            continue

        name_matches = [row for row in candidates if normalize(row["locatie"]) == normalize(location)]
        if len(name_matches) == 1:
            links.append(SiteLink(company, source_code, location, name_matches[0]["site_code"], "exact_name", 1.0, True))
            continue

        scored = sorted(
            (
                difflib.SequenceMatcher(None, normalize(location), normalize(row["locatie"])).ratio(),
                row,
            )
            for row in candidates
        )
        best_score, best = scored[-1]
        second_score = scored[-2][0] if len(scored) > 1 else 0.0
        if best_score >= 0.82 and best_score - second_score >= 0.08:
            links.append(SiteLink(company, source_code, location, best["site_code"], "fuzzy_name", best_score, False))
        else:
            unresolved.append(
                f"{company}/{source_code} {location!r}: candidat {best['site_code']} {best['locatie']!r} "
                f"({best_score:.2f}, marja {best_score - second_score:.2f})"
            )
    return links, unresolved


async def run(apply: bool) -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste din .env")
    connection = await asyncpg.connect(database_url)
    try:
        sources = await connection.fetch(
            """
            SELECT DISTINCT ON (company_name, source_site_code)
                company_name, source_site_code, source_location_name
            FROM store_pnl_monthly
            WHERE data_kind = 'actual'
            ORDER BY company_name, source_site_code, period DESC
            """
        )
        stores = await connection.fetch("SELECT site_code, locatie, firma FROM stores")
        links, unresolved = build_links(list(sources), list(stores))
        counts: dict[str, int] = {}
        for link in links:
            counts[link.match_method] = counts.get(link.match_method, 0) + 1
        print(f"Mapari propuse: {len(links)}/{len(sources)}; metode={counts}")
        for item in unresolved:
            print(f"  NEREZOLVAT {item}")
        if unresolved:
            print("Cazurile fara magazin in master-data raman nemapate; maparile sigure pot fi aplicate.")
        if apply:
            async with connection.transaction():
                await connection.executemany(
                    """
                    INSERT INTO store_pnl_site_links (
                        company_name, source_site_code, source_location_name, site_code,
                        match_method, confidence, reviewed
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (company_name, source_site_code) DO UPDATE SET
                        source_location_name = EXCLUDED.source_location_name,
                        site_code = EXCLUDED.site_code,
                        match_method = EXCLUDED.match_method,
                        confidence = EXCLUDED.confidence,
                        reviewed = EXCLUDED.reviewed,
                        updated_at = now()
                    """,
                    [(x.company_name, x.source_site_code, x.source_location_name, x.site_code, x.match_method, x.confidence, x.reviewed) for x in links],
                )
            print(f"Mapari salvate: {len(links)}")
        else:
            print("Dry-run: maparile nu au fost scrise.")
        return 0
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Mapeaza magazinele istorice P&L.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(REPO_DIR / ".env")
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        raise SystemExit(1)