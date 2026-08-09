"""Pure state transitions for monthly Grile operations.

This module has no PostgreSQL, Google API or filesystem dependencies. The
repository owns compare-and-set persistence; orchestration consumes these
deterministic transition results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal


class MonthlyOperationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MonthlyOperationEvent(StrEnum):
    CLAIM = "claim"
    COMPLETE = "complete"
    FAIL = "fail"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class MonthlyOperationTransition:
    previous: MonthlyOperationState
    event: MonthlyOperationEvent
    current: MonthlyOperationState


class InvalidMonthlyOperationTransition(ValueError):
    """Raised before persistence when a lifecycle transition is impossible."""


_ALLOWED_TRANSITIONS: dict[
    tuple[MonthlyOperationState, MonthlyOperationEvent], MonthlyOperationState
] = {
    (MonthlyOperationState.QUEUED, MonthlyOperationEvent.CLAIM): MonthlyOperationState.RUNNING,
    (MonthlyOperationState.QUEUED, MonthlyOperationEvent.REJECT): MonthlyOperationState.FAILED,
    (MonthlyOperationState.RUNNING, MonthlyOperationEvent.COMPLETE): MonthlyOperationState.COMPLETED,
    (MonthlyOperationState.RUNNING, MonthlyOperationEvent.FAIL): MonthlyOperationState.FAILED,
}


def transition_monthly_operation(
    state: MonthlyOperationState | str,
    event: MonthlyOperationEvent | str,
) -> MonthlyOperationTransition:
    """Return one exhaustive deterministic transition or fail closed."""

    try:
        previous = MonthlyOperationState(state)
        requested_event = MonthlyOperationEvent(event)
    except ValueError as exc:
        raise InvalidMonthlyOperationTransition("Stare sau eveniment Grile necunoscut") from exc
    current = _ALLOWED_TRANSITIONS.get((previous, requested_event))
    if current is None:
        raise InvalidMonthlyOperationTransition(
            f"Tranziție Grile invalidă: {previous.value} + {requested_event.value}"
        )
    return MonthlyOperationTransition(
        previous=previous,
        event=requested_event,
        current=current,
    )


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

    persisted_raw = str(operation.get("status"))
    if transition_claimed:
        # The repository CAS result is the authority for a successful claim.
        # Some adapters return the row image captured before the UPDATE, so the
        # mapper must not reject an otherwise successful claim because that
        # image still says ``queued``.  New writes remain protected by the
        # explicit transition engine above and by the repository predicate.
        status: MonthlyOperationStartStatus = "started"
    else:
        try:
            persisted = MonthlyOperationState(persisted_raw)
        except ValueError:
            # Unknown persisted states fail closed as active.  This preserves
            # historical retry safety while the explicit transition engine
            # rejects unknown values before any new write.
            status = "already_running"
        else:
            status_by_persisted_value: dict[
                MonthlyOperationState, MonthlyOperationStartStatus
            ] = {
                MonthlyOperationState.QUEUED: "already_running",
                MonthlyOperationState.RUNNING: "already_running",
                MonthlyOperationState.COMPLETED: "already_completed",
                MonthlyOperationState.FAILED: "already_failed",
            }
            status = status_by_persisted_value[persisted]

    return MonthlyOperationStartResult(
        status=status,
        operation_id=operation_id,
        operation=operation,
        result=safe_persisted_result(operation),
    )


def terminal_operation_status(
    result: dict[str, Any],
) -> Literal["completed", "failed"]:
    event = (
        MonthlyOperationEvent.COMPLETE
        if result.get("status") == "success"
        else MonthlyOperationEvent.FAIL
    )
    return transition_monthly_operation(MonthlyOperationState.RUNNING, event).current.value  # type: ignore[return-value]
