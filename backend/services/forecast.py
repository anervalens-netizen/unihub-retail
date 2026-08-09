"""Application boundary for forecast SQL policies."""
from __future__ import annotations

from datetime import date
from typing import Any

from domain.reporting_sql import business_forecast_factor_ctes


async def get_forecast_factor(
    conn: Any,
    month: str,
    *,
    cutoff_date: date | None = None,
) -> float:
    """Read the weighted business-calendar forecast factor."""

    meta = await conn.fetchrow(
        f"""
        WITH {business_forecast_factor_ctes(cutoff_parameter="$2" if cutoff_date else None)}
        SELECT forecast_factor AS business_factor
        FROM forecast_meta
        """,
        month,
        *([cutoff_date] if cutoff_date else []),
    )
    return (
        float(meta["business_factor"])
        if meta and meta["business_factor"] is not None
        else 1.0
    )


__all__ = ["business_forecast_factor_ctes", "get_forecast_factor"]
