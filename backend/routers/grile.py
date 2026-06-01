from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from auth import AuthClaims, require_auth
from db.connection import get_pool
from repositories.grile import GrileRepository
from services.grile import _run_to_dict, get_overview, resolve_month
from services.jobs import enqueue_grile_check

router = APIRouter(prefix="/api/grile", tags=["grile"])


@router.get("/overview")
async def grile_overview(month: str | None = Query(default=None)) -> dict[str, Any]:
    pool = await get_pool()
    return await get_overview(pool, await resolve_month(pool, month))


@router.post("/run")
async def grile_run(
    month: str | None = Query(default=None),
    claims: AuthClaims = Depends(require_auth),
) -> dict[str, Any]:
    pool = await get_pool()
    resolved = await resolve_month(pool, month)
    repo = GrileRepository(pool)
    running = await repo.get_running_run(resolved)
    if running is not None:
        return {"status": "already_running", "run": _run_to_dict(running)}
    await enqueue_grile_check(
        month=resolved, source="manual", source_snapshot_id=None, triggered_by_email=claims.email
    )
    return {"status": "enqueued", "month": resolved}


@router.get("/run-status")
async def grile_run_status(month: str | None = Query(default=None)) -> dict[str, Any]:
    pool = await get_pool()
    repo = GrileRepository(pool)
    latest = await repo.get_latest_run(await resolve_month(pool, month))
    return {"run": _run_to_dict(latest) if latest is not None else None}
