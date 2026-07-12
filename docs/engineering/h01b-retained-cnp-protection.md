# H-01B — retained CNP protection

Last updated: 2026-07-12

## Decision and boundary

The approved business decision remains unchanged: the original CNP is retained
for controlled HR import and identity matching. H-01B does not delete, blank,
overwrite or hash-replace that value.

The runtime boundary is now based on a durable opaque identity:

- `salary_private.people` owns the retained CNP-to-`person_id` mapping;
- `salary_records.person_id` and `agent_salary_links.person_id` persist the
  public-safe identity used by application queries;
- ordinary salary repositories read `person_id` and never read `cnp`,
  `salary_cnp` or the private schema;
- the offline salary importer writes the private mapping and public-safe rows in
  the same transaction;
- duplicate-import errors expose counts only, never names or identifiers.

The `sp1_` identifiers are backfilled with the existing HMAC key, so URLs and
saved client state remain stable across the migration.

## Expand, migrate, switch, contract

1. Apply migration `023_salary_private_identity_boundary.sql`. It only adds the
   private schema and nullable `person_id` columns.
2. Run `backfill_salary_private_identities.py` with the migration database URL
   and the existing `SALARY_PERSON_ID_HMAC_KEY`.
3. Reconcile metadata-only counts: missing record IDs, missing confirmed-link
   IDs and collisions must all be zero.
4. Deploy the runtime repository switch only after that reconciliation.
5. Add non-null/foreign-key constraints and activate a least-privilege runtime
   database role in the contract phase.

The migration runner and backfill use the owner connection. The final web and
worker role must have no `USAGE` on `salary_private`, no access to CNP columns,
and no DDL ownership. Owner credentials remain limited to the one-shot migration
unit and approved offline import procedures.

## Verification

Automated coverage proves that:

- a fresh isolated database applies migration 023;
- the backfill is transactional and idempotent;
- multiple historical names for the same retained identifier resolve to one
  person;
- confirmed retail links receive the same durable person ID;
- application repository source cannot query private identity columns;
- API, OpenAPI and browser contracts remain CNP-free;
- salary totals, averages, history and import replacement semantics are
  unchanged.

Production acceptance additionally requires a verified backup, metadata-only
preflight/reconciliation, successful one-shot migration, clean backfill,
least-privilege role verification, service health and salary-path smoke tests.

## Rollback

Before the runtime switch, rollback is code-only: nullable added columns and the
private schema can remain unused. After the switch, restore the previous runtime
build while keeping the HMAC key and retained data unchanged. Do not drop the
private schema or rewrite CNP values during an incident. Database-role rollback
temporarily restores the owner URL only long enough to recover service, followed
by a new least-privilege rollout.
