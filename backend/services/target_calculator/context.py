"""Repository-independent Target Calculator context projection."""

from __future__ import annotations

from typing import Any


def build_target_context(
    *,
    latest_month: str,
    suggested_month: str,
    target_total: Any,
    cohort: list[dict[str, Any]],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    return {
        "latest_sales_month": latest_month,
        "suggested_target_month": suggested_month,
        "suggested_cohort_month": latest_month,
        "suggested_total_target": float(target_total),
        **defaults,
        "active_store_count": len(cohort),
        "regionals": sorted({row["regional"] for row in cohort}),
    }
