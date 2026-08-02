from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from auth import AuthClaims, require_auth
from db.connection import get_pool
from permissions import require_privileged_access
from privileged_access import (
    GRILE_FINALIZER_GROUPS_ENV,
    GRILE_TARGET_SYNC_GROUPS_ENV,
    has_configured_group,
)
from rate_limits import GRILE_JOB_LIMIT, rate_limit
from repositories.grile import GrileRepository
from services.grile import _run_to_dict, get_overview, resolve_month
from services.grile_monthly import (
    GrileMonthlyRetryBlockedError,
    MonthlyIntegrityError,
    approve_monthly_manifest,
    fetch_download,
    get_latest_monthly_manifest,
    next_ym,
    public_manifest_payload,
    ro_month_label,
)
from services.jobs import (
    enqueue_grile_check,
    enqueue_grile_store_refresh,
    enqueue_grile_monthly,
    enqueue_grile_target_sync,
    get_grile_monthly_operation_by_job_id,
    get_grile_target_sync_operation,
    get_job_status,
    JobStatus,
)

router = APIRouter(prefix="/api/grile", tags=["grile"])

MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ── verificare (read-only) ────────────────────────────────────────────────────

@router.get("/overview")
async def grile_overview(
    month: str | None = Query(default=None),
    _claims: AuthClaims = Depends(require_auth),
) -> dict[str, Any]:
    pool = await get_pool()
    return await get_overview(pool, await resolve_month(pool, month))


@router.post("/run")
async def grile_run(
    month: str | None = Query(default=None),
    claims: AuthClaims = Depends(require_auth),
    _rate_limit: None = Depends(rate_limit(GRILE_JOB_LIMIT)),
) -> dict[str, Any]:
    pool = await get_pool()
    resolved = await resolve_month(pool, month)
    result = await enqueue_grile_check(
        month=resolved, source="manual", source_snapshot_id=None, triggered_by_sub=claims.sub
    )
    if result.status == "already_running":
        return {
            "status": result.status,
            "run": _run_to_dict(result.run) if result.run is not None else None,
        }
    return {
        "status": result.status,
        "month": resolved,
        "run_id": result.run_id,
        "job_id": result.job.job_id if result.job is not None else None,
    }


@router.get("/run-status")
async def grile_run_status(
    month: str | None = Query(default=None),
    _claims: AuthClaims = Depends(require_auth),
) -> dict[str, Any]:
    pool = await get_pool()
    repo = GrileRepository(pool)
    latest = await repo.get_latest_run(await resolve_month(pool, month))
    return {"run": _run_to_dict(latest) if latest is not None else None}


@router.post("/stores/{site_code}/refresh")
async def grile_store_refresh(
    site_code: str = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    month: str | None = Query(default=None),
    claims: AuthClaims = Depends(require_auth),
    _rate_limit: None = Depends(rate_limit(GRILE_JOB_LIMIT)),
) -> dict[str, Any]:
    resolved = await resolve_month(await get_pool(), month)
    try:
        result = await enqueue_grile_store_refresh(
            month=resolved,
            site_code=site_code,
            requested_by_sub=claims.sub,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {
        "status": result.status,
        "month": resolved,
        "operation_id": result.operation_id,
        "job_id": result.job.job_id if result.job is not None else None,
        "operation": result.operation,
    }


# ── inchidere luna (WRITE Google Sheets — doar admin) ──────────────────────────

def can_grile_admin(claims: AuthClaims) -> bool:
    return has_configured_group(claims.groups, GRILE_FINALIZER_GROUPS_ENV)


def require_grile_admin(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    return require_privileged_access(
        request=request,
        claims=claims,
        allowed=can_grile_admin(claims),
        resource="grile_monthly",
        detail="Inchiderea de luna (finalizare/arhiva/reset) e limitata la administratorul grilelor.",
        fallback_route="/api/grile/monthly",
    )


def can_grile_target_sync(claims: AuthClaims) -> bool:
    return has_configured_group(claims.groups, GRILE_TARGET_SYNC_GROUPS_ENV)


def require_grile_target_sync(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    return require_privileged_access(
        request=request,
        claims=claims,
        allowed=can_grile_target_sync(claims),
        resource="grile_agent_target_sync",
        detail="Sincronizarea targetelor necesita grupul OIDC dedicat.",
        fallback_route="/api/grile/agent-targets/sync",
    )


class AgentTargetRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str

    @field_validator("month")
    @classmethod
    def _valid_month(cls, value: str) -> str:
        if not MONTH_PATTERN.match(value):
            raise ValueError("month trebuie sa fie YYYY-MM")
        return value


def _target_operation_payload(operation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: operation.get(key)
        for key in (
            "id",
            "run_month",
            "mode",
            "status",
            "job_id",
            "before_sha256",
            "after_sha256",
            "before_count",
            "after_count",
            "diff",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
        )
    }


@router.post("/agent-targets/diff")
async def grile_agent_targets_diff(
    body: AgentTargetRunRequest,
    claims: AuthClaims = Depends(require_auth),
    _rate_limit: None = Depends(rate_limit(GRILE_JOB_LIMIT)),
) -> dict[str, Any]:
    result = await enqueue_grile_target_sync(
        month=body.month,
        mode="dry_run",
        requested_by_sub=claims.sub,
    )
    return {
        "status": result.status,
        "operation_id": result.operation_id,
        "job_id": result.job.job_id if result.job is not None else None,
        "operation": (
            _target_operation_payload(result.operation)
            if result.operation is not None
            else None
        ),
    }


@router.post("/agent-targets/sync")
async def grile_agent_targets_sync(
    body: AgentTargetRunRequest,
    claims: AuthClaims = Depends(require_grile_target_sync),
    _rate_limit: None = Depends(rate_limit(GRILE_JOB_LIMIT)),
) -> dict[str, Any]:
    result = await enqueue_grile_target_sync(
        month=body.month,
        mode="sync",
        requested_by_sub=claims.sub,
    )
    return {
        "status": result.status,
        "operation_id": result.operation_id,
        "job_id": result.job.job_id if result.job is not None else None,
        "operation": (
            _target_operation_payload(result.operation)
            if result.operation is not None
            else None
        ),
    }


@router.get("/agent-targets/operations/{operation_id}")
async def grile_agent_targets_operation(
    operation_id: int,
    _claims: AuthClaims = Depends(require_auth),
) -> dict[str, Any]:
    operation = await get_grile_target_sync_operation(operation_id)
    if operation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operatia nu exista.")
    return {"operation": _target_operation_payload(operation)}


class MonthlyRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["finalize", "archive", "reset"]
    month: str
    dry_run: bool = True
    approved_manifest_id: int | None = None

    @field_validator("month")
    @classmethod
    def _valid_month(cls, v: str) -> str:
        if not MONTH_PATTERN.match(v):
            raise ValueError("month trebuie sa fie YYYY-MM")
        return v

    @model_validator(mode="after")
    def _manifest_contract(self) -> "MonthlyRunRequest":
        if self.op == "reset" and not self.dry_run and self.approved_manifest_id is None:
            raise ValueError("resetul live necesita approved_manifest_id")
        if self.op != "reset" and self.approved_manifest_id is not None:
            raise ValueError("approved_manifest_id este permis numai pentru reset")
        return self


@router.get("/monthly/permissions")
async def grile_monthly_permissions(claims: AuthClaims = Depends(require_auth)) -> dict[str, Any]:
    """UI-ul afiseaza sectiunea de inchidere doar daca utilizatorul e admin."""
    return {"can_run": can_grile_admin(claims)}


@router.post("/monthly/run")
async def grile_monthly_run(
    body: MonthlyRunRequest,
    claims: AuthClaims = Depends(require_grile_admin),
    _rate_limit: None = Depends(rate_limit(GRILE_JOB_LIMIT)),
) -> dict[str, Any]:
    try:
        result = await enqueue_grile_monthly(
            op=body.op,
            month=body.month,
            dry_run=body.dry_run,
            requested_by_sub=claims.sub,
            approved_manifest_id=body.approved_manifest_id,
        )
    except GrileMonthlyRetryBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    persisted_operation = result.operation or {}
    effective_op = persisted_operation.get("op") or body.op
    effective_month = persisted_operation.get("closing_month") or body.month
    effective_dry_run = bool(persisted_operation.get("dry_run", body.dry_run))
    payload: dict[str, Any] = {
        "status": result.status,
        "job_id": result.job_id,
        "operation_id": result.operation_id,
        "op": effective_op,
        "month": effective_month,
        "month_label": ro_month_label(effective_month),
    }
    if result.operation is not None:
        payload["operation"] = result.operation
    if effective_op == "reset":
        payload["next_month_label"] = ro_month_label(next_ym(effective_month))
        payload["dry_run"] = effective_dry_run
    return payload


@router.get("/monthly/manifests/{month}")
async def grile_monthly_manifest(
    month: str,
    _claims: AuthClaims = Depends(require_grile_admin),
) -> dict[str, Any]:
    if not MONTH_PATTERN.match(month):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="month invalid (YYYY-MM)")
    pool = await get_pool()
    manifest = await get_latest_monthly_manifest(pool, month=month)
    return {"manifest": public_manifest_payload(manifest) if manifest is not None else None}


@router.post("/monthly/manifests/{manifest_id}/approve")
async def grile_monthly_manifest_approve(
    manifest_id: int,
    claims: AuthClaims = Depends(require_grile_admin),
    _rate_limit: None = Depends(rate_limit(GRILE_JOB_LIMIT)),
) -> dict[str, Any]:
    pool = await get_pool()
    try:
        manifest = await approve_monthly_manifest(
            pool,
            manifest_id=manifest_id,
            approved_by_sub=claims.sub,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MonthlyIntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"manifest": manifest}


@router.get("/monthly/job/{job_id}")
async def grile_monthly_job(
    job_id: str,
    claims: AuthClaims = Depends(require_grile_admin),
) -> dict[str, Any]:
    try:
        operation = await get_grile_monthly_operation_by_job_id(job_id)
    except Exception as exc:  # noqa: BLE001 - DB status is required for authority
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job status unavailable",
        ) from exc
    if operation is not None:
        operation_status = str(operation.get("status") or "")
        if operation_status in {"completed", "failed"}:
            return {
                "job_id": job_id,
                "status": "complete",
                "result": operation.get("result") if operation_status == "completed" else None,
                "error": operation.get("error_message") if operation_status == "failed" else None,
            }
        js = await get_job_status(job_id)
        if js.status in {JobStatus.QUEUED, JobStatus.IN_PROGRESS}:
            return {
                "job_id": js.job_id,
                "status": js.status.value,
                "result": js.result,
                "error": js.error,
            }
        detail_status = (
            "backend_unavailable"
            if js.status is JobStatus.BACKEND_UNAVAILABLE
            else "unknown"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": detail_status,
                "operation_id": operation.get("id"),
                "job_id": job_id,
            },
        )
    js = await get_job_status(job_id)
    if js.status in {JobStatus.BACKEND_UNAVAILABLE, JobStatus.UNKNOWN}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": (
                    "backend_unavailable"
                    if js.status is JobStatus.BACKEND_UNAVAILABLE
                    else "unknown"
                ),
                "operation_id": None,
                "job_id": job_id,
            },
        )
    return {
        "job_id": js.job_id,
        "status": js.status.value,
        "result": js.result,
        "error": js.error,
    }


@router.get("/monthly/download/{kind}/{month}")
async def grile_monthly_download(
    kind: Literal["final", "archive"],
    month: str,
    claims: AuthClaims = Depends(require_grile_admin),
) -> Response:
    if not MONTH_PATTERN.match(month):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="month invalid (YYYY-MM)")
    try:
        content, filename, media_type = await fetch_download(kind, month)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
