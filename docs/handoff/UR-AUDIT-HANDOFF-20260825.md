# UniHub Retail — current audit remediation handoff

Date: 2026-08-25
Repository: `anervalens-netizen/unihub-retail`
Status authority: GitHub issue #159

## Restart rule

At the start of a new session, read the current body of issue #159 first. Current GitHub state wins over this snapshot if anything has moved. Do not reconstruct historical PRs unless the current task requires it.

## Current stable anchor

- `main`: `2ac80af789e521649c4f4f885b3b590aeda1f296`
- tree: `3533a0b14049ccaf4a202bf143a03f4f5a7e3c6e`
- merge commit for Promo PR #196 parents:
  1. `5e41e6558e6c29b364fbc8f6af26f19b3bfbaeb5`
  2. `09bc1a5c80ec33058269fd70b689e0826743f2d3`
- merge `main-push-policy`: run `32833224410` — SUCCESS
- last deliberate FULL anchor: run `32780412711` — SUCCESS on prior main `5e41e6558e6c29b364fbc8f6af26f19b3bfbaeb5` / tree `74f0591ab1fe562984b38dc9683c7a7f968455f3`
- do not rerun FULL merely because later low-risk work moved `main`; FULL is a deliberate checkpoint, not a per-merge ritual.

## Operating rules

- GitHub work is owned by the coordinating assistant. Use Dell/server only for actions that genuinely require local, runner, production, or unavailable GitHub capabilities.
- Work autonomously; do not ask for routine confirmations.
- DONE requires exact evidence: SHA, tree, run IDs, statuses, and topology where relevant.
- Do not repeat verification when the candidate SHA/tree has not changed.
- Never blindly rerun a failed workflow. Inspect the failure and decide whether the evidence is stale, the candidate changed, or remediation is required.
- `pr-fast` is the normal runtime PR gate. PR-DEEP is exact-head/exact-base escalation when policy requires it.
- While exact-base PR-DEEP is pending, do not move `main`; doing so invalidates the certification base.
- Merge-commit-only governance is intentional. When certification is bound to an exact PR head, merge with `expected_head_sha` and verify both merge parents afterward.
- No deploy, tag, promotion, production mutation, data regeneration, or irreversible action merely because code/CI is certified.
- Minimum process that makes false completion difficult; avoid ceremony that adds no correctness value.

## Dell/server prompt routing rule

Every instruction handed to Dell/server for direct execution must include both:

- `Difficulty: X/10`
- a recommended model tier

Score by technical complexity, operational risk, reasoning depth, and blast radius — not prompt length.

Routing guideline:

- 1–3: inexpensive/simple model, DeepSeek-class
- 4–6: MiniMax-class / medium capability
- 7–9: strong reasoning model
- 10: GPT-5.6 Sol / highest-confidence execution

Bundle related local actions when safe instead of sending many small prompts.

## Governance / remediation state

### Phase A — GitHub / governance

- A1 DONE: active ruleset `20896761`, no bypass actors, PR required, deletion blocked, non-fast-forward blocked, native required check `Validate release authority and docs`, merge-commit-only repository policy.
- A2–A4 DONE.
- A5 WAITING ON GITHUB SUPPORT ticket #4696487.

A5 current facts:

- public branch/tag history was rewritten and certified;
- fresh Dell authority clone is sanitized;
- stale push-capable histories were quarantined and runner workspace cleaned;
- revoked credential was scrubbed from four DSH session ledgers;
- GitHub Support found the sensitive first-introduction commit still referenced by 192 historical PRs;
- Support offered full deletion of affected historical PRs or internal-ref deletion followed by server-side purge/GC;
- user preference is full deletion because those historical PRs are not operational dependencies;
- do not assume Support has authorization until there is explicit confirmation that the reply was sent or a newer Support message proves it;
- restricted forensic/local-branch/stale-checkout backups remain retained until purge confirmation; then perform one final disposal operation.

### Phase B — quality-gate integrity

COMPLETE: B1–B4.

### Phase C — complexity reduction

COMPLETE: C1–C8.

### Phase D — release identity / source of truth

COMPLETE: D1–D5.

### Phase E — CI performance / resilience

- E1–E3 DONE.
- E4 pending: reduce single-runner dependency / evaluate identical or ephemeral runners.
- E5 pending: preserve runner-isolation guarantees after parallelization.
- E6 pending: simplify CI implementation without weakening evidence.

### Phase F — database / migrations

- F1 DONE via PR #192: explicit online/non-transactional migration path.
- F2 DONE via PR #193: controlled concurrent-index recovery.
- F3 NEXT: preserve transactional default plus immutable checksum/ledger guarantees.
- F4 AFTER F3: explicit transactional / online / maintenance-window classification.

## Promo business fix — DONE

Issue #194 / PR #196 fixed isolated-return netting and is merged.

Certified candidate:

- PR head: `09bc1a5c80ec33058269fd70b689e0826743f2d3`
- exact base: `5e41e6558e6c29b364fbc8f6af26f19b3bfbaeb5`
- PR-DEEP run `32829419427`: SUCCESS
- `retail/pr-deep`: SUCCESS, `PASS base=5e41e6558e6c29b364fbc8f6af26f19b3bfbaeb5`
- `retail/pr-deep-policy`: SUCCESS, same exact base
- merged as `2ac80af789e521649c4f4f885b3b590aeda1f296`
- `main-push-policy` run `32833224410`: SUCCESS
- issue #194 closed automatically

Behavior now preserves non-zero signed net rows, omits zero-net keys, keeps all-returns fail-closed, rejects a globally negative signed `promo_units` total before publication, and keeps Incentive/copurchase consumers positive-only.

Production boundary: no deployment or Promo regeneration has been performed. Existing materialized generations are unchanged. A future production correction requires separate authorization for deployment plus regeneration from the same source and live verification of gross `244`, returns `-2`, net `242`, with Incentive unaffected incorrectly.

## Standing architecture guardrail

Issue #170 remains valid: portability is a decision rule, not a speculative implementation task.

## Current execution order

1. Finish and merge this docs-only handoff PR after normal docs governance passes. Do not escalate to PR-DEEP unless policy actually requires it.
2. A5 only when GitHub Support #4696487 provides actionable confirmation.
3. Start F3 from then-current `main`; finish with exact evidence.
4. Then F4.
5. E6 and I5 later; neither may weaken delivery evidence.

## Production boundary

This handoff authorizes no production action. Do not deploy, tag, promote, regenerate Promo data, mutate production state, or delete retained A5 backups without the separate condition/authorization described above.
