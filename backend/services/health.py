from __future__ import annotations

import asyncio

from db.connection import get_pool
from oidc_verifier import verify_oidc_runtime_ready
from session_auth import verify_session_runtime_ready


READINESS_TIMEOUT_SECONDS = 2.0


async def verify_readiness(
    *,
    timeout_seconds: float = READINESS_TIMEOUT_SECONDS,
) -> None:
    """Verify only dependencies required to serve authenticated requests."""
    async with asyncio.timeout(timeout_seconds):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        await verify_session_runtime_ready()
        await verify_oidc_runtime_ready()
