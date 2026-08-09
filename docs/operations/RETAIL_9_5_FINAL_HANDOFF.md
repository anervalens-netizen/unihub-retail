# Retail 9.5 final handoff

Status: PR #127 candidate only. Do not merge or deploy until every required PR
check is green on the exact head SHA and all review threads are resolved.

## Source and delivery boundary

- Branch: `agent/retail-9-5-complete-hardening-20260808`.
- Every Retail 9.5 source, test and operational change is a normal Git file.
- No bootstrap workflow, external payload, Filebin object or recovery materializer
  is part of the delivery path.
- `.github/workflows/ci.yml` is based on `main`; its additions are limited to
  Retail 9.5 security, architecture, browser, integration and release evidence gates.
- Runtime delivery remains ADR-006: exact-SHA CI artifact, verified digest,
  one-time owner approval, formal deploy, probes and compatible rollback.

## Runtime topology

- Web: `unihub-backend.service`, metrics `9898`.
- Operations: `unihub-worker.service`, queue `arq:retail:operations`, metrics `9901`.
- Imports: `unihub-import-worker.service`, queue `arq:retail:imports`, metrics `9902`.
- Grile: `unihub-grile-worker.service`, queue `arq:retail:grile`, metrics `9903`.
- Exports: `unihub-export-worker.service`, queue `arq:retail:exports`, metrics `9904`.
- PostgreSQL is authoritative; Valkey transports bounded job/session state only.

Owner access is unchanged. No allowlist, Authentik administrator group, SSH,
sudoers, service identity or credential boundary is narrowed by Retail 9.5.

## Mandatory merge gates

Run sequentially where build output is shared:

```bash
npm run typecheck
npm run complexity:ts
npm run lint
npm test
npm audit --audit-level=high
npm run build
PYTHONPATH=backend backend/venv/bin/python scripts/generate_retail_contract.py --check
(cd backend && venv/bin/mypy . --ignore-missing-imports --explicit-package-bases)
backend/scripts/run_tests_isolated.sh
backend/venv/bin/python scripts/check_backend_architecture.py
backend/venv/bin/python scripts/check_bandit_waivers.py
scripts/run_shellcheck.sh
npm run test:e2e
npm run test:e2e:browsers
npm run test:e2e:pwa-real
scripts/run_real_e2e.sh
ops/test-deploy-retail-artifact.sh
ops/verify-forensic-remediation-runtime.sh
```

CI additionally proves migration integrity, secret scanning, Bandit, dependency
policy, deterministic SBOM/provenance, real OIDC BFF session isolation,
PostgreSQL/Valkey integration, mixed load, backup/restore, worker restart,
Workbox N -> N+1 -> N, multi-browser smoke and exact artifact identity.

## Deploy and rollback

After merge, dispatch `ci.yml` on the new `main`. Deploy only the uploaded
`retail-release-<SHA>` bundle whose `SOURCE_SHA`, `SHA256SUMS`, CycloneDX SBOM,
SLSA provenance and release manifest agree. The deploy gate installs all six
systemd units, verifies all five Prometheus targets, `/livez`, `/readyz`,
`/health`, changed authenticated paths and the deployed Git SHA.

Rollback is allowed only when migration manifests are compatible. An
incompatible database boundary fails closed as `recovery_required`; it is not
bypassed. Preserve the last good generation and use verified roll-forward.
