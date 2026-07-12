#!/usr/bin/env python3
"""Dry-run/apply pentru targetele reale per agent citite din Grile Retail.

Default ruleaza dry-run. Foloseste `--apply` ca sa inlocuiasca override-urile
sigur citite pentru managerii activati. Grilele Google sunt citite read-only.
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
        help=(
            "Lista comma-separated de manageri activati. Default: "
            "GRILE_AGENT_TARGET_ENABLED_MANAGERS sau Andrei Stancu."
        ),
    )
    parser.add_argument(
        "--disabled-managers",
        help=(
            "Lista comma-separated de manageri exclusi. Default: "
            "GRILE_AGENT_TARGET_DISABLED_MANAGERS sau Bogdan Radu,Bogdana Costan."
        ),
    )
    parser.add_argument("--apply", action="store_true", help="Scrie in agent_targets")
    args = parser.parse_args()

    enabled = _parse_managers(args.managers) or configured_enabled_managers()
    disabled = _parse_managers(args.disabled_managers) or configured_disabled_managers()

    await init_db_pool()
    await verify_migrations_current(await get_pool())
    pool = await get_pool()
    result = await sync_agent_targets_from_grile(
        pool,
        month=args.month,
        apply=args.apply,
        enabled_managers=enabled,
        disabled_managers=disabled,
    )

    print(f"Luna: {result.month}")
    print(f"Apply: {'da' if result.apply else 'nu'}")
    print(f"Manageri activati: {', '.join(result.enabled_managers) or '-'}")
    print(f"Manageri exclusi: {', '.join(result.disabled_managers) or '-'}")
    print(f"Magazine candidate: {result.sites_considered}")
    print(f"Magazine citite: {result.sites_read}")
    print(f"Targete rezolvate: {result.resolved_count}")
    print(f"Nerezolvate: {result.unresolved_count}")

    if result.skipped_managers:
        print("\nZONE NESINCRONIZATE (raman pe fallback)")
        for manager, count in sorted(result.skipped_managers.items()):
            print(f"- {manager}: {count} magazine")

    if result.unresolved:
        print("\nNEREZOLVATE (raman pe fallback)")
        for unresolved in result.unresolved:
            print(
                f"- {unresolved.get('site_code')} | {unresolved.get('source_store_key')} | "
                f"{unresolved.get('agent_name', '')} | target={unresolved.get('target_value')} | "
                f"status={unresolved.get('status')}"
            )

    print("\nREZOLVATE")
    for resolved in result.resolved:
        print(
            f"- {resolved.site_code} | {resolved.source_agent_name} -> {resolved.agent} | "
            f"target={resolved.target_value} | {resolved.match_method}"
        )

    if result.apply:
        print(f"\nImport finalizat: {result.resolved_count} randuri upsert in agent_targets.")
    else:
        print("\nDRY RUN: nu s-a scris nimic. Ruleaza cu --apply pentru import.")

    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
