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

## Fail-closed closeout contract

Migration `028_grile_monthly_fail_closed.sql` adds persistent operation
manifests and recoverable reset checkpoints. Every worker operation is bound to
the immutable OIDC `sub` stored in `requested_by_sub`; email is not used as an
authorization identity. A verified manifest records the month and operation,
expected and processed store/agent counts, control totals, zero errors,
artifact SHA-256 values, source backups and the requesting subject.

Finalization accepts only finite, non-negative required numbers. A missing
agent, a partially populated slot, duplicate agent, contradictory store
metadata, incomplete Google response, timeout or retry exhaustion fails the
operation. The staged workbook is structurally re-read before atomic promotion,
so a partial artifact never receives the official filename and an existing
official artifact is preserved as a revision.

Archive requires the latest finalization attempt for the month to be verified;
a newer failed or still-building attempt blocks reuse of an older verified
manifest. It also requires the exact active sheet registry. Every source
workbook must contain `Grila` and `Pontaj`; source files,
the aggregate ZIP and manager ZIPs are hashed before the staged archive
directory is promoted. Post-promotion verification is part of the same
filesystem transition: any failure removes the unverified directory from the
official path and restores the previous archive revision. Approval re-verifies
the manifest and every artifact, then persists `approved_by_sub`. The public
payload never returns either OIDC subject.

Live reset requires the approved archive manifest ID to remain the latest
archive attempt for the month; any newer archive attempt, regardless of state,
invalidates the older approval. It also requires an exact registry,
sheet-ID and source-backup match. Before the first clear, all editable ranges
are captured with formulas, written mode `0600`, hashed and checkpointed. Every
clear is read back. Any Google, checkpoint or output failure restores all
touched sheets and verifies the restored snapshot; a failed verification is
persisted as `uncertain` and blocks automatic retry.

The verified reset manifest, successful operation transition and consumption
of the approved archive manifest commit in one PostgreSQL transaction. If that
transaction fails, Google values are restored from the snapshots and the
operation ends `failed` with a `rolled_back` or `uncertain` manifest.

## Implemented state machine

`MonthlyOperationStartResult` contains `status`, `operation_id`, the current operation snapshot and, where persisted, a safe copy of its result. `status` is strictly one of:

- `started`;
- `already_running`;
- `already_completed`;
- `already_failed`;
- `not_found`.

Start uses a guarded `UPDATE ... WHERE status = 'queued' RETURNING *`; only a
reservation with a nonblank persisted OIDC subject and a matching building
manifest may become `running`. A queued legacy reservation without that
contract is atomically moved to `failed` before business or Google work. Only
the worker receiving `started` may execute business work; other compare-and-set
outcomes read the current terminal or active state without overwriting it.

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

In all four cases no finalize/archive/reset implementation, heartbeat, finish,
checkpoint, output-file, or Google adapter is called. The queued worker derives
operation, month, scope, subject and approval only from the persisted
reservation.

## Verification

The isolated PostgreSQL tests cover concurrent starts, duplicate delivery in
`running`/`completed`/`failed`, missing IDs, guarded late finishes, persistent
approval, atomic approval consumption and rollback of all DB transitions when
the consumption lease is lost. Unit tests cover invalid numeric values, missing
and duplicate agents, 429/503/timeouts, unexpected stores, partial workbooks,
archive/source coverage, checkpoint failure, Google rollback verification,
output promotion failure and DB commit failure.

Additional queue-publication tests verify:

- database job attachment occurs before ARQ publication;
- publication is refused when the row is no longer queued;
- Valkey exceptions and null enqueue results transition only a queued reservation to failed;
- an existing active reservation bypasses publication and returns its persisted job ID.

All H-11 operation implementations and Google-facing adapters are mocked in duplicate-delivery tests; no real Google operation was executed.

## Rollback

Stop the worker before rollback. Preserve `backend/outputs/grile`, including
`.staging`, `.revisions` and reset source snapshots. Revert application code
while retaining migration 028 and its additive tables/columns; dropping
manifest or checkpoint data is not part of application rollback. A reset with
an `uncertain` checkpoint requires manual Google reconciliation before any new
live attempt.

## Release verification

Before production deployment, back up PostgreSQL and the Grile output tree,
then inspect aggregate operation states only. After deployment, trigger a
dry-run in a controlled month and verify that a duplicated worker invocation is
a no-op. Verify finalization/archive with non-production fixtures. Do not test
duplicate or destructive live Google writes in production.
