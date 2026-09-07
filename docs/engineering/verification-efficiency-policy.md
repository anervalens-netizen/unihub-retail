# Verification efficiency policy

This is the **canonical operating policy for verification cost and routing** in
UniHub Retail. When another active document appears to require more verification
than this policy, interpret that requirement narrowly or correct the stale text.
Historical audit trackers are evidence, not execution authority.

## Prime directive

**Use the smallest authoritative evidence set that can falsify the change at its
actual risk level. Efficiency is part of correctness.**

Before starting any expensive verification step (`PR-DEEP`, `FULL`, replay of a
large suite, extra independent review), answer both questions:

1. **What concrete risk does this step check?**
2. **What materially new evidence will it produce beyond evidence already valid?**

If question 2 has no meaningful answer, do not run the step.

Time on self-hosted runners, owner waiting time and AI/model usage are engineering
costs. Do not spend them merely to obtain a newer timestamp or a second copy of
the same proof.

## Default routing

| Change | Default verification |
|---|---|
| docs / Markdown / tracker metadata | cheap docs/native checks only; no code CI, PR-DEEP or FULL |
| small UI/config/test/refactor with bounded impact | focused local check(s) + repository-native PR fast lane |
| ordinary application/runtime code | focused local checks + `pr-fast`; let native policy decide whether escalation is required |
| auth/authz, financial/private data, migrations, destructive operations | relevant focused tests + high-risk governance; PR-DEEP only when native policy requires it or a concrete unresolved risk justifies it |
| CI/release/control-plane authority | high-risk governance and the exact authority checks activated by the change; avoid unrelated suites |
| formal production release/deploy | exact-main `FULL` release run because it creates/verifies the deployable artifact, manifests and provenance |

The table is a default, not permission to bypass a server-required check. GitHub
native gates remain authoritative for the exact PR they guard.

## PR-DEEP

`PR-DEEP` is an **escalation lane**, not a standard second phase of every PR.
The trusted selector/policy may require it for unsafe or broad backend changes
(for example control-plane/dependency/wiring trust surfaces, deletions, changed
dynamic-import surfaces, or affected-test fan-out above the fast-lane budget).

Do not manually dispatch PR-DEEP for docs, snapshots, normal UI work, small
refactors, or ordinary changes merely because a previous audit once used it.
Do not run a second PR-DEEP on unchanged candidate content.

## FULL

`FULL` is **not** a per-PR, per-merge or post-PR-DEEP ritual.

Run FULL only when it provides a distinct required output or proof, such as:

- a formal production release/deploy that needs the exact-main immutable release
  artifact and provenance;
- an explicitly chosen release/checkpoint certification;
- a material control-plane change whose unresolved correctness question genuinely
  depends on FULL lanes not already covered;
- unresolved cross-lane uncertainty demonstrated by evidence;
- an explicit owner request.

**Never chain `PR-DEEP -> merge -> FULL` by default.** If PR-DEEP has certified
the relevant candidate and no formal release is being produced, merge plus the
required post-merge policy checks is normally the end of that workstream.

## Evidence validity: SHA vs tree/content

Distinguish two concepts:

1. **Server status authority is SHA-bound.** A required GitHub status must refer
to the exact PR HEAD/base expected by the gate.
2. **Technical test evidence is content/scope-bound.** A new commit SHA does not
automatically make every previous test result technically worthless.

Rerun only evidence invalidated by a relevant code/tree/configuration/execution-
semantic change or required by an exact-SHA server gate.

After a merge commit, compare the resulting tree with the certified candidate
tree. If the merge tree is identical and the certified base did not drift,
there is no new application content to retest merely because the merge commit
has a different SHA. Run exact-main FULL only if a formal release artifact or
another distinct FULL proof is actually required.

## Failure handling

- No blind reruns.
- Diagnose job -> step -> log/artifact -> root cause.
- Fix the smallest demonstrated cause.
- Do not lower thresholds, broaden snapshots or weaken a gate only to make CI
  green.
- A rerun on unchanged content is allowed only when evidence shows a transient
  external failure and the rerun can materially distinguish that hypothesis.

## One bounded remediation cycle

For a failing PR:

1. identify the largest real blocker;
2. fix only that blocker;
3. run the smallest focused local check that can catch an immediate mistake;
4. push one bounded candidate;
5. let repository-native exact-head gates determine any required escalation;
6. stop when the requested outcome is proven.

Do not turn a small remediation into a new framework, tracker, audit or hardening
program.

## Planning and review proportionality

- Ordinary bounded work needs no execution plan document.
- Use a living plan only for genuinely substantial, multi-session, high-risk or
  coordination-heavy objectives.
- Independent critique/review is risk-based, not ceremonial.
- A verifier searches for material false completion; it does not manufacture
  unrelated follow-up work.

## Current authority and history

- `AGENTS.md` defines repository behavior and points here for verification cost.
- `docs/engineering/pr-fast-lane.md` documents the current fast/deep routing
  mechanism.
- `docs/adr/006-verified-runtime-delivery.md` governs **production promotion**
  from verified artifacts; it does not require a production release after every
  merge.
- GitHub Issues #159 and #226 (including #227-#236) are **completed historical
  audit evidence**. They must not be resumed as active programs unless the owner
  explicitly asks to revisit that history.

Default after a completed task is **return to product development**, not start a
new audit, certification cycle or speculative hardening stream.