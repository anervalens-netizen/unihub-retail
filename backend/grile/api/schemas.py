from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.common import MonthStr, NonNegativeInt, PercentageFloat


class GrileApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GrileRunResponse(GrileApiModel):
    id: int
    run_month: MonthStr
    source: Literal["manual", "auto"]
    source_snapshot_id: int | None = None
    status: Literal["queued", "running", "completed", "failed"]
    active: bool
    progress_current: NonNegativeInt
    progress_total: NonNegativeInt
    ok_count: NonNegativeInt
    problem_count: NonNegativeInt
    error_count: NonNegativeInt
    duration_ms: NonNegativeInt | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class GrileProviderStatus(GrileApiModel):
    state: Literal["fresh", "stale", "error", "unknown"]
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    stale_age_seconds: NonNegativeInt | None = None


class GrileStoreResponse(GrileApiModel):
    site_code: str
    sheet_id: str | None = None
    locatie: str
    firma: str
    regional: str
    asm: str
    team_leader_name: str | None = None
    completion_pct: PercentageFloat | None = None
    last_edit: datetime | None = None
    checked_at: datetime | None = None
    grila_target: Decimal | None = None
    grila_sales: Decimal | None = None
    db_target: Decimal | None = None
    db_sales_mtd: Decimal | None = None
    target_diff: Decimal | None = None
    sales_diff: Decimal | None = None
    db_max_sale_date: date | None = None
    fill_status: str | None = None
    target_status: str | None = None
    sales_status: str | None = None
    missing_days: list[int] | None = None
    days_elapsed: NonNegativeInt | None = None
    completion_algorithm_version: int = Field(ge=1)
    completion_as_of: date | None = None
    completion_window_status: Literal["current", "legacy_incomplete_window"]
    provider_status: GrileProviderStatus
    # Compatibility projection fields. Provider failures are exposed only in
    # provider_status and never overwrite the last successful business values.
    error_code: str | None = None
    error_message: str | None = None


class GrileFirmResponse(GrileApiModel):
    name: str
    stores: list[GrileStoreResponse]


class GrileTeamLeaderResponse(GrileApiModel):
    name: str | None = None
    firms: list[GrileFirmResponse]


class GrileManagerResponse(GrileApiModel):
    name: str
    store_count: NonNegativeInt
    ok: NonNegativeInt
    problems: NonNegativeInt
    business_unknown: NonNegativeInt
    provider_fresh: NonNegativeInt
    provider_errors: NonNegativeInt
    provider_stale: NonNegativeInt
    provider_unknown: NonNegativeInt
    legacy_completion_windows: NonNegativeInt
    avg_completion: PercentageFloat | None = None
    team_leaders: list[GrileTeamLeaderResponse]


class GrileOverviewSummary(GrileApiModel):
    business_ok: NonNegativeInt
    business_problems: NonNegativeInt
    business_unknown: NonNegativeInt
    provider_fresh: NonNegativeInt
    provider_errors: NonNegativeInt
    provider_stale: NonNegativeInt
    provider_unknown: NonNegativeInt
    legacy_completion_windows: NonNegativeInt


class GrileOverviewResponse(GrileApiModel):
    month: MonthStr
    total_sheets: NonNegativeInt
    run: GrileRunResponse | None = None
    summary: GrileOverviewSummary
    managers: list[GrileManagerResponse]


class GrileRunEnqueueResponse(GrileApiModel):
    status: Literal["enqueued", "already_running"]
    month: MonthStr | None = None
    run_id: int | None = None
    job_id: str | None = None
    run: GrileRunResponse | None = None


class GrileRunStatusResponse(GrileApiModel):
    run: GrileRunResponse | None = None


class GrileStoreRefreshEnqueueResponse(GrileApiModel):
    status: Literal["enqueued", "already_running"]
    month: MonthStr
    operation_id: int
    job_id: str | None = None


class GrileStoreRefreshOperationResponse(GrileApiModel):
    id: int
    run_month: MonthStr
    site_code: str
    status: Literal["queued", "running", "completed", "failed", "cancelled", "unknown"]
    projection_applied: bool | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None


class GrileStoreRefreshOperationEnvelope(GrileApiModel):
    operation: GrileStoreRefreshOperationResponse


class GrilePermissionsResponse(GrileApiModel):
    can_run: bool


class GrileAgentTargetOperationResponse(GrileApiModel):
    id: int
    run_month: MonthStr
    mode: Literal["dry_run", "sync"]
    status: str
    job_id: str | None = None
    before_sha256: str | None = None
    after_sha256: str | None = None
    before_count: int | None = None
    after_count: int | None = None
    diff: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class GrileAgentTargetEnqueueResponse(GrileApiModel):
    status: str
    operation_id: int
    job_id: str | None = None
    operation: GrileAgentTargetOperationResponse | None = None


class GrileAgentTargetOperationEnvelope(GrileApiModel):
    operation: GrileAgentTargetOperationResponse


GrileMonthlyOp = Literal["finalize", "archive", "reset"]


class GrileMonthlyManifestResponse(GrileApiModel):
    id: int
    operation_id: int
    month: MonthStr
    operation: GrileMonthlyOp
    status: Literal[
        "building",
        "failed",
        "verified",
        "approved",
        "consumed",
        "rolled_back",
        "uncertain",
    ]
    expected: dict[str, Any] = Field(default_factory=dict)
    processed: dict[str, Any] = Field(default_factory=dict)
    error_count: NonNegativeInt
    manifest_sha256: str | None = None
    approved: bool
    created_at: datetime | None = None
    verified_at: datetime | None = None
    approved_at: datetime | None = None
    consumed_at: datetime | None = None


class GrileMonthlyManifestEnvelope(GrileApiModel):
    manifest: GrileMonthlyManifestResponse | None = None


class GrileMonthlyRunResponse(GrileApiModel):
    status: Literal["enqueued", "already_running", "already_completed"]
    job_id: str | None = None
    operation_id: int
    op: GrileMonthlyOp
    month: MonthStr
    month_label: str
    next_month_label: str | None = None
    dry_run: bool | None = None
    operation: dict[str, Any] | None = None


class GrileMonthlyResultResponse(GrileApiModel):
    op: GrileMonthlyOp
    month_label: str
    status: Literal["success", "failed"]
    output: str
    exit_code: int | None = None
    dry_run: bool | None = None
    manifest: GrileMonthlyManifestResponse | None = None


class GrileMonthlyJobResponse(GrileApiModel):
    job_id: str
    status: Literal["queued", "in_progress", "complete", "not_found"]
    result: dict[str, Any] | None = None
    error: str | None = None
