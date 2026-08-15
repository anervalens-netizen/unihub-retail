from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any

from request_context import bind_request_id, reset_request_id
import services.grile_pilot_v2_runtime as grile_pilot_v2_runtime
from services.sales_generation_lineage_guard import (
    guard_sales_generation_lineage_bound,
)


_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _validate_lineage(generation_hash: str, sales_revision: int) -> None:
    if not _SHA256_RE.fullmatch(generation_hash):
        raise ValueError("Campaign reporting generation hash is invalid")
    if (
        isinstance(sales_revision, bool)
        or not isinstance(sales_revision, int)
        or sales_revision < 1
    ):
        raise ValueError("Campaign reporting sales revision is invalid")


def _superseded_result(
    *, period: str, generation_hash: str, sales_revision: int
) -> dict[str, Any]:
    return {
        "status": "superseded",
        "period": period,
        "sales_generation_hash": generation_hash,
        "sales_generation_revision": sales_revision,
        "promotion": None,
        "contest": None,
        "grile_v2_job_id": None,
    }


async def publish_campaign_reporting_background(
    ctx: dict,
    period: str,
    requested_by_sub: str,
    reason: str,
    generation_hash: str,
    sales_revision: int,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Publish Campaigns/Contests and enqueue the exact sales projection."""
    from services.campaign_reporting import CampaignReportingPublisher
    from services.contest_reporting import ContestReportingPublisher

    _validate_lineage(generation_hash, sales_revision)
    token = bind_request_id(request_id) if request_id else None
    try:
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool

            pool = await get_pool()

        async with guard_sales_generation_lineage_bound(
            pool,
            month=period,
            generation_hash=generation_hash,
            sales_revision=sales_revision,
        ) as (status, publication_pool):
            if status == "superseded":
                return _superseded_result(
                    period=period,
                    generation_hash=generation_hash,
                    sales_revision=sales_revision,
                )
            promotion = await CampaignReportingPublisher(
                publication_pool
            ).publish_month(
                period, requested_by_sub=requested_by_sub, reason=reason
            )
            contest = await ContestReportingPublisher(
                publication_pool
            ).publish_month(
                period, requested_by_sub=requested_by_sub, reason=reason
            )
            grile_job = await grile_pilot_v2_runtime.enqueue_grile_pilot_v2_sync(
                month=period,
                trigger=f"sales_outbox:{generation_hash}:{sales_revision}",
                generation_hash=generation_hash,
                sales_revision=sales_revision,
                campaign_revision=promotion.revision,
                contest_revision=contest.revision,
            )
        return {
            "promotion": asdict(promotion),
            "contest": asdict(contest),
            "sales_generation_hash": generation_hash,
            "sales_generation_revision": sales_revision,
            "grile_v2_job_id": grile_job.job_id,
        }
    finally:
        if token is not None:
            reset_request_id(token)
