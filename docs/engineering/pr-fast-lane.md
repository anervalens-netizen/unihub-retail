# PR-fast lane

`pr-fast` is the normal repository feedback lane for runtime/code PRs. It exists
to catch relevant regressions quickly without turning every change into FULL.

## Current server-side authority

`main` is protected by the active repository ruleset `Protect main`:

- pull request required;
- merge method: `merge` only;
- review-thread resolution required;
- no bypass actors;
- required statuses include `Validate release authority and docs` and
  `retail/pr-merge-gate`.

Therefore old documentation claiming that the repository has no server-side
PR/merge enforcement is historical and must not be used to justify redundant
CI duplication.

## Normal target

- `pr-fast`: target under **10 minutes**;
- 15-minute workflow timeout is a guardrail, not a target;
- docs-only work should not start heavy code CI;
- unchanged failures/timeouts are not blindly rerun;
- verification cost follows
  [`verification-efficiency-policy.md`](verification-efficiency-policy.md).

## Trigger model

Current heavy CI trigger model:

```yaml
on:
  workflow_dispatch:
  pull_request:
    branches:
      - main
    paths-ignore:
      - "**/*.md"
      - "docs/**"
```

Docs/Markdown-only PRs are intentionally excluded from heavy code CI.

## Routing

### Ordinary PR

```text
focused local checks
→ pr-fast
→ native policy/gates
→ merge when required statuses/review state are satisfied
```

### Escalated backend PR

The trusted selector can return `ESCALATION_REQUIRED` for cases where affected
selection cannot safely remain in the fast lane, including trust/control-plane
surfaces, dependency/wiring changes, relevant deletions, changed dynamic-import
surfaces, or affected-test fan-out above the current budget.

Current budget:

`MAX_PR_FAST_SELECTED_TEST_FILES = 120`

When native policy requires escalation:

```text
pr-fast/policy classification
→ one exact-head/base PR-DEEP
→ merge after required status is green
```

Do not dispatch PR-DEEP manually merely because a change is runtime code or
because a historical audit used PR-DEEP.

## What PR-DEEP means

PR-DEEP is the exhaustive **backend escalation lane**. It is not FULL and is not
a standard second pass after every PR.

A successful exact-head/base PR-DEEP satisfies the backend escalation question
for that candidate. If the merge commit introduces the same certified tree and
no release is being produced, do not automatically start another FULL run.

## What FULL means

The manually dispatched exact-main FULL lane remains available for:

- formal release/deploy artifact creation and provenance;
- explicit checkpoints;
- concrete unresolved cross-lane/control-plane risk;
- explicit owner request.

FULL is not required after every PR, every merge, or every PR-DEEP. For release
semantics see [`../adr/006-verified-runtime-delivery.md`](../adr/006-verified-runtime-delivery.md).

## Affected backend selection

The trusted selector in `scripts/pr_fast_select_tests.py` runs from base-side
trusted logic and classifies the exact candidate diff before importing mutable
candidate gate authority. Its four states are:

- `NO_ELIGIBLE_BACKEND_CHANGE`;
- `SELECTED`;
- `ESCALATION_REQUIRED`;
- `ERROR`.

An oversized otherwise valid affected suite (>120 selected backend test files)
escalates instead of expanding `pr-fast` until it behaves like FULL.

Measured historical basis for the budget:

- 111 selected files completed in about 7m35s;
- 133 selected files caused the affected backend work to exceed the intended
  fast-lane envelope and the job hit its 15-minute guardrail.

Do not increase the timeout just to absorb more work. Change the threshold only
from new measured evidence.

## Frontend affected mode

Frontend verification uses affected Vitest mode for ordinary PRs and forces the
full frontend test path when test/configuration authority changes. Classifier
errors fail closed.

## High-risk governance

High-risk governance remains orthogonal. Current categories include auth/
identity, migrations/DB authority, deploy/release/CI, salary/private identity and
target-calculator surfaces. Activating a relevant high-risk gate does not imply
that unrelated FULL lanes must also run.

## No ceremonial duplication

For every proposed extra verification step ask:

1. what concrete risk is being checked?
2. what new evidence does this produce?

If the existing exact candidate evidence already answers the question, do not
run another workflow for ceremony. In particular, do not use the old pattern
`PR-DEEP -> merge -> FULL` unless the FULL has a separate release/checkpoint
purpose.