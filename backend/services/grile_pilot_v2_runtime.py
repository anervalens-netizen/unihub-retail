"""Compatibility tombstone for queued August 2026 Grile V2 jobs."""

from __future__ import annotations

from typing import Any


async def grile_pilot_v2_sync_background(
    ctx: dict,
    month: str,
    trigger: str,
    generation_hash: str,
    sales_revision: int,
    campaign_revision: int,
    contest_revision: int,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Drain a legacy queued job without reading or writing Google Sheets."""
    del ctx, trigger, request_id
    return {
        "status": "retired",
        "contract": "grile-v2-queued-job-retired-v1",
        "month": month,
        "sales_generation_hash": generation_hash,
        "sales_generation_revision": sales_revision,
        "campaign_revision": campaign_revision,
        "contest_revision": contest_revision,
        "synced": [],
        "skipped": [],
        "failed": [],
    }
