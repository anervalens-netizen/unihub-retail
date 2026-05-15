from __future__ import annotations

import logging
from datetime import datetime

import asyncpg
from prometheus_client import Gauge

logger = logging.getLogger(__name__)

retail_revenue_current_month = Gauge(
    "retail_revenue_current_month",
    "Total sales revenue for the current month (RON).",
)
retail_active_agents_count = Gauge(
    "retail_active_agents_count",
    "Number of distinct active agents with sales this month.",
)
retail_active_stores_count = Gauge(
    "retail_active_stores_count",
    "Number of distinct stores with sales this month.",
)
retail_active_campaigns_products = Gauge(
    "retail_active_campaigns_products",
    "Number of focus campaign products active this month (0 if no campaign).",
)


async def update_business_metrics(pool: asyncpg.Pool) -> None:
    month = datetime.now().strftime("%Y-%m")
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(SUM(total_sales), 0)          AS revenue,
                    COUNT(DISTINCT agent)::INT              AS agents,
                    COUNT(DISTINCT site_code)::INT          AS stores
                FROM reporting_agent_month
                WHERE import_month = $1
                """,
                month,
            )
        if row:
            retail_revenue_current_month.set(float(row["revenue"]))
            retail_active_agents_count.set(row["agents"])
            retail_active_stores_count.set(row["stores"])

        async with pool.acquire() as conn:
            focus_row = await conn.fetchrow(
                """
                SELECT COUNT(DISTINCT item_code) FILTER (WHERE total_quantity > 0)::INT
                    AS focus_products
                FROM reporting_focus_item_month
                WHERE import_month = $1
                """,
                month,
            )
        if focus_row and focus_row["focus_products"] is not None:
            retail_active_campaigns_products.set(focus_row["focus_products"])

    except Exception:
        logger.exception("Failed to update retail business metrics for month %s", month)
