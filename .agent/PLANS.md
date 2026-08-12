# Retail execution-plan contract

Substantial objectives use exactly one living plan under
`docs/exec-plans/active/`. The active plan is the authority for scope,
acceptance, progress, evidence and recovery; audit reports and historical
handoffs are inputs, not competing trackers.

## Required lifecycle

1. Record the exact Git/runtime baseline and preserve unrelated/user work.
2. Define observable acceptance criteria. Every criterion starts
   `UNVERIFIED`; absence of evidence is not `FAIL`.
3. Obtain an independent contract critique before high-risk implementation.
4. Build bounded lots locally. Do not use GitHub Actions as an iterative test
   runner and do not repeat gates against unchanged content.
5. Obtain an independent acceptance verdict against the integrated artifact.
6. Deliver runtime changes only through ADR-006 exact-SHA provenance.
7. Mark `DONE` only after every criterion is `PASS`, production proof is
   complete and Git/runtime state is reconciled. Move the plan to
   `docs/exec-plans/completed/` when closed.

## Evidence rules

- Evidence is concise, sanitized, reproducible and tied to an exact SHA.
- Never persist credentials, CNP, salary values, personal names or raw
  production payloads.
- User-attested acceptance is recorded as such and is not needlessly replayed.
- A failed gate is rerun only after a relevant change; after two no-progress
  cycles, diagnose and replan once instead of looping.

## Active objective

- `UR-CLOSE-20260812` — definitive closure of the remaining 2026-08-12 Retail
  audit/improvement-plan findings.
