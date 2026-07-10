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
        """
        SELECT
            item_code, item_name, reward_value, valid_from, valid_to,
            category, subcategory, source_file
        FROM incentive_products
        WHERE campaign_id = $1
        ORDER BY valid_from, valid_to, item_code
        """,
        campaign["id"],
    )
    periods_by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in products:
        key = (row["valid_from"], row["valid_to"])
        period = periods_by_key.setdefault(key, {
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "products": [],
            "reward_map": {},
            "source_file": row["source_file"],
        })
        product = {
            "item_code": str(row["item_code"]),
            "item_name": str(row["item_name"] or row["item_code"]),
            "reward_value": float(row["reward_value"]),
            "category": str(row["category"] or ""),
            "subcategory": str(row["subcategory"] or ""),
        }
        period["products"].append(product)
        period["reward_map"][product["item_code"]] = product["reward_value"]

    periods = list(periods_by_key.values())
    latest_reward_map = periods[-1]["reward_map"] if periods else {}
    item_codes = sorted({str(row["item_code"]) for row in products})

    return {
        "id": campaign["id"],
        "month": campaign["month"],
        "title": campaign["title"],
        "subtitle": campaign["subtitle"] or "",
        "description": campaign["description"] or "",
        # Compatibilitate pentru consumatorii care afiseaza lista curenta.
        "reward_map": latest_reward_map,
        "item_codes": item_codes,
        "periods": periods,
    }


async def list_incentive_campaigns(
    conn: asyncpg.Connection,
) -> list[dict[str, Any]]:
    """Returnează toate campaniile ordonate descrescător după lună."""
    rows = await conn.fetch(
        """
        SELECT ic.id, ic.month, ic.title, ic.subtitle, ic.description,
               COUNT(DISTINCT ip.item_code)::INT AS product_count,
               ic.created_at
        FROM incentive_campaigns ic
        LEFT JOIN incentive_products ip ON ip.campaign_id = ic.id
        GROUP BY ic.id
        ORDER BY ic.month DESC
        """
    )
    return [dict(r) for r in rows]
