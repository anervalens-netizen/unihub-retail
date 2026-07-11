# H-11 Grile monthly idempotency and state-transition plan

## Revalidated defect

`run_monthly_op()` currently calls `start_monthly_operation()`. When the atomic `queued -> running` update returns false, it prints that the operation was already started or finished, but then continues into `finalize_month()`, `archive_month()` or `reset_month()`. It subsequently calls `finish_monthly_operation()` unconditionally.

A duplicate ARQ delivery can therefore repeat local/Google side effects and overwrite a terminal or concurrently running operation row.

## Existing protections to preserve

- reservation serialization for one active operation per closing month;
- stale-operation detection;
- retry blocking for uncertain live-reset checkpoints;
- completed live-reset deduplication for the same scope;
- per-store live-reset checkpoints and heartbeat updates.

## Required implementation

1. Replace the boolean start result with a typed snapshot containing one of:
   - `started`;
   - `already_running`;
   - `already_completed`;
   - `already_failed`;
   - `not_found`.
2. Keep `queued -> running` as an atomic compare-and-set update.
3. If the worker does not acquire `started`, return without calling any operation implementation, heartbeat or finish mutation.
4. Preserve the existing job-result contract used by the frontend. Add explicit metadata such as `idempotent_replay` and `operation_status`; do not turn a harmless duplicate delivery into a second side effect.
5. Terminal rows (`completed`/`failed`) must never be overwritten by a late duplicate worker.
6. `finish_monthly_operation()` must update only a row currently in `running` state and report whether the transition was applied.
7. `fail_monthly_operation()` may transition only `queued` or `running` rows and must not overwrite terminal state.
8. A missing operation ID fails deterministically without executing an operation.
9. Direct/manual execution with `operation_id=None` remains supported and retains current behavior.
10. Do not modify Google Sheets or production data while validating this finding.

## Required tests

- two concurrent starts for the same queued operation: exactly one acquires `started`;
- duplicate delivery while row is `running`: zero calls to finalize/archive/reset and no row mutation;
- duplicate delivery after `completed`: zero side effects and stored result remains unchanged;
- duplicate delivery after `failed`: zero side effects and error/result remains unchanged;
- missing operation ID: zero side effects;
- late finish cannot overwrite `completed` or `failed`;
- enqueue failure can still move `queued -> failed`;
- direct execution without an operation ID still runs once;
- live-reset checkpoint tests continue to pass;
- full isolated PostgreSQL suite, mypy and frontend checks remain green.

## Rollback

Revert the H-11 implementation commit. No database migration is expected. If a schema change becomes necessary, stop and document an expand/rollback plan before implementation.

## Release verification

Before production deployment, inspect aggregate operation states only. After deployment, trigger a dry-run operation in a controlled month/scope and verify that a duplicated worker invocation is a no-op. Do not test duplicate live Google writes in production.
