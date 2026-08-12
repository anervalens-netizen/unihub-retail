from __future__ import annotations

from typing import Sequence

import asyncpg

from services.reporting_refresh_lifecycle import (
    rebuild_agent_lifecycle_reporting,
    list_completed_import_months,
)
from services.reporting_refresh_month import (
    rebuild_reporting_cartela_month,
    rebuild_reporting_month,
)
from services.reporting_refresh_premium import (
    _PREMIUM_CAMERA_FILE,
    _PREMIUM_GLASS_INSERT_SQL,
    _load_premium_camera_rows,
)


async def refresh_premium_glass_indicators(
    conn: asyncpg.Connection,
) -> None:
    await conn.execute("TRUNCATE premium_glass_item_models")
    await conn.execute(
        _PREMIUM_GLASS_INSERT_SQL,
        *_load_premium_camera_rows(),
    )
    await conn.execute("ANALYZE premium_glass_item_models")


async def rebuild_reporting_all(
    conn: asyncpg.Connection,
    months: Sequence[str] | None = None,
) -> list[str]:
    target_months = (
        list(months)
        if months is not None
        else await list_completed_import_months(conn)
    )
    for import_month in target_months:
        async with conn.transaction():
            await rebuild_reporting_month(conn, import_month)
    async with conn.transaction():
        await rebuild_agent_lifecycle_reporting(conn)
    return target_months
