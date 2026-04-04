from __future__ import annotations

from typing import Any

import asyncpg


async def get_incentive_campaign(
    conn: asyncpg.Connection,
    month: str,
) -> dict[str, Any] | None:
    """
    Returnează campania de incentive pentru luna dată, inclusiv reward_map per produs.
    Returnează None dacă nu există campanie pentru luna respectivă.
    """
    campaign = await conn.fetchrow(
        "SELECT id, month, title, subtitle, description FROM incentive_campaigns WHERE month = $1",
        month,
    )
    if campaign is None:
        return None

    products = await conn.fetch(
        "SELECT item_code, item_name, reward_value FROM incentive_products WHERE campaign_id = $1",
        campaign["id"],
    )
    reward_map = {r["item_code"]: float(r["reward_value"]) for r in products}

    return {
        "id": campaign["id"],
        "month": campaign["month"],
        "title": campaign["title"],
        "subtitle": campaign["subtitle"] or "",
        "description": campaign["description"] or "",
        "reward_map": reward_map,
    }


async def list_incentive_campaigns(
    conn: asyncpg.Connection,
) -> list[dict[str, Any]]:
    """Returnează toate campaniile ordonate descrescător după lună."""
    rows = await conn.fetch(
        """
        SELECT ic.id, ic.month, ic.title, ic.subtitle, ic.description,
               COUNT(ip.id)::INT AS product_count,
               ic.created_at
        FROM incentive_campaigns ic
        LEFT JOIN incentive_products ip ON ip.campaign_id = ic.id
        GROUP BY ic.id
        ORDER BY ic.month DESC
        """
    )
    return [dict(r) for r in rows]
