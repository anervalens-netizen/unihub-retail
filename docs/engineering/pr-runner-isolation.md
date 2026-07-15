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

The production environment must have required-reviewer protection before that
variable is enabled. The current private repository plan does not expose branch
protection or required environment reviewers; release/deploy remains blocked
until the repository plan or hosting policy supplies those controls. Manual
merge discipline is not represented as an enforced GitHub protection.

Pre-rollout inspection also found that the expected root-owned entrypoint
`/opt/Mobiup/ops/scripts/deploy-retail-artifact.sh` is not provisioned. This is a
second intentional fail-closed prerequisite: do not register the deploy runner
or enable `PRODUCTION_DEPLOY_APPROVALS_ENFORCED` until the entrypoint is installed
from a separately reviewed operations source, owned and writable only by root,
and its backup, migration, health and rollback behavior has been exercised. The
deploy job must never install that privileged entrypoint from PR-controlled code.

## Controlled isolation evidence

The `runner-isolation` job is the repeatable proof. It must remain required by
both backend and frontend jobs. Its assertions intentionally refer only to
infrastructure identity and reachability; they never inspect or print secrets.

After PR-00 is merged, remove the `unihub-server` label from the persistent
Retail runner or stop that runner. If it is retained for deployment, register
it only with the dedicated `unihub-deploy` label and never add that label to a
pull-request workflow.

## Rollback

Reverting package vendoring or restoring the self-hosted PR labels reopens the
critical finding and is not an acceptable production rollback. If hosted CI is
unavailable, stop merges and deployments until it recovers. Existing releases
remain runnable because runtime does not fetch npm packages.
