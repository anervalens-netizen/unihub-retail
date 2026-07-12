#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.migration_runner import run_migrations


async def main() -> None:
    applied = await run_migrations()
    if applied:
        print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        print("Database migrations are current")


if __name__ == "__main__":
    asyncio.run(main())
