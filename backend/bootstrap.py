from __future__ import annotations

import asyncpg


async def ensure_tl_users_and_assignments(conn: asyncpg.Connection) -> None:
    """Create default TL (Team Leader) users if they don't exist.
    
    If needed, add TL user creation logic here.
    For now, this is a no-op stub replacing the original bootstrap function.
    """
    pass
