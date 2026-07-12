# H-01 — Business decision: retain CNP in PostgreSQL

**Decision date:** 12 July 2026  
**Scope:** UniHub Retail salary domain

## Decision

CNP remains stored in the canonical PostgreSQL salary data model because it is required for internal identity matching and data integrity.

The privacy boundary is therefore:

- raw CNP may exist only in approved internal database/import/matching paths;
- raw CNP must not be returned by the public application API;
- raw CNP must not be placed in browser state, URLs, exports, ordinary logs, metrics, error payloads or CI artifacts;
- public salary navigation uses the opaque `person_id` introduced by H-01A.

## Prohibited changes without a new explicit business approval

No audit-remediation task may:

- drop a CNP column or index;
- null, blank, hash-overwrite or otherwise destroy stored CNP values;
- migrate the database to a model in which the original CNP is no longer retained;
- run a destructive backfill or cleanup against CNP data.

## Allowed later hardening

A later H-01B may improve protection while preserving the stored value, for example:

- isolate salary data behind a dedicated PostgreSQL role/schema;
- restrict raw-CNP reads to approved internal matching operations;
- add audited access paths and least-privilege grants;
- strengthen encrypted storage, backups and secret handling;
- document retention, recovery and incident procedures;
- add a durable internal `salary_people`/`person_id` model alongside, not instead of, the retained CNP.

Any migration that touches CNP storage requires a verified backup, read-only reconciliation plan, forward/rollback procedure and a separate explicit approval.
