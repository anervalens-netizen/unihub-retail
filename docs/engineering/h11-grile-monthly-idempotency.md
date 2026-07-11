# H-11 Grile monthly idempotency and state transitions

## Revalidated defect

`run_monthly_op()` previously called `start_monthly_operation()`. When the atomic `queued -> running` update returned false, it printed that the operation was already started or finished, but then continued into `finalize_month()`, `archive_month()` or `reset_month()`. It subsequently called `finish_monthly_operation()` unconditionally.

A duplicate ARQ delivery could therefore repeat local/Google side effects and overwrite a terminal or concurrently running operation row.

A second race existed in job publication: the ARQ job was published before its deterministic `job_id` was attached to the database reservation. A fast worker could acquire `queued -> running` before the attachment, leaving an active operation without a recoverable `job_id` for duplicate requests and status polling. Queue exceptions could also leave a reservation queued until stale cleanup.

## Existing protections preserved

- reservation serialization for one active operation per closing month;
- stale-operation detection;
- retry blocking for uncertain live-reset checkpoints;
- completed live-reset deduplication for the same scope;
- per-store live-reset checkpoints and heartbeat updates.

## Implemented state machine

`MonthlyOperationStartResult` contains `status`, `operation_id`, the current operation snapshot and, where persisted, a safe copy of its result. `status` is strictly one of:

- `started`;
- `already_running`;
- `already_completed`;
- `already_failed`;
- `not_found`.

Start uses `UPDATE ... WHERE id = $1 AND status = 'queued' RETURNING *`; only the worker receiving `started` may execute business work. A failed compare-and-set reads the current row without changing it.

Allowed transitions are `queued -> running`, `running -> completed|failed`, and `queued -> failed` when queue publication fails. `finish_monthly_operation()` and `fail_monthly_operation()` return whether their guarded transition applied. Terminal rows cannot be overwritten by late workers or enqueue error handling.

## Queue publication contract

The deterministic job identifier `grile-monthly:{operation_id}` is persisted while the operation is still `queued`, before publishing the ARQ job.

Publication proceeds only if that guarded attachment succeeds. If Valkey raises or returns no job:

- the operation is moved `queued -> failed` through compare-and-set;
- an operation already acquired by a worker is not overwritten;
- the original queue error is propagated;
- no reservation remains silently queued for two hours.

This ordering removes the worker-before-attachment race and keeps duplicate API responses capable of returning the persisted job identifier.

## Duplicate worker contract

- `already_running`: returns a no-op result with `idempotent_replay: true` and `operation_status: running`.
- `already_completed`: returns a safe copy of the stored result with replay metadata; it does not rewrite the row.
- `already_failed`: returns a failed replay result without rewriting error or result.
- `not_found`: returns a deterministic failed no-op result with zero side effects.

In all four cases no finalize/archive/reset implementation, heartbeat, finish, checkpoint, output-file, or Google adapter is called. Direct execution with `operation_id=None` still executes once.

## Verification

The isolated PostgreSQL tests cover concurrent starts, duplicate delivery in `running`/`completed`/`failed`, missing IDs, guarded late finishes, allowed and refused fail transitions, direct execution and all three operations. Existing stale/uncertain/reset-checkpoint tests remain in the same suite.

Additional queue-publication tests verify:

- database job attachment occurs before ARQ publication;
- publication is refused when the row is no longer queued;
- Valkey exceptions and null enqueue results transition only a queued reservation to failed;
- an existing active reservation bypasses publication and returns its persisted job ID.

All H-11 operation implementations and Google-facing adapters are mocked in duplicate-delivery tests; no real Google operation was executed.

## Rollback

Revert the H-11 implementation and queue-publication hardening commits. No database migration was added. The previous behavior is restored by code revert only; no production data rollback is required.

## Release verification

Before production deployment, inspect aggregate operation states only. After deployment, trigger a dry-run operation in a controlled month/scope and verify that a duplicated worker invocation is a no-op. Do not test duplicate live Google writes in production.
