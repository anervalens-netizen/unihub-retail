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
    new-function threshold, history append-only, locked-entry survival,
    candidate-identity laundering). PR-B1 does not wire --previous-contract
    into CI; PR-B3 will pass the PR-base / FIRST_PARENT contract.

The shared metric module is the single source of truth for the
complexity score. This script provides only policy: thresholds, the
contract payload hash, the ratchet semantics, and the transition
validator. It never re-implements the score algorithm.

Failures fall into three categories:
  FAIL (rc 1)              any safety/policy violation
  RATCHET_REQUIRED (rc 2)  current code strictly better than contract
                           but contract has not been tightened
  PASS (rc 0)              all checks pass

PR-B1 also keeps the --evidence <path> argument and writes a single
JSON artifact there for downstream consumption. The artifact follows
the schema described in
docs/contracts/python-complexity-contract-v2.md.

This script does NOT auto-edit the contract file. Contract changes
must be explicit Git changes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
L1_PATH = Path(__file__).with_name("_python_complexity.py")
DEFAULT_CONTRACT = Path(__file__).with_name("python-complexity-contract-v2.json")
# Private module name used to register L1 in sys.modules before exec_module
# so that dataclasses and other runtime metadata can resolve it. The name
# is fixed and not derived from user input.
_L1_MODNAME = "_unihub_python_complexity_l1"


# ---------------------------------------------------------------------------
# L1 loading
# ---------------------------------------------------------------------------


class L1LoadError(RuntimeError):
    """Raised when L1 cannot be loaded. The check fails closed."""


def _load_l1() -> Any:
    """Load scripts/_python_complexity.py via importlib.

    Uses Path(__file__).with_name(...) so the trusted sibling is
    resolved regardless of cwd and without polluting sys.path with
    scripts/. The module is registered under a fixed private name
    in sys.modules before exec_module so dataclasses can resolve its
    module metadata. On any loader exception the temporary entry is
    removed and the exception is re-raised; the caller turns it into
    a FAIL.
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
    required = {"COUNTED_NODES", "FunctionMetric", "collect_metrics", "function_metrics", "score"}
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
# Per-function metric collection using L1
# ---------------------------------------------------------------------------


def _collect_metrics(root: Path, l1: Any) -> list:
    return list(l1.collect_metrics(root))


# ---------------------------------------------------------------------------
# Transition validator
# ---------------------------------------------------------------------------


def _entries_by_identity(entries: list) -> dict:
    return {
        (str(e["path"]), str(e["function"])): e
        for e in entries
        if isinstance(e, dict) and "path" in e and "function" in e
    }


def _validate_transition(
    candidate: dict,
    previous: dict,
    current_metrics: list,
) -> list:
    """Pure, testable monotonic transition validator.

    Rules (per reviewer enumeration):
      A. aggregate blocking ceilings cannot increase
         (gte_20_maximum, gte_30_maximum, max_complexity_proxy,
          mandatory_locked_gte_30_maximum, wp11_locked_entries_maximum).
      B. new-function threshold cannot loosen (must stay <= 19).
      C. per-function ceiling cannot increase.
      D. history is append-only (cannot remove/overwrite historical records).
      E. tightening is allowed (lower limits, lower ceilings, lower
         threshold are all permitted).
      F. locked identity cannot disappear merely to legitimize current
         complexity. A previously locked function that still exists in
         the current tree and is still >=20 cannot be silently removed.
      G. candidate contract contents cannot redefine history. Adding a
         new entry whose (path, function) is not in the previous >=20
         locked set AND that function is currently >=20 is treated as a
         laundering attempt and rejected.
      H. a previously locked function may disappear from active entries
         only if the current measurement proves it has been
         deleted or has dropped below 20. That is improvement.

    Returns a list of human-readable violation strings. Empty list means
    the transition is monotonic.
    """
    out: list = []
    cand_gates = candidate.get("release_b_gates", {}) or {}
    prev_gates = previous.get("release_b_gates", {}) or {}

    # Rule A: aggregate ceilings cannot increase
    for key in (
        "complexity_proxy_gte_20_maximum",
        "complexity_proxy_gte_30_maximum",
        "maximum_complexity_proxy",
        "mandatory_locked_gte_30_maximum",
        "wp11_locked_entries_maximum",
    ):
        if key in prev_gates and key in cand_gates:
            prev_v = int(prev_gates[key])
            cand_v = int(cand_gates[key])
            if cand_v > prev_v:
                out.append(
                    f"aggregate ceiling {key} {cand_v} > previous {prev_v}"
                )

    # Rule B: new-function threshold cannot loosen
    prev_nf = prev_gates.get("new_function_complexity_proxy_maximum")
    cand_nf = cand_gates.get("new_function_complexity_proxy_maximum")
    if prev_nf is not None and cand_nf is not None and int(cand_nf) > int(prev_nf):
        out.append(
            f"new-function threshold {cand_nf} > previous {prev_nf}"
        )

    cand_entries = _entries_by_identity(candidate.get("entries", []) or [])
    prev_entries = _entries_by_identity(previous.get("entries", []) or [])

    # Rule C: per-function ceiling cannot increase
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

    # Rule D: history append-only
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

    # Rule F: locked identity disappearance while still >=20 in current tree
    by_identity = {(m.path, m.function): m for m in current_metrics}
    for identity, prev_entry in prev_entries.items():
        if identity in cand_entries:
            continue
        cur = by_identity.get(identity)
        if cur is None:
            # Rule H: function was deleted from the tree; allowed.
            continue
        if cur.complexity_proxy >= 20:
            out.append(
                f"locked entry {identity[0]}::{identity[1]} removed "
                f"but current complexity {cur.complexity_proxy} >=20"
            )

    # Rule G: candidate identity laundering — a new entry that covers a
    # function which was not in the previous >=20 locked set AND is
    # currently >=20 is treated as a laundering attempt.
    prev_identities = set(prev_entries.keys())
    for identity, cand_entry in cand_entries.items():
        if identity in prev_identities:
            continue
        cur = by_identity.get(identity)
        if cur is None:
            continue
        if cur.complexity_proxy >= 20:
            out.append(
                f"candidate identity laundering: new entry "
                f"{identity[0]}::{identity[1]} covers function currently "
                f"at complexity {cur.complexity_proxy} but was not in the "
                f"previous >=20 locked set"
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
    new_gte_20: list,
    entry_violations: list,
    entries_count: int,
    gte_20_count: int,
    gte_30_count: int,
    maximum_complexity: int,
    l1_module_sha256: str,
    contract_version,
    contract_source_sha,
    production_functions: int,
) -> dict:
    return {
        "schema": "unihub.python_complexity_contract_v2/v1",
        "result": status,
        "source_sha": source_sha,
        "event_name": event_name,
        "algorithm": {
            "name": "python_complexity_proxy_v1",
            "parser": "python_3.12_ast",
            "implementation_sha256": l1_module_sha256,
        },
        "contract_payload_sha256": contract_sha,
        "contract_source_sha": contract_source_sha,
        "contract_version": contract_version,
        "previous_contract_payload_sha256": previous_sha,
        "candidate_contract_payload_sha256": candidate_sha,
        "metrics": {
            "production_functions": production_functions,
            "complexity_proxy_gte_20": gte_20_count,
            "complexity_proxy_gte_30": gte_30_count,
            "maximum_complexity_proxy": maximum_complexity,
            "new_function_gte_20": len(new_gte_20),
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
    event_name: str = "unknown",
) -> dict:
    """Evaluate the contract against the production tree at ``root``."""
    l1_sha = hashlib.sha256(L1_PATH.read_bytes()).hexdigest() if L1_PATH.is_file() else ""

    payload = _contract_payload(contract)
    expected_sha = str(contract.get("contract_payload_sha256") or "")
    actual_sha = _canonical_sha256(payload)
    violations: list = []
    ratchet_deltas: list = []
    transition_violations: list = []
    entry_violations: list = []
    new_gte_20: list = []

    if not expected_sha:
        violations.append("contract payload digest missing")
    elif actual_sha != expected_sha:
        violations.append(
            f"contract payload digest mismatch (expected {expected_sha}, got {actual_sha})"
        )

    if contract.get("version") != 2:
        violations.append(f"unsupported contract version: {contract.get('version')!r}")

    gates = contract.get("release_b_gates")
    entries = contract.get("entries")
    if not isinstance(gates, dict):
        violations.append("release_b_gates must be a dict")
    if not isinstance(entries, list):
        violations.append("entries must be a list")

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
            limits={} if not isinstance(gates, dict) else dict(gates),
            violations=violations,
            ratchet_deltas=[],
            transition_violations=[],
            new_gte_20=[],
            entry_violations=[],
            entries_count=0,
            gte_20_count=0,
            gte_30_count=0,
            maximum_complexity=0,
            l1_module_sha256=l1_sha,
            contract_version=contract.get("version"),
            contract_source_sha=str(contract.get("baseline_source_sha") or "") or None,
            production_functions=0,
        )

    metrics = _collect_metrics(root, l1)
    by_identity = {(m.path, m.function): m for m in metrics}
    entries_dict = _entries_by_identity(entries)
    gte_20 = [m for m in metrics if m.complexity_proxy >= 20]
    gte_30 = [m for m in metrics if m.complexity_proxy >= 30]
    new_gte_20 = [
        m for m in gte_20 if (m.path, m.function) not in entries_dict
    ]
    maximum = max((m.complexity_proxy for m in metrics), default=0)

    limits = {
        "complexity_proxy_gte_20_maximum": int(gates["complexity_proxy_gte_20_maximum"]),
        "complexity_proxy_gte_30_maximum": int(gates["complexity_proxy_gte_30_maximum"]),
        "maximum_complexity_proxy": int(gates["maximum_complexity_proxy"]),
        "new_function_complexity_proxy_maximum": int(
            gates["new_function_complexity_proxy_maximum"]
        ),
        "wp11_locked_entries_maximum": int(gates["wp11_locked_entries_maximum"]),
        "mandatory_locked_gte_30_maximum": int(
            gates["mandatory_locked_gte_30_maximum"]
        ),
    }

    # Precedence 1: FAIL checks
    if len(gte_20) > limits["complexity_proxy_gte_20_maximum"]:
        violations.append(
            f"complexity_proxy >=20 count {len(gte_20)} > {limits['complexity_proxy_gte_20_maximum']}"
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

    for m in new_gte_20:
        violations.append(
            f"new function {m.path}::{m.function} complexity_proxy {m.complexity_proxy} >=20 not in locked entries"
        )

    # Precedence 1 (continued): monotonic transition validation if --previous-contract
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
                "gte_20": len(gte_20),
                "gte_30": len(gte_30),
                "maximum": maximum,
            },
            limits=limits,
            violations=violations,
            ratchet_deltas=[],
            transition_violations=transition_violations,
            new_gte_20=[asdict(m) for m in new_gte_20],
            entry_violations=entry_violations,
            entries_count=len(entries_dict),
            gte_20_count=len(gte_20),
            gte_30_count=len(gte_30),
            maximum_complexity=maximum,
            l1_module_sha256=l1_sha,
            contract_version=contract.get("version"),
            contract_source_sha=str(contract.get("baseline_source_sha") or "") or None,
            production_functions=len(metrics),
        )

    # Precedence 2: RATCHET_REQUIRED
    if len(gte_20) < limits["complexity_proxy_gte_20_maximum"]:
        ratchet_deltas.append(
            f"gte_20 {len(gte_20)} < baseline {limits['complexity_proxy_gte_20_maximum']}"
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
                "gte_20": len(gte_20),
                "gte_30": len(gte_30),
                "maximum": maximum,
            },
            limits=limits,
            violations=[],
            ratchet_deltas=ratchet_deltas,
            transition_violations=[],
            new_gte_20=[],
            entry_violations=[],
            entries_count=len(entries_dict),
            gte_20_count=len(gte_20),
            gte_30_count=len(gte_30),
            maximum_complexity=maximum,
            l1_module_sha256=l1_sha,
            contract_version=contract.get("version"),
            contract_source_sha=str(contract.get("baseline_source_sha") or "") or None,
            production_functions=len(metrics),
        )

    # Precedence 3: PASS
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
            "gte_20": len(gte_20),
            "gte_30": len(gte_30),
            "maximum": maximum,
        },
        limits=limits,
        violations=[],
        ratchet_deltas=[],
        transition_violations=[],
        new_gte_20=[],
        entry_violations=[],
        entries_count=len(entries_dict),
        gte_20_count=len(gte_20),
        gte_30_count=len(gte_30),
        maximum_complexity=maximum,
        l1_module_sha256=l1_sha,
        contract_version=contract.get("version"),
        contract_source_sha=str(contract.get("baseline_source_sha") or "") or None,
        production_functions=len(metrics),
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
             "PR-B1 does not wire this into CI; PR-B3 will.",
    )
    parser.add_argument(
        "--event-name",
        default="unknown",
        help="Logical event name to record in the evidence (e.g., pull_request, workflow_dispatch).",
    )
    args = parser.parse_args()

    try:
        l1 = _load_l1()
    except (L1LoadError, FileNotFoundError, ImportError) as exc:
        print(f"FAIL: cannot load L1 metric module: {exc}")
        return 1

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    previous_contract = (
        json.loads(args.previous_contract.read_text(encoding="utf-8"))
        if args.previous_contract is not None
        else None
    )

    try:
        evidence = evaluate(
            args.root.resolve(),
            contract,
            l1,
            previous_contract=previous_contract,
            event_name=args.event_name,
        )
    except (KeyError, ValueError, TypeError) as exc:
        fallback = {
            "schema": "unihub.python_complexity_contract_v2/v1",
            "result": "FAIL",
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
        f">=20 {summary.get('gte_20', 0)}, "
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
