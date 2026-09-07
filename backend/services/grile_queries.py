"""Read-side application facade for Grile HTTP operations."""
from __future__ import annotations

from typing import Any

import asyncpg

from repositories.grile import GrileRepository
from services.grile import _run_to_dict, get_overview, resolve_month
from services.grile_monthly import (
    approve_monthly_manifest,
    get_latest_monthly_manifest,
    public_manifest_payload,
)


class GrileQueryService:
    """Keep Grile persistence and pool access out of HTTP routers."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.repo = GrileRepository(pool)

    async def resolve_month(self, month: str | None) -> str:
        return await resolve_month(self.pool, month)

    async def overview(self, month: str | None) -> dict[str, Any]:
        resolved = await self.resolve_month(month)
        return await get_overview(self.pool, resolved)

    async def run_status(self, month: str | None) -> dict[str, Any]:
        resolved = await self.resolve_month(month)
        await self.repo.reconcile_stale_runs(run_month=resolved)
        latest = await self.repo.get_latest_run(resolved)
        return {"run": _run_to_dict(latest) if latest is not None else None}

    async def store_refresh(self, operation_id: int) -> dict[str, Any] | None:
        operation = await self.repo.get_store_refresh(operation_id)
        return dict(operation) if operation is not None else None

    async def latest_monthly_manifest(self, month: str) -> dict[str, Any] | None:
        manifest = await get_latest_monthly_manifest(self.pool, month=month)
        return public_manifest_payload(manifest) if manifest is not None else None

    async def approve_monthly_manifest(
        self,
        *,
        manifest_id: int,
        approved_by_sub: str,
    ) -> dict[str, Any]:
        return await approve_monthly_manifest(
            self.pool,
            manifest_id=manifest_id,
            approved_by_sub=approved_by_sub,
        )
