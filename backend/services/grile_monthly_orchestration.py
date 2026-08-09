"""Typed orchestration for fenced monthly Grile operations.

All side effects are injected at call time.  This keeps the state machine
independent from Google/DB adapters and lets tests exercise crash boundaries.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Coroutine


AsyncCallable = Callable[..., Awaitable[Any]]
SyncCallable = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class MonthlyRunPorts:
    valid_ops: frozenset[str]
    owner_hex: Callable[[], str]
    get_pool: Callable[[], Awaitable[Any]]
    start_operation: AsyncCallable
    heartbeat_operation: AsyncCallable
    finish_operation: AsyncCallable
    run_with_lease: AsyncCallable
    persist_manifest: AsyncCallable
    persist_reset_success: AsyncCallable
    fetch_manifest: AsyncCallable
    finalize_execution: SyncCallable
    archive_execution: SyncCallable
    reset_execution: SyncCallable
    base_manifest: SyncCallable
    public_manifest_payload: SyncCallable
    finalize_manifest: SyncCallable
    ro_month_label: Callable[[str], str]
    next_month: Callable[[str], str]
    utc_now: Callable[[], str]
    manifest_error_type: type[BaseException]
    integrity_error_type: type[BaseException]


@dataclass(slots=True)
class MonthlyRunState:
    ports: MonthlyRunPorts
    pool: Any
    operation_id: int | None
    op: str
    month: str
    only: str | None
    dry_run: bool
    requested_by_sub: str
    approved_manifest_id: int | None
    execution_owner: str
    execution_epoch: int


@dataclass(slots=True)
class MonthlyRunOutcome:
    status: str = "success"
    exit_code: int = 0
    error_code: str | None = None
    execution: Any | None = None
    manifest_record: dict[str, Any] | None = None


def _validate_request(ports: MonthlyRunPorts, op: str | None, month: str | None) -> None:
    if op not in ports.valid_ops:
        raise ValueError(f"Operatie necunoscuta: {op}")
    if month is None:
        raise ValueError("month is required")


def _not_started_result(
    ports: MonthlyRunPorts,
    *,
    operation_id: int,
    start: Any,
    fallback_op: str | None,
    fallback_month: str | None,
    fallback_dry_run: bool,
) -> dict[str, Any]:
    if start.status == "already_completed" and start.result is not None:
        replay = dict(start.result)
        replay.update(
            operation_id=operation_id,
            operation_status="completed",
            idempotent_replay=True,
        )
        return replay
    persisted = start.operation or {}
    persisted_op = str(persisted.get("op") or fallback_op or "unknown")
    persisted_month = persisted.get("closing_month") or fallback_month
    persisted_dry_run = bool(persisted.get("dry_run", fallback_dry_run))
    failed = start.status in {"already_failed", "not_found"}
    return {
        "op": persisted_op,
        "month_label": (
            ports.ro_month_label(str(persisted_month)) if persisted_month else None
        ),
        "status": "failed" if failed else "no_op",
        "output": f"Operation {operation_id} was not started: {start.status}.",
        "exit_code": -1 if failed else 0,
        "dry_run": persisted_dry_run if persisted_op == "reset" else None,
        "operation_id": operation_id,
        "operation_status": start.status.removeprefix("already_"),
        "idempotent_replay": True,
    }


async def _claim_run(
    ports: MonthlyRunPorts,
    pool: Any,
    *,
    op: str | None,
    month: str | None,
    only: str | None,
    dry_run: bool,
    operation_id: int | None,
    execution_owner_hint: str | None,
) -> tuple[MonthlyRunState | None, dict[str, Any] | None]:
    if operation_id is None:
        assert op is not None and month is not None
        return MonthlyRunState(
            ports=ports,
            pool=pool,
            operation_id=None,
            op=op,
            month=month,
            only=only,
            dry_run=dry_run,
            requested_by_sub="direct-execution",
            approved_manifest_id=None,
            execution_owner="",
            execution_epoch=0,
        ), None
    requested_owner = execution_owner_hint or ports.owner_hex()
    start = await ports.start_operation(
        pool, operation_id, execution_owner=requested_owner
    )
    if start.status != "started":
        return None, _not_started_result(
            ports,
            operation_id=operation_id,
            start=start,
            fallback_op=op,
            fallback_month=month,
            fallback_dry_run=dry_run,
        )
    operation = start.operation
    if operation is None:
        raise RuntimeError("Started monthly operation has no persisted state")
    requested_by_sub = str(operation.get("requested_by_sub") or "")
    if not requested_by_sub:
        raise RuntimeError("Persisted monthly operation has no OIDC subject")
    persisted_month = operation.get("closing_month")
    resolved_month = (
        persisted_month
        if isinstance(persisted_month, str) and persisted_month
        else None
    )
    state = MonthlyRunState(
        ports=ports,
        pool=pool,
        operation_id=operation_id,
        op=str(operation["op"]),
        month=str(resolved_month) if resolved_month is not None else "",
        only=operation.get("only_filter"),
        dry_run=bool(operation["dry_run"]),
        requested_by_sub=requested_by_sub,
        approved_manifest_id=operation.get("approved_manifest_id"),
        execution_owner=str(operation.get("execution_owner") or requested_owner),
        execution_epoch=int(operation.get("execution_epoch", 1)),
    )
    _validate_request(ports, state.op, state.month or None)
    if not state.execution_owner or state.execution_epoch <= 0:
        raise ports.integrity_error_type(
            "operation_lease_missing", "Monthly operation lease is missing"
        )
    return state, None


def _empty_failure_manifest(
    state: MonthlyRunState,
    error_code: str,
    *,
    status: str = "failed",
) -> dict[str, Any]:
    return state.ports.base_manifest(
        month=state.month,
        operation=state.op,
        requested_by_sub=state.requested_by_sub,
        expected_stores=0,
        expected_agents=0,
        processed_stores=0,
        processed_agents=0,
        control_totals={},
        artifacts=[],
        errors=[error_code],
        status=status,
    )


def _result(state: MonthlyRunState, outcome: MonthlyRunOutcome) -> dict[str, Any]:
    result: dict[str, Any] = {
        "op": state.op,
        "month_label": state.ports.ro_month_label(state.month),
        "status": outcome.status,
        "output": (
            "Operation completed with verified coverage."
            if outcome.status == "success"
            else f"Operation failed: {outcome.error_code or 'monthly_operation_failed'}"
        ),
        "exit_code": outcome.exit_code,
        "dry_run": state.dry_run if state.op == "reset" else None,
    }
    if outcome.manifest_record is not None:
        result["manifest"] = state.ports.public_manifest_payload(
            outcome.manifest_record
        )
    if state.operation_id is not None:
        result.update(
            operation_id=state.operation_id,
            operation_status=(
                "completed" if outcome.status == "success" else "failed"
            ),
        )
    return result


async def _reject_partial(state: MonthlyRunState) -> dict[str, Any] | None:
    if not (
        state.operation_id is not None
        and state.only
        and (state.op != "reset" or not state.dry_run)
    ):
        return None
    code = "partial_official_operation_forbidden"
    await _persist_manifest(
        state, manifest=_empty_failure_manifest(state, code), error_code=code
    )
    result = _result(
        state, MonthlyRunOutcome(status="failed", exit_code=-1, error_code=code)
    )
    await state.ports.finish_operation(
        state.pool,
        state.operation_id,
        result=result,
        error_message=code,
        execution_owner=state.execution_owner,
        execution_epoch=state.execution_epoch,
    )
    return result


def _operation_call(state: MonthlyRunState, google_adapter: Any) -> Coroutine[Any, Any, Any]:
    common = {
        "month_key": state.month,
        "requested_by_sub": state.requested_by_sub,
        "operation_id": state.operation_id,
        "only": state.only,
        "google_adapter": google_adapter,
    }
    if state.op == "finalize":
        return state.ports.finalize_execution(
            state.pool, state.ports.ro_month_label(state.month), **common
        )
    if state.op == "archive":
        return state.ports.archive_execution(
            state.pool, state.ports.ro_month_label(state.month), **common
        )
    return state.ports.reset_execution(
        state.pool,
        closing_month=state.ports.ro_month_label(state.month),
        next_month=state.ports.ro_month_label(state.ports.next_month(state.month)),
        closing_month_key=state.month,
        next_month_key=state.ports.next_month(state.month),
        requested_by_sub=state.requested_by_sub,
        operation_id=state.operation_id,
        approved_manifest_id=state.approved_manifest_id,
        only=state.only,
        dry_run=state.dry_run,
        google_adapter=google_adapter,
        execution_owner=state.execution_owner,
        execution_epoch=state.execution_epoch,
    )


async def _persist_manifest(
    state: MonthlyRunState,
    *,
    manifest: dict[str, Any],
    error_code: str | None = None,
) -> dict[str, Any] | None:
    if state.operation_id is None:
        return None
    return await state.ports.persist_manifest(
        state.pool,
        operation_id=state.operation_id,
        manifest=manifest,
        error_code=error_code,
        execution_owner=state.execution_owner,
        execution_epoch=state.execution_epoch,
    )


def _clear_cancellation() -> None:
    current = asyncio.current_task()
    if current is not None:
        while current.cancelling():
            current.uncancel()


async def _execute(state: MonthlyRunState, google_adapter: Any) -> MonthlyRunOutcome:
    ports = state.ports
    outcome = MonthlyRunOutcome()
    try:
        if state.operation_id is not None:
            alive = await ports.heartbeat_operation(
                state.pool,
                state.operation_id,
                execution_owner=state.execution_owner,
                execution_epoch=state.execution_epoch,
            )
            if not alive:
                raise ports.integrity_error_type(
                    "operation_lease_lost", "Monthly operation lease was lost"
                )
        operation = _operation_call(state, google_adapter)
        if state.operation_id is not None:
            outcome.execution = await ports.run_with_lease(
                state.pool,
                state.operation_id,
                execution_owner=state.execution_owner,
                execution_epoch=state.execution_epoch,
                operation=operation,
            )
        else:
            outcome.execution = await operation
        approved_reset = (
            state.op == "reset"
            and not state.dry_run
            and state.approved_manifest_id is not None
        )
        if state.operation_id is not None and not approved_reset:
            outcome.manifest_record = await _persist_manifest(
                state, manifest=outcome.execution.manifest
            )
    except ports.manifest_error_type as exc:
        error_code = str(getattr(exc, "code", "monthly_manifest_failed"))
        manifest = getattr(exc, "manifest", _empty_failure_manifest(state, error_code))
        outcome.status, outcome.exit_code, outcome.error_code = "failed", -1, error_code
        outcome.manifest_record = await _persist_manifest(
            state, manifest=manifest, error_code=error_code
        )
    except asyncio.CancelledError:
        _clear_cancellation()
        outcome.status = "failed"
        outcome.exit_code = -1
        outcome.error_code = "monthly_operation_cancelled"
        uncertain = state.op == "reset" and not state.dry_run
        outcome.manifest_record = await _persist_manifest(
            state,
            manifest=_empty_failure_manifest(
                state, outcome.error_code, status="uncertain" if uncertain else "failed"
            ),
            error_code=outcome.error_code,
        )
    except Exception as exc:  # noqa: BLE001
        outcome.status = "failed"
        outcome.exit_code = -1
        outcome.error_code = (
            str(getattr(exc, "code", "monthly_operation_integrity_failed"))
            if isinstance(exc, ports.integrity_error_type)
            else "monthly_operation_failed"
        )
        outcome.manifest_record = await _persist_manifest(
            state,
            manifest=_empty_failure_manifest(state, outcome.error_code),
            error_code=outcome.error_code,
        )
    return outcome


async def _rollback_commit(
    state: MonthlyRunState,
    outcome: MonthlyRunOutcome,
    result: dict[str, Any],
) -> bool:
    try:
        if outcome.execution is None or outcome.execution.rollback is None:
            raise RuntimeError("Reset rollback callback is unavailable")
        rollback_manifest = await outcome.execution.rollback()
    except BaseException:
        rollback_manifest = state.ports.base_manifest(
            month=state.month,
            operation="reset",
            requested_by_sub=state.requested_by_sub,
            expected_stores=0,
            expected_agents=0,
            processed_stores=0,
            processed_agents=0,
            control_totals={},
            artifacts=[],
            errors=["reset_commit_failed", "rollback_failed"],
            status="uncertain",
        )
    try:
        record = await _persist_manifest(
            state, manifest=rollback_manifest, error_code="reset_commit_failed"
        )
    except Exception:  # noqa: BLE001
        record = None
    result.update(
        status="failed",
        output=f"Operation failed: {rollback_manifest['status']}",
        exit_code=-1,
        operation_status="failed",
    )
    if record is not None:
        result["manifest"] = state.ports.public_manifest_payload(record)
    assert state.operation_id is not None
    return await state.ports.finish_operation(
        state.pool,
        state.operation_id,
        result=result,
        error_message="reset_commit_failed",
        execution_owner=state.execution_owner,
        execution_epoch=state.execution_epoch,
    )


async def _consume_reset(
    state: MonthlyRunState,
    outcome: MonthlyRunOutcome,
    result: dict[str, Any],
) -> bool:
    assert state.operation_id is not None
    assert state.approved_manifest_id is not None
    try:
        approved = await state.ports.fetch_manifest(
            state.pool, int(state.approved_manifest_id)
        )
        payload = approved.get("manifest") if approved else None
        approved_sha = approved.get("manifest_sha256") if approved else None
        if not isinstance(payload, dict) or not isinstance(approved_sha, str):
            raise RuntimeError("Approved manifest disappeared before consumption")
        if outcome.execution is None:
            raise RuntimeError("Reset execution disappeared before commit")
        consumed = dict(payload)
        consumed.update(status="consumed", consumed_at=state.ports.utc_now())
        consumed = state.ports.finalize_manifest(consumed)
        record = await state.ports.persist_reset_success(
            state.pool,
            state.operation_id,
            result=result,
            reset_manifest=outcome.execution.manifest,
            manifest_id=int(state.approved_manifest_id),
            expected_manifest_sha256=approved_sha,
            consumed_manifest=consumed,
            execution_owner=state.execution_owner,
            execution_epoch=state.execution_epoch,
        )
        result["manifest"] = state.ports.public_manifest_payload(record)
        return True
    except BaseException:
        return await _rollback_commit(state, outcome, result)


def _lease_lost_result(state: MonthlyRunState) -> dict[str, Any]:
    return {
        "op": state.op,
        "month_label": state.ports.ro_month_label(state.month),
        "status": "failed",
        "output": "Operation failed: operation_lease_lost",
        "exit_code": -1,
        "dry_run": state.dry_run if state.op == "reset" else None,
        "operation_id": state.operation_id,
        "operation_status": "failed",
    }


async def _finish(
    state: MonthlyRunState,
    outcome: MonthlyRunOutcome,
    result: dict[str, Any],
) -> dict[str, Any]:
    if state.operation_id is None:
        return result
    approved_reset = (
        outcome.status == "success"
        and state.op == "reset"
        and not state.dry_run
        and state.approved_manifest_id is not None
    )
    if approved_reset:
        finished = await _consume_reset(state, outcome, result)
    else:
        finished = await state.ports.finish_operation(
            state.pool,
            state.operation_id,
            result=result,
            error_message=(outcome.error_code if outcome.status == "failed" else None),
            execution_owner=state.execution_owner,
            execution_epoch=state.execution_epoch,
        )
    return result if finished else _lease_lost_result(state)


async def orchestrate_monthly_operation(
    ports: MonthlyRunPorts,
    *,
    op: str | None = None,
    month: str | None = None,
    only: str | None = None,
    dry_run: bool = True,
    operation_id: int | None = None,
    google_adapter: Any = None,
    execution_owner_hint: str | None = None,
) -> dict[str, Any]:
    if operation_id is None:
        _validate_request(ports, op, month)
    pool = await ports.get_pool()
    state, replay = await _claim_run(
        ports,
        pool,
        op=op,
        month=month,
        only=only,
        dry_run=dry_run,
        operation_id=operation_id,
        execution_owner_hint=execution_owner_hint,
    )
    if replay is not None:
        return replay
    assert state is not None
    _validate_request(ports, state.op, state.month)
    partial = await _reject_partial(state)
    if partial is not None:
        return partial
    outcome = await _execute(state, google_adapter)
    return await _finish(state, outcome, _result(state, outcome))
