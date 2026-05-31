from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from auth import AuthClaims, require_auth
from db.connection import get_pool
from repositories.grile import GrileRepository
from services.grile import _run_to_dict, get_overview
from services.jobs import enqueue_grile_check

router = APIRouter(prefix="/api/grile", tags=["grile"])


def _default_month() -> str:
    return datetime.now().strftime("%Y-%m")


@router.get("/overview")
async def grile_overview(month: str = Query(default_factory=_default_month)) -> dict[str, Any]:
    pool = await get_pool()
    return await get_overview(pool, month)


@router.post("/run")
async def grile_run(
    month: str = Query(default_factory=_default_month),
    claims: AuthClaims = Depends(require_auth),
) -> dict[str, Any]:
    pool = await get_pool()
    repo = GrileRepository(pool)
    running = await repo.get_running_run(month)
    if running is not None:
        return {"status": "already_running", "run": _run_to_dict(running)}
    await enqueue_grile_check(
        month=month, source="manual", source_snapshot_id=None, triggered_by_email=claims.email
    )
    return {"status": "enqueued", "month": month}


@router.get("/run-status")
async def grile_run_status(month: str = Query(default_factory=_default_month)) -> dict[str, Any]:
    pool = await get_pool()
    repo = GrileRepository(pool)
    latest = await repo.get_latest_run(month)
    return {"run": _run_to_dict(latest) if latest is not None else None}
