#!/usr/bin/env python3
"""Dry-run pentru targetele reale per agent citite din Grile Retail.

Aplicarea este disponibila numai prin endpointul privilegiat auditat. Acest
script citeste Google si baza Retail fara sa modifice `agent_targets`.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ROOT_DIR.parent
load_dotenv(REPO_DIR / ".env")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.connection import close_db_pool, get_pool, init_db_pool
from db.migration_runner import verify_migrations_current
from services.grile_agent_targets import (
    configured_disabled_managers,
    configured_enabled_managers,
    sync_agent_targets_from_grile,
)


def _parse_managers(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(item.strip() for item in value.split(",") if item.strip())


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sincronizeaza targete reale per agent din Grile in Retail."
    )
    parser.add_argument("--month", required=True, help="Luna Retail, format YYYY-MM")
    parser.add_argument(
        "--managers",
        help="Lista comma-separated de manageri activati sau configuratia din mediu.",
    )
    parser.add_argument(
        "--disabled-managers",
        help="Lista comma-separated de manageri exclusi sau configuratia din mediu.",
    )
    args = parser.parse_args()

    enabled = _parse_managers(args.managers) or configured_enabled_managers()
    disabled = _parse_managers(args.disabled_managers) or configured_disabled_managers()

    await init_db_pool()
    await verify_migrations_current(await get_pool())
    pool = await get_pool()
    result = await sync_agent_targets_from_grile(
        pool,
        month=args.month,
        enabled_managers=enabled,
        disabled_managers=disabled,
    )

    print(f"Luna: {result.month}")
    print(f"Apply: {'da' if result.apply else 'nu'}")
    print(f"Configuratii manageri activate: {len(result.enabled_managers)}")
    print(f"Configuratii manageri excluse: {len(result.disabled_managers)}")
    print(f"Magazine candidate: {result.sites_considered}")
    print(f"Magazine citite: {result.sites_read}")
    print(f"Targete rezolvate: {result.resolved_count}")
    print(f"Nerezolvate: {result.unresolved_count}")

    if result.skipped_managers:
        print(
            "Magazine nesincronizate pe configuratia managerilor: "
            f"{sum(result.skipped_managers.values())}"
        )

    if result.unresolved:
        print("Exista randuri nerezolvate; output-ul afiseaza numai totalurile de control.")

    print("\nDRY RUN: nu s-a scris nimic. Aplicarea se face numai prin API-ul privilegiat.")

    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
