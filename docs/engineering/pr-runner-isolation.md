# PR runner isolation and release artifact boundary

## Decision

Pull-request code runs only on GitHub-hosted runners. The production host and
the persistent `unihub-server` runner are not valid PR execution targets.

The CI workflow has read-only repository permissions and does not consume
deployment secrets. It proves the hosted-runner boundary before executing the
test jobs: the production filesystem is absent, the production runner identity
is absent, no Tailscale interface is present, and the private TimesFM peer is
unreachable. Docker used by isolated PostgreSQL tests belongs only to the
ephemeral GitHub-hosted VM; no production Docker socket or mount is available.

## Private package distribution

Retail vendors the four exact `@unihub/*` package tarballs already identified
by the previous `package-lock.json` SHA-512 values under `vendor/npm/`.
`scripts/verify_vendored_npm_packages.mjs` checks every file dependency and
integrity before `npm ci`. A clean checkout therefore needs neither the
host-local Verdaccio endpoint nor a registry token.

The vendored files are dependency inputs, not generated business artifacts.
Updating one requires a separately reviewed shared-package release, an exact
version change, updated lock integrity, consumer tests, and replacement of only
the corresponding tarball. Never copy a Verdaccio token into GitHub Actions.

## Build and deploy separation

On a successful push to `main`, the tested frontend job creates one immutable
release bundle from `git archive` plus the tested `dist/` output. CI writes the
source SHA and SHA-256 manifest next to the bundle and uploads them as a GitHub
artifact. Pull requests never create deployable release artifacts.

The deploy workflow:

1. accepts only a successful `CI` push run for `main`;
2. downloads that run's exact release artifact without checking out source;
3. verifies the requested source SHA and every SHA-256 entry;
4. targets only the dedicated `unihub-deploy` runner label;
5. invokes a root-owned deployment entrypoint outside the checkout;
6. is fail-closed unless repository variable
   `PRODUCTION_DEPLOY_APPROVALS_ENFORCED=true` is present.

GitHub required reviewers are available for private repositories only with
GitHub Enterprise, which is not part of the current plan. The production gate
therefore uses a host-enforced human approval rather than pretending that an
unprotected GitHub environment is sufficient. `approve-retail-release.sh`
creates a root-only, 30-minute, one-time record bound to the exact successful CI
run, `main` source SHA and artifact SHA-256. The deploy entrypoint must claim the
matching record before any application mutation. It finalizes the record as
`consumed` or `failed`; expiry, reuse, duplicates and mismatches fail closed.

The reviewed entrypoint source is `ops/deploy-retail-artifact.sh`; its sandbox
test is `ops/test-deploy-retail-artifact.sh`. The production copy is installed
separately at `/opt/Mobiup/ops/scripts/deploy-retail-artifact.sh`, with both the
file and parent directory owned by root and writable only by root. Its installed
SHA-256 is recorded during rollout and must match the reviewed source exactly.
The deploy job must never install or replace this privileged copy.

Before changing production, the entrypoint copies the runner-owned artifact to
a root-only temporary directory, rejects unsafe archive members, and compares
all source files (excluding only the separately tested root `dist/`) to the exact
`origin/main` commit. It permits only a fast-forward from the current production
SHA, requires a completely clean production worktree and a fresh verified backup
generation, stops web/worker, switches the tested frontend, runs the one-shot
migration unit, and checks local liveness/readiness. Failure after the switch
automatically restores the old Git SHA and frontend. Manual rollback is root-only;
the `unihub-deploy` service identity is
explicitly refused that mode.

The sandbox covers missing approval, invalid approval identity, duplicates,
single consumption, expiry, digest mismatch, success, manual rollback, injected
health failure with automatic rollback, source tampering, path traversal,
archive symlinks and an unexpected dirty worktree. The exact final CI artifact
must also pass the entrypoint's read-only `validate` mode before approval.

## Controlled isolation evidence

The `runner-isolation` job is the repeatable proof. It must remain required by
both backend and frontend jobs. Its assertions intentionally refer only to
infrastructure identity and reachability; they never inspect or print secrets.

The old `unihub-server` Retail runner is stopped and removed from the repository
runner inventory. It must not be reused for deployment. Register a separate OS
identity only with the dedicated `unihub-deploy` label after the root approval
boundary and exact sudo policy are installed, and never add that label to a
pull-request workflow. That identity must have no Docker group, production
secret read access, interactive credentials or general sudo.

## Rollback

Reverting package vendoring or restoring the self-hosted PR labels reopens the
critical finding and is not an acceptable production rollback. If hosted CI is
unavailable, stop merges and deployments until it recovers. Existing releases
remain runnable because runtime does not fetch npm packages.

Application rollback uses the root entrypoint's verified backup handle. The
three v2.0.1 migrations are additive, so code rollback keeps the expanded schema;
the verified PostgreSQL dump is reserved for disaster recovery rather than an
automatic destructive restore that could discard writes made after deployment.
