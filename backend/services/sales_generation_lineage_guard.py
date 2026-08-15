"""Connection-bound lineage fencing for sales-derived publication work."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class BoundConnectionPool:
    """Pool-shaped adapter that never acquires beyond one already-held connection."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        yield self.connection


@asynccontextmanager
async def guard_sales_generation_lineage_bound(
    pool: Any,
    *,
    month: str,
    generation_hash: str,
    sales_revision: int,
) -> AsyncIterator[tuple[str, BoundConnectionPool]]:
    """Hold the exact sales head while all dependent DB work reuses its connection."""
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT snap.manifest_sha256 AS generation_hash, head.revision
            FROM sales_generation_heads AS head
            JOIN import_snapshots AS snap ON snap.id = head.snapshot_id
            WHERE head.import_month = $1
            FOR SHARE OF head
            """,
            month,
        )
        if row is None:
            raise RuntimeError("Authoritative sales generation is unavailable")
        current_hash = str(row["generation_hash"] or "")
        current_revision = int(row["revision"] or 0)
        if current_revision > sales_revision:
            yield "superseded", BoundConnectionPool(conn)
            return
        if current_revision < sales_revision:
            raise RuntimeError("Requested sales generation is ahead of the head")
        if current_hash != generation_hash:
            raise RuntimeError("Sales generation hash differs at the same revision")
        yield "current", BoundConnectionPool(conn)
