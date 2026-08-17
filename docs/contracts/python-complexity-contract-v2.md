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
monotonic transition check that enforces these rules. PR-B1 does not
wire it into CI; PR-B3 will pass the PR-base / FIRST_PARENT contract
as `--previous-contract`.

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
  SHA-256 when not in a transition; PR-B3 will introduce a separate
  `comparison_base_sha` field once the comparison source is wired
  against PR base / FIRST_PARENT;
- `metrics` — production functions, complexity_proxy counts, max;
- `blocking_baseline` — recording the v2 gates at evaluation time;
- `entries_count` — number of locked entries in the contract;
- `violations` — schema/integrity/policy failures;
- `entry_violations` — per-function lock violations;
- `transition_violations` — monotonic transition failures
  (only when `--previous-contract` is supplied);
- `ratchet_candidate` — improvements that have not yet been tightened
  into the contract.

The `comparison_base_sha` field is **not yet present** in the
artifact: PR-B1 does not wire the comparison source. PR-B3 will add
it when the gate is wired against the PR base / FIRST_PARENT.

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

## Relation to PR-B2 (incremental gate)

PR-B2 will replace
[`scripts/check_changed_function_complexity.py`](../../scripts/check_changed_function_complexity.py)'s
inline scoring with calls into the same L1 module, and add the
`--no-renames` rename escape fix and the strict-improvement rule for
existing touched functions. It will not change the threshold for
new functions in PR-B1; that alignment (new-function maximum stays
at 19) is already enforced by the v2 contract.

PR-B2 will also use the L1 transition validator for the changed-line
gate.

## Relation to the size/length ratchet

`scripts/check_complexity_ratchet.py` tracks file and function
line-of-code (LOC) counts. That is a distinct domain: LOC is not
control-flow complexity, and the two gates are complementary, not
interchangeable.

The L1 module does NOT cover LOC. The size/length ratchet keeps its
own implementation. PR-B1 does not promote LOC to a strict blocker.

## Running locally

```bash
backend/venv/bin/python -I scripts/check_python_complexity_contract.py \
  --contract scripts/python-complexity-contract-v2.json \
  --evidence /tmp/python-complexity-contract-v2.json
```

Expected on exact main: `PASS`, rc 0. The evidence file is the
single artifact documented in PR-B1; it carries the L1 module
SHA-256, the algorithm descriptor, the contract payload SHA-256, the
production metrics, the limits, the violation list, and (if
applicable) the RATCHET_REQUIRED delta list.
