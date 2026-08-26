# UniHub Retail — current audit remediation handoff

Date refreshed: 2026-08-26
Repository: `anervalens-netizen/unihub-retail`
Status authority: GitHub issue #159

## Restart rule

At the start of a new session, read the current body of issue #159 first. Current GitHub state wins over this snapshot if anything has moved. Do not reconstruct historical PRs unless the current task requires it.

## Post-E6 stable anchor

This document refresh is intentionally based on the certified post-E6 anchor immediately before the docs-only refresh PR. The docs-only merge itself will move `main`; issue #159 remains the live authority.

- post-E6 `main`: `dc443a505e261c90867089b90b69b18df496d930`
- post-E6 tree: `5f4ac2fb473df821aa749fcf96f720c23a9bfdd6`
- E6 merge parents:
  1. `e5891470e2fb04599b934df43348fea128506e83`
  2. `21952d379c279df178986569a0c36f495ff5cddf`
- E6 merge `main-push-policy`: run `33002794851` — SUCCESS
- last deliberate FULL anchor: run `32780412711` — SUCCESS on prior main `5e41e6558e6c29b364fbc8f6af26f19b3bfbaeb5` / tree `74f0591ab1fe562984b38dc9683c7a7f968455f3`
- do not rerun FULL merely because later low-risk work moves `main`; FULL is a deliberate checkpoint, not a per-merge ritual.

## Operating rules

- GitHub work is owned by the coordinating assistant. Use Dell/server only for actions that genuinely require local, runner, production, or unavailable GitHub capabilities.
- Work autonomously; do not ask for routine confirmations.
- DONE requires exact evidence: SHA, tree, run IDs, statuses, and topology where relevant.
- Current GitHub state is source of truth. Any handoff SHA/status that differs from live GitHub is stale.
- Do not repeat verification when the candidate SHA/tree has not changed.
- A new commit invalidates old exact-head CI, PR-DEEP, and Codex certification unless the evidence is explicitly reusable for an unchanged tested artifact/tree and the repo policy permits that use.
- Never blindly rerun a failed workflow. Diagnose the exact job/step/log/artifact and root cause first.
- `pr-fast` is the normal runtime PR gate. PR-DEEP is exact-head/exact-base escalation when policy requires it.
- While exact-base PR-DEEP is pending, do not move `main`; doing so invalidates the certification base.
- Merge-commit-only governance is intentional. When certification is bound to an exact PR head, merge with `expected_head_sha` and verify both merge parents afterward.
- After merge, verify `main == merge commit`, capture the merge tree, and require fresh `main-push-policy` SUCCESS on the exact merge commit before marking the workstream DONE.
- No deploy, tag, promotion, release, production mutation, migration execution, data regeneration, or irreversible action merely because code/CI is certified.
- Prefer the minimum process that makes false completion difficult; avoid ceremony that adds no correctness value.

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
- E6 DONE via PR #201: simplify CI implementation without weakening evidence.

E6 exact evidence:

- exact base: `e5891470e2fb04599b934df43348fea128506e83`
- exact certified head: `21952d379c279df178986569a0c36f495ff5cddf`
- candidate tree: `5f4ac2fb473df821aa749fcf96f720c23a9bfdd6`
- fresh CI run `32990800135`: SUCCESS
- docs-contract run `32990800121`: SUCCESS
- exact-head Codex: clean on `21952d379c`
- review threads: zero
- PR-DEEP run `32996897490`: SUCCESS
- SHA-bound `retail/pr-deep`: SUCCESS with exact base
- SHA-bound `retail/pr-deep-policy`: SUCCESS with exact base
- merged as `dc443a505e261c90867089b90b69b18df496d930`
- exact merge parents: `[e5891470e2fb04599b934df43348fea128506e83, 21952d379c279df178986569a0c36f495ff5cddf]`
- merge tree: `5f4ac2fb473df821aa749fcf96f720c23a9bfdd6`
- post-merge `main-push-policy` run `33002794851`: SUCCESS
- production boundary remained untouched.

### Phase F — database / migrations

- F1 DONE via PR #192: explicit online/non-transactional migration path.
- F2 DONE via PR #193: controlled concurrent-index recovery.
- F3 DONE via PR #198 plus certified P1 follow-up PR #199: transactional default and immutable checksum/ledger guarantees preserved, including lost-update race handling.
- F4 DONE via PR #200: explicit transactional / online / maintenance-window classification with exact-filename maintenance authorization and release/deploy tooling parity.

F4 final anchor before E6:

- merge commit: `e5891470e2fb04599b934df43348fea128506e83`
- certified head: `48342ba1eca4eee0de01267238f260bf18fd9784`
- exact base: `d3ee8a6679120f69c2ced992798294c9b5512253`
- PR-DEEP run `32946289113`: SUCCESS
- `main-push-policy` run `32949932381`: SUCCESS

## Promo business fix — DONE

Issue #194 / PR #196 fixed isolated-return netting and is merged. Existing materialized Promo generations remain unchanged because no deployment or regeneration was authorized.

Certified merge anchor:

- PR head: `09bc1a5c80ec33058269fd70b689e0826743f2d3`
- exact base: `5e41e6558e6c29b364fbc8f6af26f19b3bfbaeb5`
- PR-DEEP run `32829419427`: SUCCESS
- merged as `2ac80af789e521649c4f4f885b3b590aeda1f296`
- `main-push-policy` run `32833224410`: SUCCESS

## Known follow-up debt discovered during F4

Do not fold this into already-completed F4. A separate future remediation should harden env-contract constant detection and reconcile these five pre-existing latent environment variables:

1. `EFFECTIVE_DATED_VAT_ENABLED` — `backend/services/fiscal_rules.py`
2. `PROMETHEUS_DOCKER_GATEWAY` — `backend/observability/metrics_network.py`
3. `PROMETHEUS_DOCKER_SUBNET` — `backend/observability/metrics_network.py`
4. `SALARY_APPROVAL_REVIEWER_PUBLIC_KEYS_JSON` — `backend/salary_import_approval.py`
5. `UNIHUB_DB_AUTHORITY_CUTOVER_BOOTSTRAP` — `backend/db/migration_runner.py`

Do not solve the drift by allowlisting/suppressing it or weakening the env-contract gate.

## Standing architecture guardrail

Issue #170 remains valid: portability is a decision rule, not a speculative implementation task.

## Current execution order

1. A5 remains externally blocked until GitHub Support #4696487 provides actionable confirmation. Do not perform destructive/final-disposal work before that condition is met.
2. Finish this docs-only handoff refresh through normal governance; PR-DEEP only if policy explicitly requires it.
3. Continue from then-current `main` with the next unblocked audit-remediation workstream. E4/E5 remain the outstanding Phase E resilience pair.
4. I5 remains later work; it must not weaken delivery evidence or single-operator recovery guarantees.

## Production boundary

This handoff authorizes no production action. Do not deploy, tag, release, promote, regenerate Promo data, run migrations, mutate production state, or delete retained A5 backups without the separate condition/authorization described above.
