# Migration execution classification

The active migration manifest classifies every immutable migration explicitly.
The classification is operational metadata and is separate from the F1
`execution_modes` compatibility field used for online execution.

## Classes

- `transactional` — normal/default path. The migration SQL and
  `schema_migrations` ledger insert run in the same database transaction.
- `online` — explicit F1/F2 opt-in for a single statement that must execute
  outside a database transaction. Controlled `CREATE INDEX CONCURRENTLY`
  migrations use the dedicated validated recovery path.
- `maintenance-window` — planned-window work that still uses the transactional
  executor, but the runner refuses to start that migration unless
  `UNIHUB_MIGRATION_MAINTENANCE_WINDOW=1` is present exactly.

`maintenance-window` does not make a migration non-transactional. It adds an
operator authorization boundary around transactionally safe work whose lock,
duration, or operational impact requires a planned window.

## Compatibility

Version-1 manifests created before F4 may omit `execution_classes`. For those
legacy manifests the class is inferred from the existing execution mode:
explicit `online` stays online and everything else remains transactional.

Once `execution_classes` is present, it must classify every manifest migration,
may use only the three values above, and must agree with any explicit F1
`online` execution mode.

The current immutable migration history is classified `transactional` because
F4 does not retroactively change how already-authored SQL executes. Future
migrations must receive the class that matches their actual operational
contract when they are added to the active manifest.
