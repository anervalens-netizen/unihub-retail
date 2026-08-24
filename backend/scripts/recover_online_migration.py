#!/usr/bin/env python3
"""Explicit operator recovery for a controlled online migration.

Recovers the exact manifest filename that left an ``online-recovery`` sentinel
in the canonical ``schema_migrations`` ledger. Requires
``MIGRATION_DATABASE_URL`` (owner-only) and the same migration authority.

Usage::

    MIGRATION_DATABASE_URL=postgresql://... python recover_online_migration.py 070_online.sql
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.migration_runner import MigrationError
from db.recover_online_index import recover_online_migration


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recover one controlled online CREATE INDEX CONCURRENTLY migration."
    )
    parser.add_argument(
        "filename",
        help="manifest migration filename that holds the online recovery sentinel",
    )
    args = parser.parse_args()
    try:
        asyncio.run(recover_online_migration(filename=args.filename))
    except (MigrationError, RuntimeError) as exc:
        print(f"Migration recovery failed: {exc}", file=sys.stderr)
        return 1
    print(f"Recovered online migration: {args.filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
