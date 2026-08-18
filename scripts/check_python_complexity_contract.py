#!/usr/bin/env python3
"""Verify the monotonic Python AST-complexity contract v2.

PR-B1 introduces:
  - import of the shared metric from scripts/_python_complexity.py via
    importlib.util.spec_from_file_location (works under `python -I`,
    independent of cwd, no sys.path pollution, exact trusted sibling path);
  - PASS / FAIL / RATCHET_REQUIRED semantics with rc 0/1/2;
  - an optional --previous-contract <path> flag that activates a
    pure, testable monotonic transition validator covering every rule
    the reviewer enumerated (aggregate ceilings, per-function ceilings,
    new-function threshold pinned at 19, history append-only,
    locked-entry survival, candidate-identity laundering, and
    algorithm descriptor exact-equality).

PR-B1 final semantic correction (this revision):

  - The new-function threshold is derived from the contract
    (``new_function_complexity_proxy_maximum``); the evaluator does
    not hardcode ``>= 20``. The v2 contract pins this value at 19.
  - The contract algorithm is pinned via a structured descriptor
    (``algorithm.name``, ``implementation_sha256``, ``initial_score``,
    ``counted_nodes``, ``bool_op``, ``walk``). The runtime computes the
    SHA-256 of the L1 file and rejects any mismatch. The v2 -> v2
    transition validator requires the candidate algorithm descriptor
    to be exactly equal to the previous one.
  - The v2 transition validator rejects both ``19 -> 20`` (loosen) and
    ``19 -> 18`` (would require rebaseline). The v2 boundary is
    immutable at 19.
  - Schema validation fails closed on duplicate locked identities,
    malformed entries (missing path/function/ceiling/current_complexity)
    and duplicate remediation identities.
  - The legacy WP11 fields (``wp11_locked_entries_maximum`` and
    ``mandatory_locked_gte_30_maximum``) are removed from the active
    v2 contract. They remain in the historical v1 history block only.

Failures fall into three categories:
  FAIL (rc 1)              any safety/policy violation
  RATCHET_REQUIRED (rc 2)  current code strictly better than contract
                           but contract has not been tightened
  PASS (rc 0)              all checks pass

PR-B1 keeps the --evidence <path> argument and writes a single JSON
artifact there for downstream consumption. The artifact follows the
schema described in docs/contracts/python-complexity-contract-v2.md.

This script does NOT auto-edit the contract file. Contract changes
must be explicit Git changes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
L1_PATH = Path(__file__).with_name("_python_complexity.py")
DEFAULT_CONTRACT = Path(__file__).with_name("python-complexity-contract-v2.json")
_L1_MODNAME = "_unihub_python_complexity_l1"

# v2 invariant: the new-function threshold is pinned at 19. Any change
# requires a contract version bump and an explicit rebaseline.
V2_NEW_FUNCTION_THRESHOLD: int = 19


# ---------------------------------------------------------------------------
# L1 loading
# ---------------------------------------------------------------------------


class L1LoadError(RuntimeError):
    """Raised when L1 cannot be loaded. The check fails closed."""


def _load_l1() -> Any:
    """Load scripts/_python_complexity.py via importlib.

    Uses Path(__file__).with_name(...) so the trusted sibling is
    resolved regardless of cwd. The module is registered under a fixed
    private name in sys.modules before exec_module so dataclasses can
    resolve its module metadata. On any loader exception the temporary
    entry is removed and the exception is re-raised.
    """
    if not L1_PATH.is_file():
        raise L1LoadError(f"L1 module not found at {L1_PATH}")
    spec = importlib.util.spec_from_file_location(_L1_MODNAME, str(L1_PATH))
    if spec is None or spec.loader is None:
        raise L1LoadError(f"could not build import spec for {L1_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_L1_MODNAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_L1_MODNAME, None)
        raise
    required = {
        "ALGORITHM_NAME",
        "ALGORITHM_VERSION",
        "COUNTED_NODES",
        "FunctionMetric",
        "algorithm_spec",
        "collect_metrics",
        "function_metrics",
        "score",
    }
    missing = required - set(dir(module))
    if missing:
        sys.modules.pop(_L1_MODNAME, None)
        raise L1LoadError(f"L1 missing required names: {sorted(missing)}")
    return module


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git_sha(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _contract_payload(contract: dict) -> dict:
    return {k: v for k, v in contract.items() if k != "contract_payload_sha256"}


# ---------------------------------------------------------------------------
# Algorithm pinning (PR-B1 final semantic correction)
# ---------------------------------------------------------------------------


def _l1_file_sha256() -> str:
    """SHA-256 of the L1 file bytes, exactly as on disk."""
    return hashlib.sha256(L1_PATH.read_bytes()).hexdigest()


def _runtime_algorithm_descriptor(l1: Any) -> dict:
    """Collect the runtime algorithm descriptor from L1.

    Returns the data the contract must mirror. The dict is intentionally
    plain (json-friendly) so a deep equality check is trivial.
    """
    spec = l1.algorithm_spec()
    return {
        "name": str(l1.ALGORITHM_NAME),
        "implementation_sha256": _l1_file_sha256(),
        "initial_score": int(spec["initial_score"]),
        "counted_nodes": list(spec["counted_nodes"]),
        "bool_op": str(spec["bool_op"]),
        "walk": str(spec["walk"]),
    }


def _validate_algorithm_pin(contract: dict, l1: Any) -> list:
    """Pure validation: contract.algorithm must match the L1 module.

    Returns a list of human-readable violation strings. Empty list means
    the algorithm is pinned correctly.
    """
    out: list = []
    algo = contract.get("algorithm")
    if not isinstance(algo, dict):
        return ["algorithm descriptor must be an object"]

    expected = _runtime_algorithm_descriptor(l1)

    # Required fields must be present.
    for field in (
        "name",
        "implementation_sha256",
        "initial_score",
        "counted_nodes",
        "bool_op",
        "walk",
    ):
        if field not in algo:
            out.append(f"algorithm.{field} missing")

    if out:
        return out

    # Field-by-field equality:
    if str(algo["name"]) != expected["name"]:
        out.append(
            f"algorithm.name mismatch (expected {expected['name']!r}, got {algo['name']!r})"
        )
    if str(algo["implementation_sha256"]) != expected["implementation_sha256"]:
        out.append(
            "algorithm.implementation_sha256 mismatch with runtime L1"
            f" (expected {expected['implementation_sha256']}, got {algo['implementation_sha256']})"
        )
    if int(algo["initial_score"]) != expected["initial_score"]:
        out.append(
            f"algorithm.initial_score mismatch (expected {expected['initial_score']}, got {algo['initial_score']})"
        )
    if list(algo["counted_nodes"]) != expected["counted_nodes"]:
        out.append(
            f"algorithm.counted_nodes mismatch (expected {expected['counted_nodes']}, got {algo['counted_nodes']})"
        )
    if str(algo["bool_op"]) != expected["bool_op"]:
        out.append(
            f"algorithm.bool_op mismatch (expected {expected['bool_op']!r}, got {algo['bool_op']!r})"
        )
    if str(algo["walk"]) != expected["walk"]:
        out.append(
            f"algorithm.walk mismatch (expected {expected['walk']!r}, got {algo['walk']!r})"
        )
    return out


def _algorithm_descriptor_equal(a: dict, b: dict) -> bool:
    """Deep equality for the algorithm descriptor block.

    Used by the v2 -> v2 transition validator. Both inputs are pulled
    from the contract, so they are already JSON-serializable.
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    return _canonical_sha256(a) == _canonical_sha256(b)


# ---------------------------------------------------------------------------
# Schema / structural validation (fail-closed)
# ---------------------------------------------------------------------------


def _validate_schema(contract: dict, *, check_threshold: bool = True) -> list:
    """Pure validation: the contract must be a well-formed v2 contract.

    Returns a list of human-readable violation strings. Empty list means
    the contract is structurally valid.

    Reused by `_validate_previous_contract_integrity` for the previous
    (trusted-base) contract so the structural authority lives in one
    place. For the previous contract, callers pass
    ``check_threshold=False`` so the threshold rule is enforced by the
    transition validator (Rule B), not here.

    Strictly rejects:
      - unsupported version
      - duplicate locked identities (path, function)
      - malformed entries missing path/function/ceiling/current_complexity
      - duplicate remediation identities (path, function)
      - the legacy WP11 fields in active v2 release_b_gates
      - new_function_complexity_proxy_maximum != 19 (only when
        ``check_threshold`` is True, i.e., for initial contracts).

    The threshold check is opt-in so the v2 -> v2 transition validator
    can produce the more specific "new-function threshold N is not pinned
    at 19" message when a previous contract is provided.
    """
    out: list = []

    if contract.get("version") != 2:
        out.append(f"unsupported contract version: {contract.get('version')!r}")

    gates = contract.get("release_b_gates")
    if not isinstance(gates, dict):
        out.append("release_b_gates must be a dict")
    else:
        # Required v2 limits.
        for required in (
            "complexity_proxy_gte_20_maximum",
            "complexity_proxy_gte_30_maximum",
            "maximum_complexity_proxy",
            "new_function_complexity_proxy_maximum",
        ):
            if required not in gates:
                out.append(f"release_b_gates.{required} missing")

        # PR-B1 final semantic correction: active v2 must NOT carry the
        # legacy WP11 fields. They are historical-only.
        for legacy in ("wp11_locked_entries_maximum", "mandatory_locked_gte_30_maximum"):
            if legacy in gates:
                out.append(
                    f"release_b_gates.{legacy} is a legacy v1 field and must not appear in active v2"
                )

        # The v2 boundary is pinned at 19. Any other initial value is
        # rejected to keep the contract unambiguous. Skipped for v2 ->
        # v2 transitions so the transition validator can produce its
        # specific "not pinned at 19" message.
        if check_threshold and "new_function_complexity_proxy_maximum" in gates:
            try:
                nft = int(gates["new_function_complexity_proxy_maximum"])
            except (TypeError, ValueError):
                out.append("release_b_gates.new_function_complexity_proxy_maximum must be an integer")
            else:
                if nft != V2_NEW_FUNCTION_THRESHOLD:
                    out.append(
                        f"release_b_gates.new_function_complexity_proxy_maximum must be {V2_NEW_FUNCTION_THRESHOLD}"
                        f" (got {nft})"
                    )

    entries = contract.get("entries")
    if not isinstance(entries, list):
        out.append("entries must be a list")
    else:
        seen_locked: set = set()
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                out.append(f"entries[{idx}] must be an object")
                continue
            path = entry.get("path")
            function = entry.get("function")
            if not isinstance(path, str) or not path:
                out.append(f"entries[{idx}].path missing or empty")
                continue
            if not isinstance(function, str) or not function:
                out.append(f"entries[{idx}].function missing or empty")
                continue
            if not ("ceiling" in entry or "current_complexity" in entry):
                out.append(
                    f"entries[{idx}] ({path}::{function}) missing ceiling/current_complexity"
                )
                continue
            identity = (path, function)
            if identity in seen_locked:
                out.append(
                    f"duplicate locked entry identity: {path}::{function}"
                )
            seen_locked.add(identity)

    remediation_entries = contract.get("remediation_entries")
    if remediation_entries is not None:
        if not isinstance(remediation_entries, list):
            out.append("remediation_entries must be a list when present")
        else:
            seen_remediation: set = set()
            for idx, entry in enumerate(remediation_entries):
                if not isinstance(entry, dict):
                    out.append(f"remediation_entries[{idx}] must be an object")
                    continue
                path = entry.get("path")
                function = entry.get("function")
                if not isinstance(path, str) or not path:
                    out.append(f"remediation_entries[{idx}].path missing or empty")
                    continue
                if not isinstance(function, str) or not function:
                    out.append(f"remediation_entries[{idx}].function missing or empty")
                    continue
                identity = (path, function)
                if identity in seen_remediation:
                    out.append(
                        f"duplicate remediation entry identity: {path}::{function}"
                    )
                seen_remediation.add(identity)

    return out


# ---------------------------------------------------------------------------
# Per-function metric collection using L1
# ---------------------------------------------------------------------------


def _collect_metrics(root: Path, l1: Any) -> list:
    return list(l1.collect_metrics(root))


def _entries_by_identity(entries: list) -> dict:
    return {
        (str(e["path"]), str(e["function"])): e
        for e in entries
        if isinstance(e, dict) and "path" in e and "function" in e
    }


# ---------------------------------------------------------------------------
# Previous-contract integrity validation (PR-B3)
# ---------------------------------------------------------------------------
#
# The previous (trusted-base) contract is read from a fixed base SHA. It
# is the input to the v2 -> v2 transition validator and a tampering
# vector for a malicious PR. Before any transition rule runs, the
# previous contract must prove it is a well-formed v2 contract whose
# self-hash matches the embedded digest.
#
# Implementation rule: reuse `_validate_schema` for structural
# authority (do NOT duplicate schema semantics). The threshold check
# is enabled (check_threshold=True) so a previous contract with an
# invalid v2 threshold is rejected as a base-integrity failure
# BEFORE the transition validator runs; the trusted previous must
# itself be a valid v2 contract. Algorithm pin against the *current*
# runtime L1 is intentionally NOT checked here; the candidate's
# `algorithm_runtime_match` validates against the current runtime, and
# transition Rule E enforces candidate.algorithm == previous.algorithm.
# Validating the previous contract's algorithm against the current L1
# would make a future L1 bump (which is meant to fail Rule E and force
# a v3 contract) impossible to detect cleanly.


def _validate_previous_contract_integrity(previous: Any) -> list:
    """Pure validation: previous contract must be a well-formed v2 contract
    with a matching self-hash.

    Returns a list of human-readable violation strings. Empty list means
    the previous contract is structurally valid (including the v2
    threshold invariant) and self-consistent.

    Structural rules are delegated to ``_validate_schema`` with
    ``check_threshold=True`` so a previous contract that violates the
    v2 threshold invariant fails base integrity before any transition
    rule runs. The self-hash rule is local because no other component
    needs it.
    """
    out: list = []
    if not isinstance(previous, dict):
        out.append("previous contract must be a JSON object")
        return out

    out.extend(_validate_schema(previous, check_threshold=True))

    expected = previous.get("contract_payload_sha256")
    if not isinstance(expected, str) or not expected:
        out.append("previous contract payload digest missing")
    else:
        actual = _canonical_sha256(_contract_payload(previous))
        if actual != expected:
            out.append(
                "previous contract payload digest mismatch "
                f"(expected {expected}, got {actual})"
            )

    return out


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _validate_comparison_base_sha(value: Any) -> tuple[str | None, str | None]:
    """Validate the comparison-base-sha CLI value.

    Returns ``(sha, None)`` on a clean 40-char lowercase hex input, or
    ``(None, error)`` otherwise. ``sha`` is the normalized value (which
    is the input string because the regex constrains shape) and
    ``error`` is a human-readable violation string.
    """
    if value is None:
        return None, "comparison-base-sha must not be empty"
    if not isinstance(value, str):
        return None, (
            f"comparison-base-sha must be a string (got {type(value).__name__})"
        )
    if not _SHA_RE.match(value):
        return None, (
            f"comparison-base-sha must match ^[0-9a-f]{{40}}$ (got {value!r})"
        )
    return value, None


# ---------------------------------------------------------------------------
# Transition validator (PR-B1 final semantic correction)
# ---------------------------------------------------------------------------


def _validate_transition(
    candidate: dict,
    previous: dict,
    current_metrics: list,
) -> list:
    """Pure, testable monotonic transition validator.

    Rules (per reviewer enumeration):
      A.  aggregate blocking ceilings cannot increase
          (gte_20_maximum, gte_30_maximum, maximum_complexity_proxy).
      B.  new-function threshold must stay pinned at 19 in v2.
          Both 19 -> 20 and 19 -> 18 are rejected.
      C.  per-function ceiling cannot increase.
      D.  history is append-only (cannot remove or overwrite records).
      E.  algorithm descriptor must be exactly equal across v2 -> v2.
      F.  locked identity cannot disappear merely to legitimize current
          complexity. A previously locked function that still exists in
          the current tree and is still >= new_function_threshold+1 cannot
          be silently removed.
      G.  candidate contract contents cannot redefine history. Adding a
          new entry whose (path, function) is not in the previous locked
          set AND that function is currently > new_function_threshold is
          treated as a laundering attempt and rejected.
      H.  a previously locked function may disappear from active entries
          only if the current measurement proves it has been deleted or
          has dropped below the new-function threshold. That is
          improvement.

    Returns a list of human-readable violation strings. Empty list means
    the transition is monotonic.
    """
    out: list = []
    cand_gates = candidate.get("release_b_gates", {}) or {}
    prev_gates = previous.get("release_b_gates", {}) or {}

    # Rule A: aggregate ceilings cannot increase (active v2 keys only).
    for key in (
        "complexity_proxy_gte_20_maximum",
        "complexity_proxy_gte_30_maximum",
        "maximum_complexity_proxy",
    ):
        if key in prev_gates and key in cand_gates:
            prev_v = int(prev_gates[key])
            cand_v = int(cand_gates[key])
            if cand_v > prev_v:
                out.append(
                    f"aggregate ceiling {key} {cand_v} > previous {prev_v}"
                )

    # Rule B: v2 boundary is pinned at 19. Both directions are rejected.
    prev_nf = prev_gates.get("new_function_complexity_proxy_maximum")
    cand_nf = cand_gates.get("new_function_complexity_proxy_maximum")
    if prev_nf is not None and cand_nf is not None:
        prev_nf_i = int(prev_nf)
        cand_nf_i = int(cand_nf)
        if cand_nf_i != V2_NEW_FUNCTION_THRESHOLD:
            out.append(
                f"new-function threshold {cand_nf_i} is not pinned at {V2_NEW_FUNCTION_THRESHOLD}"
            )
        elif cand_nf_i != prev_nf_i:
            out.append(
                f"new-function threshold {cand_nf_i} != previous {prev_nf_i}"
            )

    cand_entries = _entries_by_identity(candidate.get("entries", []) or [])
    prev_entries = _entries_by_identity(previous.get("entries", []) or [])

    # Rule C: per-function ceiling cannot increase.
    for identity, prev_entry in prev_entries.items():
        cand_entry = cand_entries.get(identity)
        if cand_entry is None:
            continue  # covered by Rule F
        prev_ceil = int(prev_entry.get("ceiling", prev_entry.get("current_complexity", 0)))
        cand_ceil = int(cand_entry.get("ceiling", cand_entry.get("current_complexity", 0)))
        if cand_ceil > prev_ceil:
            out.append(
                f"per-function ceiling {identity[0]}::{identity[1]} {cand_ceil} > previous {prev_ceil}"
            )

    # Rule D: history append-only.
    prev_history = previous.get("history", {}) or {}
    cand_history = candidate.get("history", {}) or {}
    prev_history_keys = set(prev_history.keys())
    cand_history_keys = set(cand_history.keys())
    removed = prev_history_keys - cand_history_keys
    for k in removed:
        out.append(f"history record {k!r} removed")
    for k in prev_history_keys & cand_history_keys:
        if prev_history[k] != cand_history[k]:
            out.append(f"history record {k!r} overwritten")

    # Rule E: algorithm descriptor must be exactly equal.
    cand_algo = candidate.get("algorithm")
    prev_algo = previous.get("algorithm")
    if not _algorithm_descriptor_equal(cand_algo, prev_algo):
        out.append("algorithm descriptor changed between v2 contracts")

    # Rule F: locked identity disappearance while still > new_function_threshold.
    new_function_threshold = int(cand_gates.get(
        "new_function_complexity_proxy_maximum", V2_NEW_FUNCTION_THRESHOLD
    ))
    by_identity = {(m.path, m.function): m for m in current_metrics}
    for identity, prev_entry in prev_entries.items():
        if identity in cand_entries:
            continue
        cur = by_identity.get(identity)
        if cur is None:
            continue  # function was deleted from the tree; allowed.
        if cur.complexity_proxy > new_function_threshold:
            out.append(
                f"locked entry {identity[0]}::{identity[1]} removed"
                f" but current complexity {cur.complexity_proxy} > new_function_threshold {new_function_threshold}"
            )

    # Rule G: candidate identity laundering.
    prev_identities = set(prev_entries.keys())
    for identity, cand_entry in cand_entries.items():
        if identity in prev_identities:
            continue
        cur = by_identity.get(identity)
        if cur is None:
            continue
        if cur.complexity_proxy > new_function_threshold:
            out.append(
                f"candidate identity laundering: new entry"
                f" {identity[0]}::{identity[1]} covers function currently"
                f" at complexity {cur.complexity_proxy} but was not in the"
                f" previous locked set"
            )

    return out


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _result(
    *,
    status: str,
    source_sha,
    contract_sha: str,
    candidate_sha,
    previous_sha,
    event_name: str,
    metrics_summary: dict,
    limits: dict,
    violations: list,
    ratchet_deltas: list,
    transition_violations: list,
    new_gte_threshold: list,
    entry_violations: list,
    entries_count: int,
    gte_threshold_count: int,
    gte_30_count: int,
    maximum_complexity: int,
    l1_module_sha256: str,
    algorithm_runtime_match: bool,
    contract_version,
    contract_source_sha,
    production_functions: int,
    algorithm_descriptor: dict,
    comparison_base_sha: str | None,
) -> dict:
    return {
        "schema": "unihub.python_complexity_contract_v2/v1",
        "result": status,
        "source_sha": source_sha,
        "event_name": event_name,
        "algorithm": {
            "name": algorithm_descriptor.get("name"),
            "implementation_sha256": algorithm_descriptor.get("implementation_sha256"),
            "initial_score": algorithm_descriptor.get("initial_score"),
            "counted_nodes": list(algorithm_descriptor.get("counted_nodes", [])),
            "bool_op": algorithm_descriptor.get("bool_op"),
            "walk": algorithm_descriptor.get("walk"),
        },
        "algorithm_runtime_match": algorithm_runtime_match,
        "contract_payload_sha256": contract_sha,
        "contract_source_sha": contract_source_sha,
        "contract_version": contract_version,
        "previous_contract_payload_sha256": previous_sha,
        "candidate_contract_payload_sha256": candidate_sha,
        "comparison_base_sha": comparison_base_sha,
        "metrics": {
            "production_functions": production_functions,
            "complexity_proxy_gte_threshold": gte_threshold_count,
            "complexity_proxy_gte_30": gte_30_count,
            "maximum_complexity_proxy": maximum_complexity,
            "new_function_above_threshold": len(new_gte_threshold),
        },
        "blocking_baseline": limits,
        "entries_count": entries_count,
        "violations": violations,
        "ratchet_candidate": ratchet_deltas,
        "transition_violations": transition_violations,
        "entry_violations": entry_violations,
        "metrics_summary": metrics_summary,
    }


def evaluate(
    root: Path,
    contract: dict,
    l1: Any,
    *,
    previous_contract=None,
    comparison_base_sha: str | None = None,
    event_name: str = "unknown",
) -> dict:
    """Evaluate the contract against the production tree at ``root``."""
    actual_sha = _canonical_sha256(_contract_payload(contract))
    violations: list = []
    ratchet_deltas: list = []
    transition_violations: list = []
    entry_violations: list = []
    new_gte_threshold: list = []

    # 0. Previous-contract integrity (fail closed before anything else).
    # Reuses _validate_schema for structural authority so the rules live
    # in one place. Runs only when a previous contract was supplied.
    if previous_contract is not None:
        violations.extend(_validate_previous_contract_integrity(previous_contract))

    runtime_descriptor = _runtime_algorithm_descriptor(l1)
    algorithm_runtime_match = True  # populated below

    # 1. Schema validation (fail closed on structural problems).
    # The threshold check is skipped when a previous contract is
    # supplied so the transition validator owns the threshold rule.
    violations.extend(_validate_schema(contract, check_threshold=(previous_contract is None)))

    # 2. Algorithm pin (runtime L1 vs contract). Mismatch is a FAIL.
    if not violations:
        algo_violations = _validate_algorithm_pin(contract, l1)
        if algo_violations:
            violations.extend(algo_violations)
            algorithm_runtime_match = False
        else:
            algorithm_runtime_match = True

    # 3. Contract payload digest (only when structure is otherwise valid).
    if not violations:
        expected_sha = str(contract.get("contract_payload_sha256") or "")
        if not expected_sha:
            violations.append("contract payload digest missing")
        elif actual_sha != expected_sha:
            violations.append(
                f"contract payload digest mismatch (expected {expected_sha}, got {actual_sha})"
            )

    if violations:
        return _result(
            status="FAIL",
            source_sha=_git_sha(root),
            contract_sha=actual_sha,
            candidate_sha=actual_sha,
            previous_sha=(
                _canonical_sha256(_contract_payload(previous_contract))
                if previous_contract is not None
                else None
            ),
            event_name=event_name,
            metrics_summary={},
            limits={},
            violations=violations,
            ratchet_deltas=[],
            transition_violations=[],
            new_gte_threshold=[],
            entry_violations=[],
            entries_count=0,
            gte_threshold_count=0,
            gte_30_count=0,
            maximum_complexity=0,
            l1_module_sha256=runtime_descriptor["implementation_sha256"],
            algorithm_runtime_match=algorithm_runtime_match,
            contract_version=contract.get("version"),
            contract_source_sha=str(contract.get("baseline_source_sha") or "") or None,
            production_functions=0,
            algorithm_descriptor=runtime_descriptor,
            comparison_base_sha=comparison_base_sha,
        )

    metrics = _collect_metrics(root, l1)
    by_identity = {(m.path, m.function): m for m in metrics}
    entries_dict = _entries_by_identity(contract.get("entries", []) or [])
    gates = contract["release_b_gates"]
    new_function_threshold = int(gates["new_function_complexity_proxy_maximum"])
    gte_threshold = [m for m in metrics if m.complexity_proxy > new_function_threshold]
    gte_30 = [m for m in metrics if m.complexity_proxy >= 30]
    new_gte_threshold = [m for m in gte_threshold if (m.path, m.function) not in entries_dict]
    maximum = max((m.complexity_proxy for m in metrics), default=0)

    limits = {
        "complexity_proxy_gte_20_maximum": int(gates["complexity_proxy_gte_20_maximum"]),
        "complexity_proxy_gte_30_maximum": int(gates["complexity_proxy_gte_30_maximum"]),
        "maximum_complexity_proxy": int(gates["maximum_complexity_proxy"]),
        "new_function_complexity_proxy_maximum": new_function_threshold,
    }

    # 4. Aggregate / per-function checks (FAIL).
    if len(gte_threshold) > limits["complexity_proxy_gte_20_maximum"]:
        violations.append(
            f"complexity_proxy > {new_function_threshold} count {len(gte_threshold)}"
            f" > {limits['complexity_proxy_gte_20_maximum']}"
        )
    if len(gte_30) > limits["complexity_proxy_gte_30_maximum"]:
        violations.append(
            f"complexity_proxy >=30 count {len(gte_30)} > {limits['complexity_proxy_gte_30_maximum']}"
        )
    if maximum > limits["maximum_complexity_proxy"]:
        violations.append(
            f"maximum complexity_proxy {maximum} > {limits['maximum_complexity_proxy']}"
        )

    for identity, entry in entries_dict.items():
        m = by_identity.get(identity)
        if m is None:
            continue
        ceiling = int(entry.get("ceiling", entry.get("current_complexity", 0)))
        if m.complexity_proxy > ceiling:
            entry_violations.append(
                f"locked entry {identity[0]}::{identity[1]} complexity {m.complexity_proxy} > ceiling {ceiling}"
            )

    for m in new_gte_threshold:
        violations.append(
            f"new function {m.path}::{m.function} complexity_proxy {m.complexity_proxy}"
            f" > new_function_complexity_proxy_maximum {new_function_threshold} not in locked entries"
        )

    # 5. Monotonic transition validation if --previous-contract.
    if previous_contract is not None:
        transition_violations = _validate_transition(contract, previous_contract, metrics)

    if violations or entry_violations or transition_violations:
        return _result(
            status="FAIL",
            source_sha=_git_sha(root),
            contract_sha=actual_sha,
            candidate_sha=actual_sha,
            previous_sha=(
                _canonical_sha256(_contract_payload(previous_contract))
                if previous_contract is not None
                else None
            ),
            event_name=event_name,
            metrics_summary={
                "production_functions": len(metrics),
                "gte_threshold": len(gte_threshold),
                "gte_30": len(gte_30),
                "maximum": maximum,
            },
            limits=limits,
            violations=violations,
            ratchet_deltas=[],
            transition_violations=transition_violations,
            new_gte_threshold=[asdict(m) for m in new_gte_threshold],
            entry_violations=entry_violations,
            entries_count=len(entries_dict),
            gte_threshold_count=len(gte_threshold),
            gte_30_count=len(gte_30),
            maximum_complexity=maximum,
            l1_module_sha256=runtime_descriptor["implementation_sha256"],
            algorithm_runtime_match=algorithm_runtime_match,
            contract_version=contract.get("version"),
            contract_source_sha=str(contract.get("baseline_source_sha") or "") or None,
            production_functions=len(metrics),
            algorithm_descriptor=runtime_descriptor,
            comparison_base_sha=comparison_base_sha,
        )

    # 6. RATCHET_REQUIRED (rc 2): code is strictly better than contract.
    if len(gte_threshold) < limits["complexity_proxy_gte_20_maximum"]:
        ratchet_deltas.append(
            f"gte_threshold {len(gte_threshold)} < baseline {limits['complexity_proxy_gte_20_maximum']}"
        )
    if len(gte_30) < limits["complexity_proxy_gte_30_maximum"]:
        ratchet_deltas.append(
            f"gte_30 {len(gte_30)} < baseline {limits['complexity_proxy_gte_30_maximum']}"
        )
    if maximum < limits["maximum_complexity_proxy"]:
        ratchet_deltas.append(
            f"max {maximum} < baseline {limits['maximum_complexity_proxy']}"
        )

    for identity, entry in entries_dict.items():
        m = by_identity.get(identity)
        if m is None:
            continue
        ceiling = int(entry.get("ceiling", entry.get("current_complexity", 0)))
        if m.complexity_proxy < ceiling:
            ratchet_deltas.append(
                f"{identity[0]}::{identity[1]} {m.complexity_proxy} < ceiling {ceiling}"
            )

    if ratchet_deltas:
        return _result(
            status="RATCHET_REQUIRED",
            source_sha=_git_sha(root),
            contract_sha=actual_sha,
            candidate_sha=actual_sha,
            previous_sha=(
                _canonical_sha256(_contract_payload(previous_contract))
                if previous_contract is not None
                else None
            ),
            event_name=event_name,
            metrics_summary={
                "production_functions": len(metrics),
                "gte_threshold": len(gte_threshold),
                "gte_30": len(gte_30),
                "maximum": maximum,
            },
            limits=limits,
            violations=[],
            ratchet_deltas=ratchet_deltas,
            transition_violations=[],
            new_gte_threshold=[],
            entry_violations=[],
            entries_count=len(entries_dict),
            gte_threshold_count=len(gte_threshold),
            gte_30_count=len(gte_30),
            maximum_complexity=maximum,
            l1_module_sha256=runtime_descriptor["implementation_sha256"],
            algorithm_runtime_match=algorithm_runtime_match,
            contract_version=contract.get("version"),
            contract_source_sha=str(contract.get("baseline_source_sha") or "") or None,
            production_functions=len(metrics),
            algorithm_descriptor=runtime_descriptor,
            comparison_base_sha=comparison_base_sha,
        )

    # 7. PASS (rc 0).
    return _result(
        status="PASS",
        source_sha=_git_sha(root),
        contract_sha=actual_sha,
        candidate_sha=actual_sha,
        previous_sha=(
            _canonical_sha256(_contract_payload(previous_contract))
            if previous_contract is not None
            else None
        ),
        event_name=event_name,
        metrics_summary={
            "production_functions": len(metrics),
            "gte_threshold": len(gte_threshold),
            "gte_30": len(gte_30),
            "maximum": maximum,
        },
        limits=limits,
        violations=[],
        ratchet_deltas=[],
        transition_violations=[],
        new_gte_threshold=[],
        entry_violations=[],
        entries_count=len(entries_dict),
        gte_threshold_count=len(gte_threshold),
        gte_30_count=len(gte_30),
        maximum_complexity=maximum,
        l1_module_sha256=runtime_descriptor["implementation_sha256"],
        algorithm_runtime_match=algorithm_runtime_match,
        contract_version=contract.get("version"),
        contract_source_sha=str(contract.get("baseline_source_sha") or "") or None,
        production_functions=len(metrics),
        algorithm_descriptor=runtime_descriptor,
        comparison_base_sha=comparison_base_sha,
    )


def _write_evidence(path: Path, evidence: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument(
        "--previous-contract",
        type=Path,
        default=None,
        help="Optional path to the previous contract for monotonic transition validation. "
             "When supplied, --comparison-base-sha is required.",
    )
    parser.add_argument(
        "--comparison-base-sha",
        default=None,
        help="Trusted SHA (40 lowercase hex chars) from which the previous "
             "contract was fetched. Required when --previous-contract is "
             "supplied; not meaningful without it.",
    )
    parser.add_argument(
        "--event-name",
        default="unknown",
        help="Logical event name to record in the evidence (e.g., pull_request, workflow_dispatch).",
    )
    args = parser.parse_args()

    # --- CLI-level coupling invariant (fail closed up front) -----------
    previous_supplied = args.previous_contract is not None
    comparison_supplied = args.comparison_base_sha is not None

    if previous_supplied and not comparison_supplied:
        print(
            "FAIL: --comparison-base-sha is required when --previous-contract is supplied"
        )
        return 1
    if comparison_supplied and not previous_supplied:
        print(
            "FAIL: --comparison-base-sha is only meaningful with --previous-contract"
        )
        return 1

    comparison_base_sha: str | None = None
    if comparison_supplied:
        comparison_base_sha, validation_error = _validate_comparison_base_sha(
            args.comparison_base_sha
        )
        if validation_error is not None:
            print(f"FAIL: {validation_error}")
            return 1

    # --- L1 + input-file reads (hardened: clean rc 1, no traceback) ----

    try:
        l1 = _load_l1()
    except (L1LoadError, FileNotFoundError, ImportError) as exc:
        print(f"FAIL: cannot load L1 metric module: {exc}")
        return 1

    try:
        contract_text = args.contract.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"FAIL: cannot read candidate contract {args.contract}: {exc}")
        return 1
    try:
        contract = json.loads(contract_text)
    except json.JSONDecodeError as exc:
        print(f"FAIL: candidate contract is not valid JSON: {exc}")
        return 1

    previous_contract = None
    if previous_supplied:
        try:
            previous_text = args.previous_contract.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"FAIL: cannot read previous contract {args.previous_contract}: {exc}")
            return 1
        try:
            previous_contract = json.loads(previous_text)
        except json.JSONDecodeError as exc:
            print(f"FAIL: previous contract is not valid JSON: {exc}")
            return 1

    try:
        evidence = evaluate(
            args.root.resolve(),
            contract,
            l1,
            previous_contract=previous_contract,
            comparison_base_sha=comparison_base_sha,
            event_name=args.event_name,
        )
    except (KeyError, ValueError, TypeError) as exc:
        fallback = {
            "schema": "unihub.python_complexity_contract_v2/v1",
            "result": "FAIL",
            "comparison_base_sha": comparison_base_sha,
            "event_name": args.event_name,
            "violations": [f"evaluator raised: {type(exc).__name__}: {exc}"],
        }
        _write_evidence(args.evidence, fallback)
        return 1

    _write_evidence(args.evidence, evidence)
    status = evidence["result"]
    summary = evidence["metrics_summary"]
    print(
        f"Python complexity contract {status}: "
        f"production={summary.get('production_functions', 0)}, "
        f">threshold {summary.get('gte_threshold', 0)}, "
        f">=30 {summary.get('gte_30', 0)}, "
        f"max {summary.get('maximum', 0)}"
    )
    for violation in evidence["violations"]:
        print(f"- {violation}")
    for violation in evidence["entry_violations"]:
        print(f"- {violation}")
    for violation in evidence["transition_violations"]:
        print(f"- {violation}")
    for delta in evidence["ratchet_candidate"]:
        print(f"~ ratchet: {delta}")

    if status == "PASS":
        return 0
    if status == "FAIL":
        return 1
    if status == "RATCHET_REQUIRED":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
