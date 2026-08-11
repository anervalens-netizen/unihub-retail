# Retail 9.5 final handoff

Status: deployed and verified in production on
`2cb2785c2340b901e07af7fcf40241e5bfd3555e`.

## Delivery identity

- reviewed remediation PRs: #134–#142;
- final PR CI: [31482819627](https://github.com/anervalens-netizen/unihub-retail/actions/runs/31482819627);
- exact-main CI: [31484028843](https://github.com/anervalens-netizen/unihub-retail/actions/runs/31484028843);
- release archive SHA-256: `aec301e2c82084de526f8e334d8d38c7ef3633544b0f22a84e356e0d54db4dcd`;
- formal deploy: [31485385533](https://github.com/anervalens-netizen/unihub-retail/actions/runs/31485385533);
- rollback handle: `/opt/Mobiup/ops/backups/retail-deploy/20260811T111002Z-397731e32c13-to-2cb2785c2340-f59b54973630e293`.

The deployed artifact passed exact-SHA identity, checksums, aggregate SBOM,
Sigstore issuer/repository/workflow/ref verification, migration compatibility,
service restart and post-deploy runtime checks. Do not reconstruct this release
from a checkout.

`main` may be ahead of the deployed artifact only by direct documentation-only
handoff commits permitted by ADR-006. Dell, the primary checkout and GitHub
must still have the same clean `main`, and `git diff --name-only
2cb2785c2340b901e07af7fcf40241e5bfd3555e..main` must contain no runtime file.

## Runtime topology

- Web: `unihub-backend.service`, metrics `9898`.
- Operations: `unihub-worker.service`, queue `arq:retail:operations`, metrics `9901`.
- Imports: `unihub-import-worker.service`, queue `arq:retail:imports`, metrics `9902`.
- Grile: `unihub-grile-worker.service`, queue `arq:retail:grile`, metrics `9903`.
- Exports: `unihub-export-worker.service`, queue `arq:retail:exports`, metrics `9904`.
- Legacy default queue: drained and retired; `unihub-legacy-worker.service` is a disabled rollback tombstone.
- PostgreSQL is authoritative; Valkey transports bounded job/session state only.

Owner access is unchanged. No Authentik group, SSH/sudoers boundary, service
identity or credential was changed by the audit remediation.

## Verified production state

- deployed Git SHA equals the delivery identity;
- all five runtime services are active and enabled;
- local `/livez` and `/readyz`, public `/health` and `/readyz` return 200;
- public diagnostics return 404;
- all five Prometheus targets are UP;
- all workers report up, backlog 0 and oldest queued age 0;
- no Retail worker/SLO alert fires after the Grile role selector correction;
- no warning-or-higher service logs occurred after deploy;
- content-length and chunked regular bodies above 1 MiB return 413;
- exact-main restore evidence reports passed, 11 business objects and restored app ready.

The GlitchTip warning visible immediately after deploy represents one event at
`2026-08-11T11:07:26.599Z`, before deployment began; the post-deploy count is
zero. Historical unresolved issues remain informational when recent events are
zero.

## Validation and rollback contract

CI remains authoritative for typecheck, lint, tests, global/critical/changed-
line coverage, changed-function complexity, mutation probes, security checks,
environment/architecture contracts, browser/PWA lifecycle, real integration,
restore, official ecosystem SBOMs and signed release packaging.

Rollback is allowed only when migration manifests are compatible. An
incompatible database boundary fails closed as `recovery_required`; recover by
reviewed roll-forward. The migration unit remains one-shot and is never
enabled.

The complete UR-01–UR-20 evidence matrix is in
`docs/operations/AUDIT_REMEDIATION_2026-08-11.md`.
