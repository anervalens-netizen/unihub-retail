# Verification efficiency policy

This document is a persistent operating contract for repository verification.
It exists to prevent correctness controls from drifting into process overhead
that delays ordinary software delivery without adding proportional confidence.

## Core rule

**Efficiency is a correctness requirement.** Verification must make false
completion difficult while remaining proportional to the change. A fast lane
that routinely behaves like FULL is defective even if every individual check
is defensible in isolation.

## PR-fast invariant

`pr-fast` is a fast feedback lane, not a miniature FULL run.

- Normal target: **under 10 minutes**.
- Hard workflow timeout: **15 minutes**. This is a guardrail, not an expected
  runtime and must not be increased merely to fit more work.
- Ordinary PR work should receive targeted/affected verification.
- Large affected-backend fan-out belongs in `PR-DEEP`, not `pr-fast`.
- Exact-main FULL remains independent release/checkpoint authority.

### Evidence-based affected-test budget

The initial routing budget is **120 selected backend test files**.

Live evidence that defines this boundary:

- validation PR #173: `selection_count=111`, exact-head `pr-fast` completed in
  about **7m35s** and passed;
- C7 PR #184: `selection_count=133`; the affected-backend step ran **11m38s**
  and the overall `pr-fast` job hit its 15-minute hard timeout before the
  selected suite completed.

Therefore a selector result above 120 selected backend test files must become
`ESCALATION_REQUIRED` and route to `PR-DEEP`. The threshold may change only
from measured evidence showing that the normal fast-lane target remains
satisfied; do not raise the timeout to hide routing failure.

## Proportional verification

Use the smallest authoritative evidence set that matches the risk.

- Docs-only / Markdown-only changes are non-runtime and must not launch the
  heavy CI workflow under the current repository enforcement model.
- Tracker-only changes require no code CI.
- Low/medium-risk runtime changes use focused local checks plus the normal
  affected PR lane.
- High-risk/control-plane changes use their required governance and deep
  certification paths.
- FULL is not a per-PR or per-merge ritual. It is justified only by the master
  tracker policy: release/promotion, a deliberate checkpoint, material
  control-plane change whose correctness depends on FULL, unresolved
  uncertainty, or explicit owner request.

Required cheap controls that protect repository integrity may remain active;
"proportional" does not mean bypassing a control that the change actually
activates.

## No ceremonial reruns

- Never rerun an unchanged failed/cancelled candidate until the failure mode is
  diagnosed.
- A hard-timeout rerun with the same workflow definition and same candidate is
  prohibited unless there is evidence the timeout was caused by a transient
  external condition rather than deterministic workload.
- Reuse still-valid exact-SHA evidence. Do not repeat lint, mypy, tests, review,
  or certification on unchanged content merely to create fresh timestamps.
- When HEAD changes, rerun only evidence invalidated by that change or required
  by the repository's exact-head authority model.

## One bounded remediation cycle

For a failing PR:

1. identify the largest real blocking gap;
2. fix that gap only;
3. run the smallest focused local checks that can catch an immediate mistake;
4. push one bounded candidate;
5. let repository-native exact-head gates decide what additional evidence is
   required;
6. do not perform multiple speculative verifier/CI cycles in parallel.

If a new mechanism adds substantial recurring runtime to ordinary PRs, its
change must include measured before/after cost and prove that the normal fast
path still meets the target. Otherwise route that work to `PR-DEEP` or FULL.

## Persistent coordinator/agent rules

- Prefer delivery over administration when correctness evidence is already
  sufficient.
- Do not create new frameworks, generic verification machinery, temporary
  environments, or documentation layers solely to satisfy process aesthetics.
- Do not broaden a task because a verifier can imagine unrelated improvements.
- A verifier should search for false completion and material regressions, not
  manufacture extra ceremony.
- Preserve architecture, governance, security, coverage, release, and
  irreversible-action boundaries; optimize routing and duplication rather than
  weakening those authorities.

## Relationship to other sources

- GitHub issue #159 remains the audit-remediation master tracker and contains
  the 2026-08-21 operating-invariant amendment that reopened E2 operationally
  until the fast-lane regression is corrected and live-proven.
- `docs/engineering/pr-fast-lane.md` describes the concrete fast-lane design.
- `AGENTS.md` defines the default agent behavior and GitHub Actions budget.
- If these sources disagree on verification cost, this policy and the latest
  tracker amendment take precedence until the stale text is corrected.
