"""Pure state transitions for monthly Grile operations.

This module has no PostgreSQL, Google API or filesystem dependencies. The
repository owns compare-and-set persistence; orchestration consumes these
deterministic transition results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal


MonthlyOperationStartStatus = Literal[
    "started",
    "already_running",
    "already_completed",
    "already_failed",
    "not_found",
]


@dataclass(frozen=True)
class MonthlyOperationReservation:
    status: Literal["enqueued", "already_running", "already_completed"]
    operation_id: int
    job_id: str | None = None
    operation: dict[str, Any] | None = None


@dataclass(frozen=True)
class MonthlyOperationStartResult:
    status: MonthlyOperationStartStatus
    operation_id: int
    operation: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class GrileMonthlyRetryBlockedError(RuntimeError):
    """Raised when a live reset has uncertain Google-side effects."""


def safe_persisted_result(
    operation: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return an independent JSON-compatible result for idempotent replays."""

    result = operation.get("result") if operation is not None else None
    if not isinstance(result, dict):
        return None
    return json.loads(json.dumps(result, ensure_ascii=False))


def operation_start_result(
    *,
    operation_id: int,
    operation: dict[str, Any] | None,
    transition_claimed: bool,
) -> MonthlyOperationStartResult:
    """Map the persisted CAS outcome to the worker's exhaustive state model."""

    if operation is None:
        return MonthlyOperationStartResult(
            status="not_found",
            operation_id=operation_id,
        )

    if transition_claimed:
        status: MonthlyOperationStartStatus = "started"
    else:
        persisted_status = str(operation.get("status"))
        status_by_persisted_value: dict[str, MonthlyOperationStartStatus] = {
            "running": "already_running",
            "completed": "already_completed",
            "failed": "already_failed",
        }
        status = status_by_persisted_value.get(
            persisted_status,
            "already_running",
        )

    return MonthlyOperationStartResult(
        status=status,
        operation_id=operation_id,
        operation=operation,
        result=safe_persisted_result(operation),
    )


def terminal_operation_status(
    result: dict[str, Any],
) -> Literal["completed", "failed"]:
    return "completed" if result.get("status") == "success" else "failed"
