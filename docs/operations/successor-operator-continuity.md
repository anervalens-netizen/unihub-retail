# UniHub Retail — successor-operator continuity runbook

## Purpose and authority

This is the canonical non-secret entrypoint for a competent successor operating UniHub Retail during an owner absence. It is a navigation and decision runbook: it does not replace the authoritative architecture, security, deployment, data or SLO documents linked below, and it never grants production mutation authority by itself.

Always distinguish three different kinds of truth:

1. **Repository/document lifecycle:** `docs/catalog.json` is the machine-readable authority for whether a tracked document is active, historical or superseded.
2. **Runtime health:** current health is observed from `/readyz` and the Prometheus signals defined in `docs/operations/retail-slo-readiness.md`; Git history and Markdown cannot declare a service healthy.
3. **Release identity:** GitHub `main`, the signed CI `RELEASE_MANIFEST.json`, and the production D2 promotion record identify what was certified and what is deployed. Never infer the current release from a filename, old issue comment or “latest-looking” backup directory.

Primary references:

- architecture and business invariants: `APP_ARCHITECTURE.md`;
- repository operating rules: `AGENTS.md`;
- documentation authority: `docs/README.md` and `docs/catalog.json`;
- exact-SHA runtime delivery: `docs/adr/006-verified-runtime-delivery.md`;
- production deploy/rollback boundary: `ops/README.md` and `ops/deploy-retail-artifact.sh`;
- readiness/SLO: `docs/operations/retail-slo-readiness.md`;
- OIDC/JWKS: `docs/engineering/h04-h05-oidc-jwks-hardening.md`;
- browser session/BFF: `docs/engineering/h06-bff-server-session.md`;
- privileged authorization: `docs/engineering/h08-privileged-access-fail-closed.md`;
- active audit-follow-up program: GitHub Issue #226 and its first open, unblocked K1–K10 child issue.

## 1. First five minutes: establish identity before acting

Do not mutate production until repository identity, production identity and health have been separated and understood.

### 1.1 Current GitHub `main`

From a GitHub-authenticated administrative workstation:

```bash
gh api repos/anervalens-netizen/unihub-retail/branches/main --jq '.commit.sha'
```

Record the 40-character SHA. GitHub current state supersedes SHA snapshots in handoffs or issue comments.

### 1.2 Production checkout identity

On the production host (`server` in the current operator SSH configuration), read only:

```bash
ssh -o BatchMode=yes server '
  cd /opt/Mobiup/unihub-retail &&
  printf "branch=" && git branch --show-current &&
  printf "head=" && git rev-parse HEAD &&
  printf "dirty_count=" && git status --porcelain=v1 --untracked-files=all | wc -l
'
```

Expected normal shape is branch `main` and a clean worktree. Do not fix divergence by `pull`, `reset`, `checkout` or direct edits. First collect evidence and determine whether a formal release/deploy/recovery path is required.

### 1.3 Production release identity and D2 boundary

For routine read-only orientation, bind the exact production HEAD from 1.2 to its exact D3 promotion tag. D3 is GitHub-hosted promotion history; it does **not** replace the signed CI manifest or D2 promotion state.

```bash
PROD_HEAD="<40-char production HEAD from 1.2>"
D3_TAG="production/retail-release-$PROD_HEAD"
D3_OBJECT_SHA="$(
  gh api \
    "repos/anervalens-netizen/unihub-retail/git/matching-refs/tags/$D3_TAG" \
    --jq 'if length == 1 then .[0].object.sha else error("expected one exact D3 tag") end'
)"

gh api "repos/anervalens-netizen/unihub-retail/git/tags/$D3_OBJECT_SHA" |
  jq -e --arg head "$PROD_HEAD" --arg tag "$D3_TAG" '
    .tag == $tag and
    .object.type == "commit" and
    .object.sha == $head and
    ((.message | fromjson) as $p |
      $p.schemaVersion == 1 and
      $p.kind == "unihub-retail-production-promotion" and
      $p.sourceSha == $head and
      $p.releaseId == ("retail-release-" + $head) and
      ($p.artifactSha256 | test("^[0-9a-f]{64}$")) and
      ($p.sbomSha256 | test("^[0-9a-f]{64}$")) and
      (($p.ciRunId | tostring) | test("^[0-9]+$")) and
      (($p.deployRunId | tostring) | test("^[0-9]+$")) and
      (($p.migrationHead | type) == "string") and
      (($p.migrationHead | length) > 0)
    )
  '
```

A success establishes that the exact live checkout SHA has a structurally valid D3 promotion-history record pointing to the same commit. The D3 message also exposes non-secret evidence such as release ID, CI/deploy run IDs, artifact/SBOM digests and migration head. Follow those exact run/artifact identities when deeper certification evidence is required; never rebuild or substitute an artifact.

D2 promotion records remain under:

```text
/opt/Mobiup/ops/backups/retail-deploy/*/release.env
```

D2 remains promotion-state authority. `scripts/render_production_release_notes.py` validates the complete D2 schema/relationships for an exact file supplied through a safe mechanism; it does not discover or select a `current`/`latest` handle.

Do **not** construct an ad-hoc privileged D2 reader from separate `stat`/`cat`, `find`, temporary copies or a generic privileged interpreter. The current root-owned release entrypoint exposes deploy, artifact validation and rollback operations, but no standalone least-privilege read-only D2 inspection mode that atomically opens one exact handle with no-follow semantics and validates bytes from that same opened object. A split path-check/read sequence is insufficient because another privileged release operation can replace `release.env` between the two operations, and leaf-only checks do not validate the handle directory chain.

Therefore:

- use production HEAD plus its exact D3 tag for routine non-mutating release orientation;
- do not treat D3 as a substitute for D2 when a deploy/rollback decision specifically depends on current promotion state;
- if independently validated D2 state is required, use an already approved root-owned atomic read/validation mechanism if one exists at execution time; otherwise report `D2 promotion state not independently verified` and stop the operation that depends on it;
- never choose a D2 handle by newest filename, glob ordering or an old issue comment;
- never broaden sudo, weaken permissions, execute repository checkout code as root or persist protected D2 bytes merely to inspect release state.

### 1.4 Health

The safe baseline probes are:

```bash
ssh -o BatchMode=yes server 'curl -fsS --max-time 5 http://127.0.0.1:9898/livez'
ssh -o BatchMode=yes server 'curl -fsS --max-time 5 http://127.0.0.1:9898/readyz'
curl -fsS --max-time 10 https://retail.unihub.ro/readyz
```

Interpret them using `docs/operations/retail-slo-readiness.md`:

- `/livez`: process/event-loop liveness only;
- `/readyz`: PostgreSQL + Valkey-backed session state + usable JWKS readiness;
- `/health`: compatibility alias for `/readyz`.

A public success is not proof that every worker is healthy. A local success plus public failure points first toward proxy/tunnel/networking rather than application readiness.

## 2. System map and ownership boundaries

The current production topology is centered on the `server` host, with repository-owned runtime definitions and shared infrastructure around it. Revalidate actual state before a mutation; the following is an operating map, not a current-health declaration.

### Retail application

Repository-owned systemd roles:

- `unihub-backend.service` — web/API identity `unihub-web`;
- `unihub-worker.service` — operations worker identity `unihub-operations`;
- `unihub-import-worker.service` — import identity `unihub-import`;
- `unihub-grile-worker.service` — Grile identity `unihub-grile`;
- `unihub-export-worker.service` — export identity `unihub-export`;
- `unihub-salary-export-worker.service` — salary-export identity `unihub-salary-export`;
- `unihub-retail-migrate.service` — one-shot migration identity `unihub-migrate`;
- `unihub-legacy-worker.service` — legacy tombstone/compatibility unit, not a normal active worker.

Versioned unit sources are `ops/systemd/` **plus repository-root `unihub-worker.service`** for the operations worker; `ops/systemd/README.md` documents this source-of-truth split. Never reconstruct a unit from memory when the repository source exists.

### Data and session dependencies

- PostgreSQL is the authoritative application database boundary for Retail and related services.
- Valkey provides the server-side browser-session/cache/queue-adjacent runtime required by authenticated readiness.
- ARQ queue availability is not itself part of web readiness; worker health/backlog must be checked separately.

Use process/container metadata for a first read-only check without exposing credentials:

```bash
ssh -o BatchMode=yes server '
  systemctl list-units --type=service --all --no-pager | grep -Ei "postgres|valkey|redis" || true
  sudo docker ps --format "{{.Names}}\t{{.Status}}" 2>/dev/null | grep -Ei "postgres|valkey|redis" || true
'
```

### Identity provider

Authentik is the OIDC identity boundary. Retail depends on a usable JWKS state, but routine health checks do not require Authentik administrative credentials. Privileged business capabilities are based on explicitly configured OIDC groups; personal email addresses are not authorization fallbacks.

Administrative changes require the **Identity / Authentik Administrator** role and must follow the security contracts linked above.

### Proxy and tunnel

The public Retail path uses Caddy as reverse proxy and Cloudflare Tunnel for external reachability. Routine Retail deploy and health observation do not require DNS, tunnel or Caddy mutation.

Administrative ownership roles:

- **DNS/Tunnel Administrator** — Cloudflare/DNS/tunnel configuration;
- **Reverse Proxy Administrator** — Caddy configuration/topology.

Read-only discovery:

```bash
ssh -o BatchMode=yes server '
  systemctl show cloudflared.service --property=LoadState,ActiveState,SubState,FragmentPath --no-pager 2>/dev/null || true
  sudo docker ps --format "{{.Names}}\t{{.Status}}" 2>/dev/null | grep -Ei "caddy" || true
'
```

Do not print tunnel tokens or unrelated Caddy routes.

### Observability

Shared observability is hosted on the production infrastructure and includes Prometheus/Alertmanager, Grafana, GlitchTip, blackbox probing and node-exporter; adjacent Loki/Alloy may also be present. The canonical Retail rules and readiness expectations remain versioned in the repository and in `docs/operations/retail-slo-readiness.md`.

Administrative changes require the **Monitoring Administrator** role. Routine health/release verification should use credential-free probes and machine signals first.

Important machine signals include:

```text
probe_success{job="blackbox_retail_readiness"}
jwks_readiness_state
```

A healthy normal state has successful blackbox readiness and a usable JWKS state (`fresh`, or bounded `stale` only during an understood IdP incident).

## 3. Accounts and roles a successor may need

This runbook stores roles, never credentials.

| Role | Purpose | Normal read-only need | Mutation boundary |
| --- | --- | --- | --- |
| GitHub Repository Administrator | Issues, PRs, Actions, rules/status evidence | Yes | Repository writes only under current workflow/PR rules |
| Production Host Operator | Read service/filesystem/runtime evidence | Yes | Restart/deploy/root operations require explicit task authorization |
| Identity / Authentik Administrator | OIDC provider, groups, mappings, client configuration | Usually no | Required for identity configuration changes |
| DNS/Tunnel Administrator | Cloudflare DNS/tunnel | Usually no | Required for DNS/tunnel changes |
| Reverse Proxy Administrator | Caddy routing/topology | Usually no | Required for proxy changes |
| Monitoring Administrator | Prometheus/Alertmanager/Grafana/GlitchTip configuration | Usually no | Required for monitoring configuration changes |
| Backup / Disaster Recovery Administrator | Backup retention and restore/recovery | Verification only | Real restore is separately authorized and currently owned by K5 |

If an account or credential is unavailable, do not bypass the boundary. Escalate to the corresponding role owner.

## 4. Secrets: where they live and how to treat them

Production uses root-protected, service-specific environment files. The versioned provisioning contract expects files such as:

```text
/opt/Mobiup/unihub-retail/.env
/opt/Mobiup/unihub-retail/.env.worker
/opt/Mobiup/unihub-retail/.env.import-worker
/opt/Mobiup/unihub-retail/.env.salary-export-worker
/opt/Mobiup/unihub-retail/.env.migrations
```

They are expected to be owned by `root:<service-group>` with mode `0640`. Do not duplicate that path/ownership contract with a per-file metadata loop. First verify that the fixed Retail live-root path canonicalizes to itself, which rejects symlink traversal in its path chain, then invoke the existing root-owned service-identity verifier that owns the environment-leaf contract:

```bash
ssh -o BatchMode=yes server '
  live_root=/opt/Mobiup/unihub-retail
  resolved="$(sudo --non-interactive /usr/bin/realpath -e -- "$live_root")" || exit 1
  if [[ "$resolved" != "$live_root" ]]; then
    printf "unsafe Retail live-root resolution: %s\n" "$resolved" >&2
    exit 1
  fi
  sudo --non-interactive /opt/Mobiup/ops/scripts/provision-retail-service-identities.sh verify
'
```

The versioned source `ops/provision-retail-service-identities.sh` requires root, rejects an unavailable or symlinked Retail live root, rejects each required environment leaf that is missing, non-regular or a symlink, and verifies exact `root:<service-group>:640` ownership/mode together with the expected service users/groups. The installed production copy is part of the root-owned operations boundary described in `ops/README.md`.

This check reads no environment-file values. If canonical live-root resolution, sudo authorization, the installed verifier or its provenance cannot be established, report that exact gap and stop; do not downgrade to an unprivileged existence test, copy protected files elsewhere, weaken permissions or run `apply` merely to investigate.

Never run `apply` merely to investigate a discrepancy.

Logical secret/configuration categories are documented with empty/non-secret placeholders in `.env.example`, including database/migration DSNs, OIDC client secret, session encryption key, Valkey URLs, rate-limit HMAC material, salary identity HMAC material and monitoring DSNs.

There is no repository-supported instruction to copy secret values into GitHub, chat, handoffs or local notes. An authorized administrator who must rotate a value should use the existing root-controlled production process for the relevant service, preserve ownership/mode, validate configuration through the owning security/runtime contract, and perform any restart/deploy only when it is within the existing task authorization and all technical gates are satisfied. If the authorized task does not cover that mutation, obtain explicit authorization first. If the authorized retrieval/rotation path for a particular credential is unclear, stop rather than invent a new secret-management path.

## 5. Normal deploy and rollback

`docs/adr/006-verified-runtime-delivery.md` is the governing decision. Runtime/data-affecting changes follow:

```text
branch/PR
→ local/focused validation as appropriate
→ exact-SHA CI
→ review
→ merge commit into main
→ exact-main CI release artifact
→ artifact/digest/migration-manifest verification
→ verified backup gate
→ formal deploy workflow
→ local/public health and observability verification
```

Operational details and the privileged boundary are in `ops/README.md` and `ops/deploy-retail-artifact.sh`.

Key fail-closed rules:

- never push runtime changes directly to production `main`;
- never deploy a local rebuild or unverified checkout;
- never substitute a different artifact for the exact CI artifact;
- do not run the migration service unless a reviewed migration is actually pending;
- rollback is allowed only when the deploy entrypoint proves the target migration manifest is compatible;
- if an incompatible migration boundary has been crossed, use reviewed roll-forward or a separately authorized coordinated recovery; do not force code rollback around schema safety;
- a failed one-time approval is not reusable; follow the formal fresh-approval/recovery contract.

Do not copy commands from historical release notes when the current `ops/` source defines the boundary.

## 6. Backup and restore ownership

### Backup verification

The deploy gate expects the production backup command:

```text
/opt/Mobiup/ops/scripts/backup.sh
```

and completion manifest:

```text
/opt/Mobiup/ops/backups/manifests/last-run.env
```

A deploy considers the backup gate valid only when the manifest has:

```text
status=success
checksum_ok=1
completed_at >= the current deploy backup-start time
```

Safe read-only inspection of the gate fields:

```bash
ssh -o BatchMode=yes server "sudo awk -F= '\
  \$1==\"status\" || \
  \$1==\"completed_at\" || \
  \$1==\"checksum_ok\" {print}' \
  /opt/Mobiup/ops/backups/manifests/last-run.env"
```

The current externally installed backup implementation has been verified to cover the PostgreSQL service portfolio plus the visits SQLite data and to maintain local copies plus off-host NAS replication. Retention is handled by `/opt/Mobiup/ops/scripts/backup-retention.sh` and is based on complete/checksum-verified generations. Treat these as external operational facts and revalidate the installed scripts before relying on them for a destructive operation.

### Restore boundary — intentional fail-closed gap

**There is currently no canonical maintained full database restore runbook/entrypoint.** The server contains recovery/probe helpers, but they do not constitute a full PostgreSQL + visits restore procedure.

Therefore this K3 runbook does **not** provide guessed `pg_restore`, drop/create, service-quiesce or in-place restore commands. A real restore is potentially destructive and belongs to **Issue #231 / K5 — real disaster-recovery restore exercise and evidence** under the **Backup / Disaster Recovery Administrator** role and explicit execution authorization.

If a restore is required before K5 closes:

1. preserve the failing state and evidence;
2. identify the required data scope and last known verified backup generation;
3. do not overwrite production based on an improvised procedure;
4. escalate for an explicitly authorized DR operation.

A non-destructive NAS sample restore probe is evidence about backup availability, not evidence that the complete application can be restored.

## 7. Worker and dependency verification

### Runtime units

Use read-only state inspection:

```bash
ssh -o BatchMode=yes server '
  for unit in \
    unihub-backend.service \
    unihub-worker.service \
    unihub-import-worker.service \
    unihub-grile-worker.service \
    unihub-export-worker.service \
    unihub-salary-export-worker.service \
    unihub-retail-migrate.service
  do
    printf "\n[%s]\n" "$unit"
    systemctl show "$unit" --property=LoadState,ActiveState,SubState,User,Group,FragmentPath --no-pager
  done
'
```

The migration one-shot is normally inactive except when deliberately executing a reviewed migration. Do not treat `inactive` alone as a failure for that unit.

### PostgreSQL and Valkey

Start with `/readyz`; it already exercises the dependencies required for authenticated Retail requests. If readiness fails, inspect service/container state without exposing connection strings, then follow logs/metrics. Do not run ad-hoc SQL writes as a health check.

### Authentik/JWKS

A healthy `/readyz` requires usable JWKS state. Read the finite-cardinality `jwks_readiness_state` signal before requesting Authentik administrative access. Administrative access is not needed merely to prove the application has a fresh/usable JWKS cache.

### Metrics

Use `probe_success{job="blackbox_retail_readiness"}` for the external readiness path and the recording/alerting contract in `docs/operations/retail-slo-readiness.md`. Do not treat a missing metric as success; determine whether scrape/config/traffic prerequisites are absent.

## 8. What must never be done directly on production

Without a separately authorized, documented exception:

- no direct runtime code edits;
- no direct `git pull`, branch switching, hard reset or force update to make production “look current”;
- no local rebuild substituted for the CI artifact;
- no manual migration execution outside the reviewed migration/release path;
- no database mutation as a diagnostic shortcut;
- no destructive Grile reset, salary promotion, P&L/finance promotion or import mutation merely to test availability;
- no secret copied into GitHub, chat, logs or documentation;
- no permission weakening (`chmod 777`, broad sudo, Docker access, shared credentials) to bypass an ownership problem;
- no Cloudflare/Caddy/Authentik/monitoring mutation merely because a downstream health probe failed;
- no improvised full restore until a reviewed DR procedure exists and the operation is explicitly authorized;
- no squash/rebase merge for repository changes; the repository policy requires merge commits.

Break-glass remains limited by ADR-006 and is not a convenience path.

## 9. Common failure modes: first evidence, not first mutation

| Symptom | First evidence to collect | Do not do first |
| --- | --- | --- |
| GitHub `main` differs from production HEAD | both SHAs, live branch, worktree cleanliness, exact D3 tag state | `git pull`/`reset` |
| live HEAD has no valid exact D3 promotion tag | exact production HEAD plus D3 tag ref/object evidence | invent/select a D2 handle or create a tag |
| a task requires D2 state but no approved atomic read path exists | task scope and formal release-tooling boundary | `sudo cat`, temp copies or generic privileged interpreters |
| `/livez` fails | backend unit state and bounded logs | restart repeatedly |
| `/livez` works but `/readyz` fails | PostgreSQL/Valkey state, `jwks_readiness_state`, readiness logs | edit auth/DB config |
| local `/readyz` works but public `/readyz` fails | blackbox signal, Cloudflared state, Caddy state | mutate DNS/tunnel/proxy |
| one worker is down | exact unit state, recent journal, queue/backlog metrics for that worker | restart every worker |
| backup gate fails/stale | `status`, `checksum_ok`, `completed_at`, backup script/log evidence | rerun deploy or weaken gate |
| service identity verifier fails | exact verifier error plus live-root canonicalization result | run provisioning `apply` automatically |
| CI/check fails | exact run → job → step → log/root cause | blind rerun |
| restore is requested | required data scope, verified backup evidence, K5 status | improvise `pg_restore` on production |

For any new commit, old SHA-bound CI/review evidence is stale. For an unchanged SHA/tree, do not rerun expensive verification ritualistically.

## 10. ChatGPT / Dell / server execution split

### ChatGPT principal agent

ChatGPT owns operations that can be safely performed through the GitHub connector/API:

- current-state reads;
- issue/tracker maintenance;
- PR/diff/commit/status/workflow inspection;
- Codex review triage and thread handling;
- branch/PR metadata and repository file changes when exposed safely;
- merge after exact certification;
- post-merge GitHub verification.

Do not delegate remote GitHub operations to Dell merely because a shell can run `gh`.

### Dell / server handoff

Use Dell only for operations that require the local filesystem, local test/build tools, a workflow dispatch not exposed by the connector, or the real server/runtime. Every handoff must bind the exact repo/branch/HEAD/base, allowed surfaces, commands, stop conditions and evidence to return.

A Dell/server handoff grants **no new mutation scope by itself**. If the task is read-only, commands must remain read-only. If the underlying operational request already explicitly authorizes an end-to-end PR or mutation scope, that authorization remains valid through the covered merge, post-merge CI, deploy/restart and live verification steps without repeated approval, while every technical gate and scope boundary still applies. Any mutation outside the existing authorized scope requires new explicit authorization.

## 11. Emergency ownership roles

Maintain access to the following organizational roles outside this repository. This document intentionally contains no personal contacts or credentials:

- Repository/GitHub Administrator;
- Production Host Operator;
- Identity / Authentik Administrator;
- DNS/Tunnel Administrator;
- Reverse Proxy Administrator;
- Monitoring Administrator;
- Backup / Disaster Recovery Administrator;
- Retail Business Owner for business-data promotions/approvals.

If a named person is unavailable, resolve the role through the organization’s authorized contact process rather than adding personal data to this repository.

## 12. Resume the active improvement program

For a new ChatGPT session or successor operator:

1. fetch current GitHub `main`;
2. read GitHub Issue #226 body and newest comment;
3. inspect K1–K10 children #227–#236 and choose the first open, unblocked item in the tracker order;
4. read that child’s body and newest checkpoint;
5. revalidate its assumptions against current GitHub state before mutation;
6. perform one logical step and verify independently;
7. update the child with exact evidence;
8. update #226 only after the child Definition of Done is actually certified.

Issue comments contain evidence snapshots, not permanent current-state authority.

## Successor read-only checklist

A successor who can complete the following without private memory has enough orientation to operate safely for routine observation and to request the right authorization for mutations:

- [ ] determine GitHub `main` SHA;
- [ ] determine production branch/HEAD and clean/dirty state;
- [ ] bind the observed production HEAD to the exact structurally valid D3 promotion tag and explain why D3 does not replace independently validated D2 state;
- [ ] explain when D2 must be independently verified and stop if no approved atomic read/validation path exists;
- [ ] run local `/livez`, local `/readyz` and public `/readyz`;
- [ ] inspect Retail systemd units and distinguish the migration one-shot from long-running services;
- [ ] explain that PostgreSQL, Valkey and usable JWKS state gate readiness;
- [ ] identify the credential-free Prometheus readiness/JWKS signals;
- [ ] verify service identities and env-file ownership without reading secret values;
- [ ] verify backup completion manifest fields without executing backup;
- [ ] explain why a full restore is blocked on the K5 canonical DR procedure rather than improvising one;
- [ ] identify the administrator role for GitHub, host, Authentik, DNS/tunnel, proxy, monitoring and backup/DR;
- [ ] explain ChatGPT vs Dell/server execution ownership;
- [ ] resume Issue #226 and select the first open, unblocked child.
