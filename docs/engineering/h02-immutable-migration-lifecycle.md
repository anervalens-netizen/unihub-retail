# H-02 — immutable PostgreSQL migration lifecycle

## Decision

The FastAPI and worker processes must never apply schema changes. Database
changes are executed by a dedicated one-shot runner before application restart.
Application startup performs a read-only consistency check and fails closed on
pending, unknown or checksum-mismatched migrations.

## Contract

- `schema_v2.sql` is frozen at the H-02 baseline and used only for a fresh DB;
- every later schema/data delta is a new `NNN_name.sql` file;
- `manifest.json` stores the immutable SHA-256 of the baseline and every file;
- manifest version 2 is the active authoring authority and requires an exhaustive
  `execution_classes` map covering every migration with exactly one of
  `transactional`, `online` or `maintenance-window`; version 1 remains accepted
  only for legacy compatibility and may omit `execution_classes`, in which case
  execution is inferred from the reviewed `execution_modes` map;
- an explicit `online` class must agree exactly with the same filename in
  `execution_modes`, and a `maintenance-window` migration remains transactional
  but requires exact filename-bound operator authorization before execution;
- production stores migration/recovery state in the single canonical
  `schema_migrations` ledger;
- historical files are never edited; corrections are forward migrations;
- a session advisory lock serializes all runners;
- ordinary migrations execute SQL and write their ledger row in the same
  database transaction;
- the web startup path executes only `SELECT` statements for migration state;
- unknown DB rows, missing checksums, file drift and pending files fail closed.

At F1, the checked-in manifest deliberately remained version 1 because there
was no online migration and `execution_modes` was introduced as additive legacy
metadata. F4 supersedes that authoring contract: the active checked-in manifest
is version 2 and newly authored active manifests must classify every migration
explicitly. Version 1 support exists only so historical artifacts remain
readable and rollback-compatible; it is not the format to copy for new work.

## Explicit online / non-transactional path

F1 adds an opt-in path for PostgreSQL commands that cannot legitimately run in
the ordinary transaction wrapper. In a legacy version-1 manifest, a migration
is inferred as transactional unless its exact filename is mapped to `online` in
`execution_modes`. In the active version-2 contract, that same filename must
also be classified explicitly as `online` in `execution_classes`; the two maps
must agree exactly. Unknown filenames and any other execution-mode value make
the manifest invalid.

An online migration is deliberately one top-level SQL statement. The runner
uses asyncpg's prepared/extended-query execution path outside an active database
transaction, so accidental multi-command files are rejected by PostgreSQL rather
than being silently executed as a batch. The runner checks both before and after
the statement that no transaction is active, so a transaction-control statement
cannot silently turn the online path back into transactional execution.

Because the online SQL statement and its final checksum cannot be committed
atomically, the canonical `schema_migrations` row is also the recovery fence:

1. inside a short transaction, insert the exact filename with checksum sentinel
   `online-recovery:<immutable-sha256>`;
2. leave the transaction and, when the dedicated migration authority is active,
   elevate the session to `unihub_schema_owner`;
3. execute the single online statement with no active transaction;
4. reset session role;
5. inside a new transaction, update that exact row from the exact sentinel to
   the immutable checksum and refresh `applied_at`; the update must affect
   exactly one row.

Any process loss, SQL error, role-reset failure or post-SQL ledger failure leaves
the sentinel in the canonical ledger. A later migration run and the read-only
current-state verifier refuse to continue automatically when they see it. The
sentinel is bound to both the immutable checksum and explicit `online` manifest
mode, so changing/removing the mode or changing the expected checksum cannot
launder the recovery state into a normal applied migration.

This is intentional: **F1 does not retry or infer whether a partially executed
online operation is safe to resume.** Controlled `CREATE INDEX CONCURRENTLY`,
retry, invalid-index cleanup and post-validation belong to F2.

### F2 controlled concurrent-index recovery

F2 adds no production/business migration and does not change the checked-in
manifest or frozen schema baseline. It is an explicit operator action only:
`backend/scripts/recover_online_migration.py <filename>` calls
`recover_online_migration(filename)`. A normal startup or migration run never
recovers or retries a sentinel.

The recovery entrypoint accepts only a manifest migration explicitly marked
`online` whose immutable SQL is one standalone, non-unique
`CREATE INDEX CONCURRENTLY <safe-unquoted-index> ON <safe-unquoted-table> ...`
statement (leading comments are allowed). `UNIQUE`, `IF NOT EXISTS`, ordinary
`CREATE INDEX`, quoted/ambiguous identifiers, multiple statements and
arbitrary online DDL fail closed. Before the initial attempt, the candidate
index name must be absent from the public catalog; no `IF NOT EXISTS` shortcut
is used.

Each controlled `CREATE` or cleanup `DROP INDEX CONCURRENTLY` uses a bounded
5-second `lock_timeout`, restoring the prior session setting in `finally`.
The explicit recovery performs at most one retry: an absent index is created,
while an existing index is dropped only when it is an index on the exact
expected table, then recreated. An unexpected object or table is never
removed. After the DDL, catalog validation requires the exact name and table
plus `indisvalid`, `indisready` and `indislive` all true. Only then is the
canonical sentinel changed to the immutable checksum. Any drop, create, role
reset, lock-timeout reset or validation failure leaves the sentinel and keeps
normal runs blocked. There is no generic online-DDL recovery framework.

### F4 explicit execution classification

F4 makes execution intent explicit for every migration in the active manifest.
Version 2 requires `execution_classes` to cover exactly the migration inventory;
missing, null, partial, extra or invalid classification metadata fails closed.
The allowed classes are `transactional`, `online` and `maintenance-window`.
`online` must agree exactly with `execution_modes`; `maintenance-window` still
uses the transactional executor but additionally requires
`UNIHUB_MIGRATION_MAINTENANCE_WINDOW` to equal the exact pending migration
filename. A stale authorization for one filename cannot authorize another, and
the legacy boolean value `1` is not accepted.

The currently tracked migrations are all classified `transactional`; F4 does
not retroactively change the execution semantics of historical SQL. Future
migration authors must choose the operational class deliberately in the v2
manifest rather than relying on omitted metadata.

## Existing database adoption

The first H-02 run adds the nullable checksum column under the migration lock,
validates every historical filename against the checked-in manifest and
backfills its reviewed checksum. It applies no historical SQL again. The
production reconciliation must confirm that all expected filenames are present
before this adoption.

Production also contained `005_retail_ai_analysis_views.sql`, whose original
body was absent from every reachable Git object before H-02. Because migration
006 removed those views and the frozen baseline contains the final state, H-02
restores 005 as an explicit fail-closed tombstone: fresh databases mark it as
incorporated, and an existing/baseline-built database that already records 006
may adopt the missing 005 checksum without executing its body. If 006 is not
recorded, the tombstone remains fail-closed and no database replays a guessed
historical body.

## Fresh database

The runner applies the frozen baseline once, records migrations incorporated
through `022_store_pnl_site_links.sql`, then replays the explicitly designated
data seed `014_target_calculator_store_exclusions.sql` and applies every later
delta in order. This preserves the CRFVUL/CRFARENA exclusions that are data, not
DDL represented by the baseline. The baseline is not evolved after H-02.

The one-shot runner prefers the owner-only `MIGRATION_DATABASE_URL`; only an
explicit function argument may override it. Web and worker continue to use the
runtime `DATABASE_URL` and never gain migration privileges.

## Deployment

1. verify a current restorable backup;
2. install/update `unihub-retail-migrate.service`;
3. run the one-shot migration service while the old web version remains live;
4. require a successful exit and current checksums, with no unresolved online
   recovery sentinel;
5. deploy/restart the web process;
6. verify health and confirm the web log contains only read-only migration
   verification.

The release/deploy identity path validates both legacy version 1 and active
version 2 with the same fail-closed structural rules used by the migration
contract. Version 2 requires exhaustive `execution_classes`; version 1 may omit
that map only for legacy compatibility. Release tooling rejects unsupported or
non-integer versions and preserves unknown additive metadata rather than
silently dropping it.

## Rollback

Application rollback does not delete migration rows or reverse committed DDL.
Before stopping the runtime, the privileged entrypoint strictly validates both
manifests and compares their canonical migration semantics. Canonicalization
normalizes only the schema-representation fields `version`, `execution_modes`
and `execution_classes`: a legacy v1 omission is expanded to the same inferred
transactional/online classes that the runner uses. This allows the metadata-only
v1 -> v2 F4 rollout to remain rollback-compatible when the migration inventory,
checksums, baseline and execution semantics are actually identical.

Checksum, migration-inventory, baseline, execution-class or unknown-metadata
differences remain incompatible and fail closed. A legacy inferred
`transactional` migration is therefore not rollback-equivalent to a v2
`maintenance-window` migration, and online-mode mismatches are also rejected.
Use a reviewed forward correction whenever possible. A destructive database
rollback requires restoring the verified pre-release backup and coordinating all
consumers of the Retail database plus any writes made after that backup.

When the new manifest may already be applied and rollback is incompatible, the
deploy audit state is `recovery_required`. The same verified artifact may be
recovered only with a fresh exact one-time approval; the migration runner is
idempotent and both failed and successful approval links remain in the handle.
