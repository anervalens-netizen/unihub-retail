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
- production stores the applied checksum in `schema_migrations`;
- historical files are never edited; corrections are forward migrations;
- a session advisory lock serializes all runners;
- each migration commits independently;
- the web startup path executes only `SELECT` statements for migration state;
- unknown DB rows, missing checksums, file drift and pending files fail closed.

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
4. require a successful exit and current checksums;
5. deploy/restart the web process;
6. verify health and confirm the web log contains only read-only migration
   verification.

## Rollback

Application rollback does not delete migration rows or reverse committed DDL.
Use a reviewed forward correction whenever possible. A destructive database
rollback requires restoring the verified pre-release backup and coordinating
all consumers of the Retail database.
