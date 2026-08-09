"""Durable Grile operation lookups independent from ephemeral ARQ state."""
from __future__ import annotations


async def get_grile_monthly_operation_by_job_id(job_id: str) -> dict | None:
    from db.connection import get_pool
    from repositories.grile_monthly_operations import get_by_job_id

    return await get_by_job_id(await get_pool(), job_id)


async def get_grile_target_sync_operation(operation_id: int) -> dict | None:
    from db.connection import get_pool
    from repositories.grile_agent_target_sync import GrileAgentTargetSyncRepository

    return await GrileAgentTargetSyncRepository(await get_pool()).get(operation_id)
