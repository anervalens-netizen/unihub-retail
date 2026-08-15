#!/usr/bin/env python3
"""Replay one exact dead Retail outbox event with operations authority."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Final
from uuid import UUID

import asyncpg


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from env_loader import load_env_file

load_env_file(REPOSITORY_ROOT / ".env.worker")

from config import DatabaseAuthority as ConfiguredDatabaseAuthority
from db.connection import (
    database_connection_options,
    get_database_url,
    verify_database_pool_authority,
)
from repositories.transactional_outbox import TransactionalOutboxRepository
from services.outbox_replay import replay_dead_event


class DatabaseAuthority:
    """Executable spelling of the sole replay authority."""

    OPERATIONS: Final[ConfiguredDatabaseAuthority] = "operations"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Requeue one exact dead transactional outbox event."
    )
    parser.add_argument("--event-id", required=True, type=UUID)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--requested-by-sub", required=True)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    pool = await asyncpg.create_pool(
        dsn=get_database_url(),
        min_size=1,
        max_size=2,
        **database_connection_options("unihub-retail-outbox-replay"),
    )
    try:
        await verify_database_pool_authority(
            pool,
            DatabaseAuthority.OPERATIONS,
        )
        replay_number = await replay_dead_event(
            repository=TransactionalOutboxRepository(pool),
            event_id=args.event_id,
            reason=args.reason,
            requested_by_sub=args.requested_by_sub,
            now=datetime.now(timezone.utc),
        )
    finally:
        await pool.close()
    print(f"Replay accepted: {replay_number}")
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LookupError, RuntimeError, ValueError) as exc:
        print(f"Replay refused: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)
