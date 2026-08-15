"""Compatibility facade for split monthly Grile persistence boundaries."""

from grile.domain.monthly_state import (
    GrileMonthlyRetryBlockedError,
    MonthlyOperationReservation,
    MonthlyOperationStartResult,
)
from repositories.grile_monthly_lifecycle import (
    fail,
    fail_queued,
    finish,
    finish_reset_success,
    get_execution_lease,
    heartbeat,
    mark_cancelled_uncertain,
    start,
)
from repositories.grile_monthly_manifests import (
    approve_manifest,
    get_latest_manifest,
    get_manifest,
    get_operation_manifest,
    persist_manifest_result,
)
from repositories.grile_monthly_reconciliation import (
    claim_reconciliation_candidates,
    list_reset_items_for_reconciliation,
    mark_item_recovery_required,
    mark_item_safe_retry,
    mark_reconciliation_result,
)
from repositories.grile_monthly_reservations import attach_job, get_by_job_id, reserve
from repositories.grile_monthly_repository_types import (
    EXECUTION_LEASE_SECONDS,
    MonthlyExecutionLease,
    ResetItemInput,
    manifest_to_dict,
    operation_to_dict,
)
from repositories.grile_monthly_reset_items import (
    claim_reset_item,
    confirm_reset_clear,
    confirm_reset_rollback,
    ensure_reset_items,
    finish_reset_item,
    get_previous_completed_reset_item,
    prepare_reset_clear,
    prepare_reset_rollback,
    record_reset_item_backup,
    record_reset_item_rollback,
)


__all__ = [
    "EXECUTION_LEASE_SECONDS",
    "GrileMonthlyRetryBlockedError",
    "MonthlyExecutionLease",
    "MonthlyOperationReservation",
    "MonthlyOperationStartResult",
    "ResetItemInput",
    "approve_manifest",
    "attach_job",
    "claim_reconciliation_candidates",
    "claim_reset_item",
    "confirm_reset_clear",
    "confirm_reset_rollback",
    "ensure_reset_items",
    "fail",
    "fail_queued",
    "finish",
    "finish_reset_item",
    "finish_reset_success",
    "get_by_job_id",
    "get_execution_lease",
    "get_latest_manifest",
    "get_manifest",
    "get_operation_manifest",
    "get_previous_completed_reset_item",
    "heartbeat",
    "list_reset_items_for_reconciliation",
    "manifest_to_dict",
    "mark_cancelled_uncertain",
    "mark_item_recovery_required",
    "mark_item_safe_retry",
    "mark_reconciliation_result",
    "operation_to_dict",
    "persist_manifest_result",
    "prepare_reset_clear",
    "prepare_reset_rollback",
    "record_reset_item_backup",
    "record_reset_item_rollback",
    "reserve",
    "start",
]
