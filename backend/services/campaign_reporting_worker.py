from __future__ import annotations

from dataclasses import asdict

from request_context import bind_request_id, reset_request_id
import services.grile_pilot_v2_runtime as grile_pilot_v2_runtime


async def publish_campaign_reporting_background(
    ctx: dict,
    period: str,
    requested_by_sub: str,
    reason: str,
    request_id: str | None = None,
) -> dict:
    """Run the bounded, canonical Campaigns publisher in the imports worker."""
    from dataclasses import asdict
    from services.campaign_reporting import CampaignReportingPublisher
    from services.contest_reporting import ContestReportingPublisher
    token = bind_request_id(request_id) if request_id else None
    try:
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        promotion_publication = await CampaignReportingPublisher(pool).publish_month(
            period,
            requested_by_sub=requested_by_sub,
            reason=reason,
        )
        contest_publication = await ContestReportingPublisher(pool).publish_month(
            period,
            requested_by_sub=requested_by_sub,
            reason=reason,
        )
        await grile_pilot_v2_runtime.trigger_grile_pilot_v2_sync(
            period,
            trigger=f"campaign_reporting:{promotion_publication.revision}",
        )
        return {
            "promotion": asdict(promotion_publication),
            "contest": asdict(contest_publication),
        }
    finally:
        if token is not None:
            reset_request_id(token)

