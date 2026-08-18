# Python Complexity Contract v2

This document describes the Python AST-complexity contract v2 introduced
by PR-B1. It is the authoritative source for the metric algorithm, the
contract shape, the ratchet semantics, and the relation to other gates.

PR-B1 ships one final semantic correction pass: the new-function
threshold is **derived from the contract** (no hardcoded `>= 20`), the
metric algorithm itself is **pinned by a structured descriptor** (not
only by the name string), the v2 boundary is **immutable at 19**, and
the legacy WP11 fields are **removed from active v2** (they remain in
the v1 history only).

## What `complexity_proxy` means

`complexity_proxy` is the per-function score produced by
[`scripts/_python_complexity.py`](../../scripts/_python_complexity.py)
(L1). It is a deterministic Python AST measurement that:

- starts at `1` for every counted function;
- adds `1` for each descendant AST node whose type name is in
  `COUNTED_NODES`;
- adds `max(1, len(values) - 1)` for each `ast.BoolOp` descendant.

## It is NOT textbook cyclomatic complexity

Cyclomatic complexity (McCabe) counts independent linear paths and is
typically computed over the entire module. `complexity_proxy` differs:

- it is computed per function;
- it uses a curated set of 13 control-flow node types
  (`If`, `For`, `AsyncFor`, `While`, `Try`, `TryStar`, `With`,
  `AsyncWith`, `IfExp`, `Assert`, `comprehension`, `Match`,
  `ExceptHandler`) instead of McCabe's branch operators;
- it walks nested function and class bodies with `ast.walk`, so a
  nested `if` contributes to the outer function's score. This is
  preserved intentionally; do not silently "fix" it in a future revision.

## Exact algorithm

```
score(node) = 1
for each descendant d in ast.walk(node):
    if type(d).__name__ in COUNTED_NODES:
        score += 1
    elif isinstance(d, ast.BoolOp):
        score += max(1, len(d.values) - 1)
return score
```

The set of counted node types is fixed at 13 names (`COUNTED_NODES`).
Any change to this set, the algorithm, or the walk semantics is a
breaking change for the contract and requires bumping the contract
version and re-baselining the entries.

## Algorithm pinning (PR-B1 final semantic correction)

L1 exposes an immutable algorithm descriptor:

| Symbol              | Value                                          |
|---------------------|------------------------------------------------|
| `ALGORITHM_NAME`    | `"python_complexity_proxy_v1"`                 |
| `ALGORITHM_VERSION` | `"1"`                                           |
| `algorithm_spec()`  | `{"initial_score": 1, "counted_nodes": [...], "bool_op": "max(1,len(values)-1)", "walk": "ast.walk_including_nested_bodies"}` |

Each v2 contract records the same values in `algorithm` plus the
SHA-256 of the L1 file as `implementation_sha256`. The runtime
checker:

1. computes the SHA-256 of `scripts/_python_complexity.py` and
   requires equality with `contract.algorithm.implementation_sha256`.
2. compares every field in `contract.algorithm` against the runtime
   L1's exposed descriptor. Any mismatch is a FAIL.
3. in a v2 -> v2 transition, requires the candidate's algorithm
   descriptor to be **exactly equal** to the previous descriptor.

This means the algorithm itself cannot be silently weakened by editing
`scripts/_python_complexity.py` while keeping the contract name — the
next contract will fail to validate, and the only legitimate path is
to introduce a new contract version (v3) and rebaseline.

## Current baseline (exact-main 76a71d9b)

Measured against the production tree at
`76a71d9bcf339385712ae1207824624af603a12f`:

| Metric                     | Value |
|----------------------------|-------|
| production_functions       | 2935  |
| complexity_proxy > 19      | 33    |
| complexity_proxy >= 30     | 3     |
| maximum_complexity_proxy   | 62    |
| new_function above 19      | 0     |

The three current `>= 30` hotspots are tracked as remediation entries:

| Path                                                              | Function                       | current | target |
|-------------------------------------------------------------------|--------------------------------|---------|--------|
| `backend/services/target_calculator/export.py`                    | `build_target_excel`           | 62      | 29     |
| `backend/services/target_calculator/profitability.py`              | `populate_profitability`       | 49      | 29     |
| `backend/services/target_calculator/export.py`                    | `manager_allocation_analysis`  | 32      | 29     |

## Current blocking ratchet

`scripts/python-complexity-contract-v2.json` records:

| Limit                                            | Value | Meaning                                          |
|--------------------------------------------------|-------|--------------------------------------------------|
| `complexity_proxy_gte_20_maximum`                | 33    | total functions with cp > 19 may not exceed 33   |
| `complexity_proxy_gte_30_maximum`                | 3     | total functions with cp >= 30 may not exceed 3   |
| `maximum_complexity_proxy`                       | 62    | the largest single function cp may not exceed 62 |
| `new_function_complexity_proxy_maximum`         | 19    | a function not in `entries` may not exceed cp 19 (i.e., may not reach cp >= 20) |

The new-function threshold is **pinned at 19** for v2. Both values
above 19 (would loosen) and below 19 (would tighten) are rejected by
the v2 -> v2 transition validator. Changing the boundary requires
v3 / rebaseline.

Per-function ceilings in `entries[]` pin each current `> 19` identity
at its exact-main complexity. A regression of any entry above its
ceiling is a FAIL.

The v2 contract deliberately omits the legacy v1 fields
`wp11_locked_entries_maximum` and `mandatory_locked_gte_30_maximum`.
Their existence was historical-only; v2 entries do not carry the v1
flags that defined those concepts, and the active v2 checker does not
compute them. They remain in the `history.v1` block for evidentiary
purposes only.

## Future target

Informational, not blocking. Recorded in `future_target`:

| Target                                 | Value |
|----------------------------------------|-------|
| `complexity_proxy_gte_20_target`       | 33    |
| `complexity_proxy_gte_30_target`       | 0     |
| `maximum_complexity_proxy_target`      | 29    |
| `no_new_function_above_19`             | true  |

The future target does not raise any limit automatically. Improvements
move toward these numbers through explicit contract updates in PRs
that achieve them.

## Result semantics

`scripts/check_python_complexity_contract.py` returns one of three
results, mapped to exit codes:

| Result              | rc | | When |
|---------------------|----|-|------|
| `PASS`              | 0  | | All checks pass and current code matches or equals the contract baseline. |
| `FAIL`              | 1  | | Any safety/policy violation: contract integrity, schema, aggregate limit exceeded, locked entry exceeded, monotonic transition rejection, algorithm descriptor mismatch, or invalid contract. |
| `RATCHET_REQUIRED`  | 2  | | Current code is strictly better than the recorded contract AND the contract has not been tightened to capture the improvement. |

Precedence:

1. any safety/policy violation => FAIL;
2. otherwise, if current code strictly better than contract => RATCHET_REQUIRED;
3. otherwise => PASS.

## Why improvements require explicit contract tightening

RATCHET_REQUIRED is emitted when the contract is loose relative to the
current tree. This is intentional: it forces the author of an
improving PR to capture the improvement in the same PR (by lowering
a ceiling or limit in the contract). Otherwise, a future PR could
regress to the looser contract ceiling without ever being caught. The
contract never auto-edits; every change is an explicit Git commit.

## Why contract transitions cannot weaken

A self-hash is necessary but not sufficient. A future PR must not be
able to:

- raise an aggregate ceiling (`gte_20_maximum`, `gte_30_maximum`,
  `maximum_complexity_proxy`);
- change the new-function threshold (must stay pinned at 19 in v2 -
  both `19 -> 20` and `19 -> 18` are rejected);
- raise a per-function ceiling;
- rewrite or remove a historical record;
- remove a locked entry while the function still exists and is >
  new_function_threshold;
- introduce a new entry whose function is currently >
  new_function_threshold but was not in the previous locked set
  (candidate-identity laundering);
- modify the algorithm descriptor (counted nodes, bool_op, walk,
  initial_score, name, implementation_sha256) in a v2 -> v2 transition.

The `--previous-contract <path>` flag activates a pure, testable
monotonic transition check that enforces these rules. PR-B3 wires it
into CI on both `pull_request` (PR base SHA) and `workflow_dispatch`
exact-main (FIRST_PARENT of `github.sha`).

The `--comparison-base-sha <40 lowercase hex>` flag is REQUIRED when
`--previous-contract` is supplied, and is forbidden without it. The
value is the trusted SHA from which the previous contract bytes were
materialized (`git show "$BASE:scripts/python-complexity-contract-v2.json"`).
The CLI rejects non-hex, non-40-char, or uppercase inputs with rc 1.

Tightening is always allowed: lower aggregate ceilings, lower
per-function ceilings, and removal of a locked entry whose function
has dropped below the new-function threshold (an improvement) all PASS
the validator.

## Evidence artifact

The checker writes a single JSON artifact via `--evidence <path>`. The
artifact contains:

- `source_sha` — current `git rev-parse HEAD`;
- `event_name` — logical event name (e.g., `pull_request`);
- `algorithm` — the full descriptor block (name, implementation
  SHA-256, initial_score, counted_nodes, bool_op, walk);
- `algorithm_runtime_match` — `true` iff the runtime L1 matches the
  contract;
- `contract_payload_sha256` — SHA-256 of the contract payload;
- `contract_source_sha` — the exact-main SHA pinned by the contract;
- `contract_version` — `2`;
- `previous_contract_payload_sha256` — SHA-256 of the previous
  contract when supplied, otherwise `null`;
- `candidate_contract_payload_sha256` — same as the contract payload
  SHA-256 when not in a transition;
- `comparison_base_sha` — the trusted SHA from which `previous_contract`
  was fetched (PR base or FIRST_PARENT). `null` when no previous
  contract was supplied;
- `metrics` — production functions, complexity_proxy counts, max;
- `blocking_baseline` — recording the v2 gates at evaluation time;
- `entries_count` — number of locked entries in the contract;
- `violations` — schema/integrity/policy failures (now also includes
  previous-contract base-integrity violations: schema failures and
  self-hash mismatches);
- `entry_violations` — per-function lock violations;
- `transition_violations` — monotonic transition failures
  (only when `--previous-contract` is supplied);
- `ratchet_candidate` — improvements that have not yet been tightened
  into the contract.

The `comparison_base_sha` field is emitted whenever `--comparison-base-sha`
is supplied (which is required whenever `--previous-contract` is supplied).
Its value is the trusted source SHA; it is **not** a second digest and
must not be confused with `previous_contract_payload_sha256`.

## v1 historical preservation

`scripts/python-complexity-contract-v1.json` is preserved verbatim.
PR-B1 does not edit it. The v2 contract records v1 history in its
`history.v1` block (version, baseline source SHA, baseline metrics,
release_b_gates, entry count) so a future PR can refer to the
pre-v2 state without reaching for the v1 file. The historical v1
`release_b_gates` retain their legacy WP11 fields
(`wp11_locked_entries_maximum: 19`) as evidence of the strategic
intent at the time v1 was authored; those fields are intentionally
absent from active v2.

The v1 contract's `release_b_gates` reflect the strategic intent at
the time it was authored (`gte_30_maximum: 0`, `maximum_complexity: 29`,
`gte_20_maximum: 54`). These were targets, not achieved state. The v2
contract's `release_b_gates` reflect what exact main actually
achieves, so that v2 PASSES against current main and ratchets
forward only by explicit tightening.

## Authority hierarchy

PR-B3 documents the three-tier complexity authority. The three scripts
remain in the repository; only their role is clarified.

| Tier | Script | Role | CI surface |
|------|--------|------|------------|
| 1. Authoritative full-tree AST invariant | `scripts/check_python_complexity_contract.py` | The contract itself: aggregate ceilings, per-function ceilings, new-function threshold (pinned at 19), transition rules A–H, algorithm pinning | **Real CI gate** on both PR (`pull_request`) and exact-main (`workflow_dispatch` + `refs/heads/main`). Wired with `--previous-contract` + `--comparison-base-sha` so the v2 → v2 transition rules run. |
| 2. Incremental PR precheck | `scripts/check_changed_function_complexity.py` | Per-PR changed-function hotspots (consumes `scripts/_python_complexity.py`) | PR-fast + exact-main on. PR-B2 already migrated this gate to the shared L1 module so the AST metric implementation lives in exactly one file. |
| 3. Size/length control | `scripts/check_complexity_ratchet.py` | File and function line-of-code (LOC), not control-flow complexity | pr-fast + exact-main on. Kept as a complementary domain; not replaced. |

PR-B2 already consumed the L1 module into the changed-function gate.
That is the reconciliation of overlapping AST authority; PR-B3 makes
the three tiers explicit in this document.

All seven files
(`scripts/check_python_complexity_contract.py`,
`scripts/_python_complexity.py`,
`scripts/python-complexity-contract-v2.json`,
`scripts/check_changed_function_complexity.py`,
`scripts/check_changed_line_coverage.py`,
`scripts/check_complexity_ratchet.py`,
`scripts/complexity-ratchet.json`)
are listed under the `deploy-release-ci` category in
`.github/governance/high-risk-paths.json` (PR-B3 addition). PRs that
edit any of them trigger the existing A3 trusted-base governance
review. This is **not** cryptographic tamper protection; it is the
current operating model of sole-owner / trusted same-repo PRs made
explicit.

## Tracker closure status after PR-B3

PR-B3 closes (when its exact-main CI is green on the new wiring):

- **B1** — v2 contract gate is now a real blocking CI authority on both
  PR and exact-main.
- **B2** — three-tier authority is documented and the only overlapping
  AST implementations share L1.
- **B4** — `test-results/closure/<sha>/release-b/python-complexity-contract-v2.json`
  is uploaded on both PR and exact-main (14-day retention).

PR-B3 does **not** close:

- **B3** — backend changed-line coverage on PR remains blocked by the
  absence of a trustworthy <15-minute test selection. PR-B3 restores
  the **promotion-path** half (workflow_dispatch exact-main now runs
  the gate) but the **PR lane** for backend is still a separate task.
- **E2** — unchanged-line diff coverage on PR remains open for the
  same reason.

## Previous-contract integrity (PR-B3)

When `--previous-contract` is supplied, the evaluator first runs
`_validate_previous_contract_integrity(previous)` BEFORE the
transition validator. The helper reuses `_validate_schema(...)` with
`check_threshold=True` for structural authority (the rules live in one
place; no duplication) so the v2 threshold invariant is enforced on the
trusted-base contract too. The helper additionally checks that the
self-hash is present and matches the payload:

- `contract_payload_sha256` is present and matches
  `_canonical_sha256(_contract_payload(previous))`.

The v2 threshold invariant (`new_function_complexity_proxy_maximum`
must equal 19) is enforced on **both** the candidate (initial contracts)
and the previous contract (every transition). A previous contract with
an off-threshold value is rejected as a base-integrity failure BEFORE
any transition rule runs.

The helper does **not** validate the previous contract's algorithm
descriptor against the **current** runtime L1. That responsibility
belongs to the candidate's `algorithm_runtime_match` (current runtime
pin) and to transition Rule E (candidate.algorithm == previous.algorithm).
Validating the previous against the current L1 would make a future L1
bump — which is intended to fail Rule E and force a v3 contract —
impossible to detect cleanly.

## Relation to PR-B2 (incremental gate)

PR-B2 already replaced
[`scripts/check_changed_function_complexity.py`](../../scripts/check_changed_function_complexity.py)'s
inline scoring with calls into the same L1 module
[`scripts/_python_complexity.py`](../../scripts/_python_complexity.py)
and added the `--no-renames` rename-escape fix and the
strict-improvement rule for existing touched functions. PR-B2 did not
change the threshold for new functions in PR-B1; that alignment
(new-function maximum stays at 19) is already enforced by the v2
contract above.

PR-B2 also added the `scripts/check_changed_line_coverage.py`
gate as a separate coverage-domain gate with its own active-coverage-lane
semantics, fail-closed missing/malformed report rules, and `--no-renames`
rename safety. **This coverage gate does NOT consume the Python
complexity L1 implementation.** It is a coverage-domain gate, not an
AST-domain gate, and it has its own parser (coverage.py JSON / LCOV).
The single-source-of-truth AST algorithm remains
`scripts/_python_complexity.py`, consumed only by the contract
checker (tier 1) and by the changed-function precheck (tier 2).

In the authority hierarchy above:

- The authoritative full-tree AST invariant remains
  `scripts/check_python_complexity_contract.py` with the v2 contract
  threshold pinned at 19.
- The incremental per-PR precheck remains
  `scripts/check_changed_function_complexity.py`, now consuming the
  shared L1 module and using its CURRENT `--maximum 20` semantics.
- `scripts/check_changed_line_coverage.py` remains a separate
  coverage-domain gate that does not participate in the complexity
  authority hierarchy.

No threshold, no algorithm, and no policy is altered by this
clarification; it merely describes the post-PR-B2 state accurately.

## Relation to the size/length ratchet

`scripts/check_complexity_ratchet.py` tracks file and function
line-of-code (LOC) counts. That is a distinct domain: LOC is not
control-flow complexity, and the two gates are complementary, not
interchangeable.

The L1 module does NOT cover LOC. The size/length ratchet keeps its
own implementation. PR-B1 does not promote LOC to a strict blocker.

## Running locally

Without previous contract (PR-B1 behavior):

```bash
backend/venv/bin/python -I scripts/check_python_complexity_contract.py \
  --contract scripts/python-complexity-contract-v2.json \
  --evidence /tmp/python-complexity-contract-v2.json
```

With previous contract (PR-B3 wired path; both flags required together):

```bash
PREV="$(mktemp)"
git show "$COMPARISON_BASE_SHA:scripts/python-complexity-contract-v2.json" >"$PREV"
backend/venv/bin/python -I scripts/check_python_complexity_contract.py \
  --contract scripts/python-complexity-contract-v2.json \
  --previous-contract "$PREV" \
  --comparison-base-sha "$COMPARISON_BASE_SHA" \
  --event-name pull_request \
  --evidence /tmp/python-complexity-contract-v2.json
```

Expected on exact main: `PASS`, rc 0. The evidence file is the
single artifact documented in PR-B1; it carries the L1 module
SHA-256, the algorithm descriptor, the contract payload SHA-256, the
comparison base SHA, the production metrics, the limits, the violation
list, and (if applicable) the RATCHET_REQUIRED delta list.
