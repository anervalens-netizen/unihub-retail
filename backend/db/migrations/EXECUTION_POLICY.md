# Migration execution classification

The active migration manifest classifies every immutable migration explicitly.
The classification is operational metadata and is separate from the F1
`execution_modes` compatibility field used for online execution.

## Manifest versions

- **Version 1** is the legacy compatibility format. A v1 manifest MAY omit
  `execution_classes`; when the key is absent the class is inferred from the
  existing `execution_modes` (`online` stays online, everything else remains
  transactional). When the key IS present, it must classify every migration
  exhaustively using only the values listed below and must agree with any
  explicit F1 `online` execution mode.
- **Version 2** is the active F4 contract. A v2 manifest MUST carry an
  exhaustive `execution_classes` dict. Removing or renaming the key on a
  v2 manifest fails closed: the runner refuses to start with
  `MigrationError("Migration manifest is invalid")`. An explicitly present
  `null` or non-dict value is also rejected. Removing `execution_classes`
  from the active manifest MUST NOT silently fall back to legacy v1 behavior
  because the v1 fallback does not authorize the `maintenance-window` class.

Unsupported manifest versions (anything other than 1 or 2) are rejected.

## Classes

- `transactional` — normal/default path. The migration SQL and
  `schema_migrations` ledger insert run in the same database transaction.
- `online` — explicit F1/F2 opt-in for a single statement that must execute
  outside a database transaction. Controlled `CREATE INDEX CONCURRENTLY`
  migrations use the dedicated validated recovery path.
- `maintenance-window` — planned-window work that still uses the transactional
  executor, but the runner refuses to start that migration unless the
  operator has set `UNIHUB_MIGRATION_MAINTENANCE_WINDOW` to the EXACT
  migration filename that is about to run. The comparison is strict
  string equality with the current migration filename: a stale
  authorization for migration `X` MUST NOT authorize migration `Y`, and
  the legacy boolean `=1` is no longer accepted. The expected operator
  contract is therefore `UNIHUB_MIGRATION_MAINTENANCE_WINDOW=070_*.sql`
  (matching the migration that is about to apply), and the env var must
  be cleared between separate maintenance-window migrations to avoid
  accidental authorization.

`maintenance-window` does not make a migration non-transactional. It adds an
operator authorization boundary around transactionally safe work whose lock,
duration, or operational impact requires a planned window.

## Compatibility

Version-1 manifests created before F4 may omit `execution_classes`. For those
legacy manifests the class is inferred from the existing execution mode:
explicit `online` stays online and everything else remains transactional.

Once `execution_classes` is present (in either v1 or v2), it must classify
every manifest migration, may use only the three values above, and must
agree with any explicit F1 `online` execution mode.

The active repository manifest is v2 and classifies every migration
exhaustively. F4 does not retroactively change how already-authored SQL
executes; future migrations must receive the class that matches their actual
operational contract when they are added to the active manifest.
