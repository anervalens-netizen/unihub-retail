# Retail execution-plan contract

Execution plans are a coordination tool, **not a prerequisite for ordinary
work**.

## When to create a plan

Create exactly one living plan under `docs/exec-plans/active/` only when the
objective is genuinely substantial: multi-session, high-risk, coordination-
heavy, difficult to resume safely, or explicitly requested by the owner.

Do **not** create a plan for a bounded bug fix, small feature, UI change,
documentation update, test adjustment, dependency patch or other task that can
be understood directly from the issue/PR and repository state.

If a plan is warranted, it is the single authority for scope, acceptance,
progress and recovery. Audit reports and historical handoffs are inputs, not
competing trackers.

## Lean lifecycle

1. Record only the baseline needed to avoid acting on stale state.
2. Define observable acceptance criteria proportional to the requested outcome.
3. Build bounded lots; do not use GitHub Actions as an iterative test runner.
4. Use independent critique/review only when risk or uncertainty justifies it.
5. Apply the smallest authoritative verification set from
   `docs/engineering/verification-efficiency-policy.md`.
6. If production delivery is in scope, use ADR-006 exact-artifact provenance.
7. Mark `DONE` when the requested outcome is proven; do not invent additional
   audit/hardening work to prolong the plan.

## Evidence rules

- Evidence is concise, sanitized and tied to the identity/scope it actually
  proves.
- Never persist credentials, CNP, salary values, personal names or raw
  production payloads.
- User-attested acceptance is recorded as such and is not needlessly replayed.
- A failed gate is rerun only after a relevant change or a demonstrated
  transient external failure.
- Reuse still-valid evidence; a new SHA alone is not a reason to replay every
  technical test when relevant content/semantics are unchanged.

## Current repository-wide objective

**None.** Audit programs #159 and #226 are completed historical evidence. New
work uses a task-specific issue/PR and creates a living execution plan only when
the criteria above genuinely require one.