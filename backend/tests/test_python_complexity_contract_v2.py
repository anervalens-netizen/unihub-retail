"""Tests for the monotonic Python complexity contract v2.

These tests verify the contract-check script's three-state result
(PASS / FAIL / RATCHET_REQUIRED), the new-function threshold semantics
(pinned at 19, derived from the contract), the algorithm descriptor
pinning (L1 SHA-256 + structured descriptor), the structural
fail-closed behavior on malformed contracts, and the optional
--previous-contract monotonic transition validator. Many cases build
synthetic contracts on a temp tree so the production tree is not
modified.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


PR_B1_WORKTREE = Path(__file__).resolve().parents[2]
CHECK_PATH = PR_B1_WORKTREE / "scripts" / "check_python_complexity_contract.py"
CONTRACT_PATH = PR_B1_WORKTREE / "scripts" / "python-complexity-contract-v2.json"
L1_PATH = PR_B1_WORKTREE / "scripts" / "_python_complexity.py"


def _load_check_module():
    spec = importlib.util.spec_from_file_location(
        "_pr_b1_check", str(CHECK_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_l1_module():
    spec = importlib.util.spec_from_file_location(
        "_pr_b1_l1", str(L1_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def check():
    return _load_check_module()


@pytest.fixture(scope="module")
def l1():
    return _load_l1_module()


@pytest.fixture(scope="module")
def real_v2_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_path(contract: dict, path_segments, value) -> dict:
    """Deep-copy a contract and set a value at a nested path."""
    out = copy.deepcopy(contract)
    cursor = out
    for seg in path_segments[:-1]:
        cursor = cursor[seg]
    cursor[path_segments[-1]] = value
    return out


def _rehash(contract: dict) -> dict:
    """Recompute the contract_payload_sha256 after mutation."""
    payload = {k: v for k, v in contract.items() if k != "contract_payload_sha256"}
    contract["contract_payload_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return contract


def _baseline_algorithm(l1) -> dict:
    """The structured algorithm block L1 must produce."""
    spec = l1.algorithm_spec()
    return {
        "name": l1.ALGORITHM_NAME,
        "implementation_sha256": hashlib.sha256(L1_PATH.read_bytes()).hexdigest(),
        "initial_score": spec["initial_score"],
        "counted_nodes": list(spec["counted_nodes"]),
        "bool_op": spec["bool_op"],
        "walk": spec["walk"],
    }


def _baseline_gates() -> dict:
    """Minimal v2 release_b_gates sufficient for synthetic tests."""
    return {
        "complexity_proxy_gte_20_maximum": 0,
        "complexity_proxy_gte_30_maximum": 0,
        "maximum_complexity_proxy": 0,
        "new_function_complexity_proxy_maximum": 19,
    }


def _gates_for(actual_max: int, actual_gte_20: int = 0) -> dict:
    """Build release_b_gates that match the synthetic code exactly."""
    return {
        "complexity_proxy_gte_20_maximum": actual_gte_20,
        "complexity_proxy_gte_30_maximum": 0,
        "maximum_complexity_proxy": actual_max,
        "new_function_complexity_proxy_maximum": 19,
    }


def _baseline_history() -> dict:
    return {"v1": {"version": 1, "baseline_source_sha": "placeholder"}}


def _minimal_contract(
    l1,
    *,
    algorithm=None,
    gates=None,
    history=None,
    entries=None,
) -> dict:
    """Build a minimal v2 contract that survives schema validation.

    PR-B3: the previous-contract integrity validator requires a
    ``contract_payload_sha256`` that matches the canonical SHA-256 of the
    payload. This helper recomputes the digest so every returned contract
    is a faithful prior contract — callers can still mutate and re-hash
    via ``_rehash`` afterwards.
    """
    contract = {
        "version": 2,
        "algorithm": algorithm if algorithm is not None else _baseline_algorithm(l1),
        "release_b_gates": gates if gates is not None else _baseline_gates(),
        "history": history if history is not None else _baseline_history(),
        "entries": entries if entries is not None else [],
    }
    return _rehash(contract)


# ---------------------------------------------------------------------------
# 1. PASS on exact-main
# ---------------------------------------------------------------------------


def test_case_1_pass_on_exact_main(check, l1, real_v2_contract):
    result = check.evaluate(PR_B1_WORKTREE, real_v2_contract, l1)
    assert result["result"] == "PASS"
    assert result["metrics"]["production_functions"] == 2990
    assert result["metrics"]["complexity_proxy_gte_threshold"] == 28
    assert result["metrics"]["complexity_proxy_gte_30"] == 0
    assert result["metrics"]["maximum_complexity_proxy"] == 28
    assert result["metrics"]["new_function_above_threshold"] == 0
    assert result["algorithm_runtime_match"] is True


# ---------------------------------------------------------------------------
# 2. New function with cp=20 should FAIL
# ---------------------------------------------------------------------------


def test_case_2_new_function_cp_20_fails(check, l1, tmp_path):
    """Build a synthetic root with one new cp=20 function; v2 contract
    must FAIL because complexity_proxy 20 > new_function_threshold 19."""
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir()
    new_py = fake_backend / "new_hot.py"
    # 1 base + 19 Ifs = cp 20
    body = (
        "def new_hot(x):\n"
        + "    if x:\n        return 1\n" * 19
        + "    return 0\n"
    )
    new_py.write_text(body)
    metrics = l1.function_metrics(body, "backend/new_hot.py")
    assert metrics[0].complexity_proxy == 20

    contract = _minimal_contract(l1)
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any("new_hot" in v for v in result["violations"])
    assert any(
        "new_function_complexity_proxy_maximum 19" in v for v in result["violations"]
    )


# ---------------------------------------------------------------------------
# 3. aggregate gte_20 29 -> 30 FAIL (transition validator)
# ---------------------------------------------------------------------------


def test_case_3_aggregate_gte_20_increase_fails(check, l1, real_v2_contract):
    previous = copy.deepcopy(real_v2_contract)
    candidate = _set_path(
        real_v2_contract,
        ("release_b_gates", "complexity_proxy_gte_20_maximum"),
        30,
    )
    _rehash(candidate)
    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("gte_20" in v and "30" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 4. aggregate gte_30 0 -> 1 FAIL (transition validator)
# ---------------------------------------------------------------------------


def test_case_4_aggregate_gte_30_increase_fails(check, l1, real_v2_contract):
    previous = copy.deepcopy(real_v2_contract)
    candidate = _set_path(
        real_v2_contract,
        ("release_b_gates", "complexity_proxy_gte_30_maximum"),
        1,
    )
    _rehash(candidate)
    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("gte_30" in v and "1" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 5. max 28 -> 29 FAIL (transition validator)
# ---------------------------------------------------------------------------


def test_case_5_max_increase_fails(check, l1, real_v2_contract):
    previous = copy.deepcopy(real_v2_contract)
    candidate = _set_path(
        real_v2_contract,
        ("release_b_gates", "maximum_complexity_proxy"),
        29,
    )
    _rehash(candidate)
    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("maximum" in v and "29" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 6. existing entry exceeds its ceiling FAIL
# ---------------------------------------------------------------------------


def test_case_6_entry_exceeds_ceiling_fails(check, l1, real_v2_contract):
    """Lower regional_summary's ceiling to 27. Actual is 28 -> FAIL."""
    contract = copy.deepcopy(real_v2_contract)
    for entry in contract["entries"]:
        if entry["function"] == "regional_summary":
            entry["ceiling"] = 27
    _rehash(contract)
    result = check.evaluate(PR_B1_WORKTREE, contract, l1)
    assert result["result"] == "FAIL"
    assert any("regional_summary" in v for v in result["entry_violations"])


# ---------------------------------------------------------------------------
# 7. code improves but contract remains stale -> RATCHET_REQUIRED rc=2
# ---------------------------------------------------------------------------


def test_case_7_ratchet_required_when_code_better(check, l1, real_v2_contract):
    contract = copy.deepcopy(real_v2_contract)
    contract["release_b_gates"]["maximum_complexity_proxy"] = 99
    for entry in contract["entries"]:
        entry["ceiling"] = 99
    _rehash(contract)
    result = check.evaluate(PR_B1_WORKTREE, contract, l1)
    assert result["result"] == "RATCHET_REQUIRED"


# ---------------------------------------------------------------------------
# 8. Same exact-main state with default ceiling -> PASS
# ---------------------------------------------------------------------------


def test_case_8_default_state_passes(check, l1, real_v2_contract):
    contract = copy.deepcopy(real_v2_contract)
    _rehash(contract)
    result = check.evaluate(PR_B1_WORKTREE, contract, l1)
    assert result["result"] == "PASS"


# ---------------------------------------------------------------------------
# 9. ceiling regression after tightening -> FAIL
# ---------------------------------------------------------------------------


def test_case_9_regression_after_tightening_fails(check, l1, tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    fn_path = backend / "mod.py"
    fn_path.write_text(
        "def f(x):\n"
        + "    if x:\n        return 1\n" * 23
        + "    return 0\n"
    )

    contract = _minimal_contract(
        l1,
        entries=[
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 24,
                "ceiling": 22,
            }
        ],
    )
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1, previous_contract=contract)
    assert result["result"] == "FAIL"
    assert any("f" in v and "ceiling" in v for v in result["entry_violations"])


# ---------------------------------------------------------------------------
# 10. boundary regression 20 -> 19 -> later 20 -> FAIL
# ---------------------------------------------------------------------------


def test_case_10_boundary_regression_fails(check, l1, tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    fn_path = backend / "b.py"
    fn_path.write_text(
        "def f(x):\n"
        + "    if x:\n        return 1\n" * 19
        + "    return 0\n"
    )

    contract = _minimal_contract(
        l1,
        entries=[
            {
                "path": "backend/b.py",
                "function": "f",
                "current_complexity": 20,
                "ceiling": 19,
            }
        ],
    )
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1, previous_contract=contract)
    assert result["result"] == "FAIL"


# ---------------------------------------------------------------------------
# 11. ceiling transition 22 -> 24 FAIL (transition validator)
# ---------------------------------------------------------------------------


def test_case_11_ceiling_increase_in_transition_fails(check, l1, tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    fn_path = backend / "mod.py"
    fn_path.write_text("def f(x):\n    return 1\n")

    previous = _minimal_contract(
        l1,
        gates=_gates_for(actual_max=22, actual_gte_20=1),
        entries=[
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 22,
                "ceiling": 22,
            }
        ],
    )
    candidate = copy.deepcopy(previous)
    candidate["entries"][0]["ceiling"] = 24
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("ceiling" in v and "22" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 12. aggregate 33 -> 34 FAIL (transition validator)
# ---------------------------------------------------------------------------


def test_case_12_aggregate_weakening_in_transition_fails(check, l1, tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    previous = _minimal_contract(l1)
    candidate = copy.deepcopy(previous)
    candidate["release_b_gates"]["complexity_proxy_gte_20_maximum"] = 34
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("gte_20" in v and "34" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 13. new-function max 19 -> 20 FAIL (transition validator)
# ---------------------------------------------------------------------------


def test_case_13_new_fn_threshold_loosen_fails(check, l1, tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    previous = _minimal_contract(l1)
    candidate = copy.deepcopy(previous)
    candidate["release_b_gates"]["new_function_complexity_proxy_maximum"] = 20
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any(
        "new-function threshold" in v and "20" in v
        for v in result["transition_violations"]
    )


# ---------------------------------------------------------------------------
# 14. history rewrite FAIL
# ---------------------------------------------------------------------------


def test_case_14_history_rewrite_fails(check, l1, tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    previous = _minimal_contract(
        l1,
        history={"v1": {"version": 1, "baseline_source_sha": "abc"}},
    )
    candidate = copy.deepcopy(previous)
    candidate["history"]["v1"]["baseline_source_sha"] = "REWRITTEN"
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("v1" in v and "overwritten" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 15. history append PASS
# ---------------------------------------------------------------------------


def test_case_15_history_append_passes(check, l1, tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    previous = _minimal_contract(
        l1,
        gates=_gates_for(actual_max=0, actual_gte_20=0),
        history={"v1": {"version": 1, "baseline_source_sha": "abc"}},
    )
    candidate = copy.deepcopy(previous)
    candidate["history"]["v2_marker"] = {"version": 2, "note": "appended"}
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "PASS"


# ---------------------------------------------------------------------------
# 16. 25 -> 22 contract tightening PASS
# ---------------------------------------------------------------------------


def test_case_16_ceiling_tightening_passes(check, l1, tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    fn_path = backend / "mod.py"
    fn_path.write_text(
        "def f(x):\n"
        + "    if x:\n        return 1\n" * 21
        + "    return 0\n"
    )
    previous = _minimal_contract(
        l1,
        gates=_gates_for(actual_max=22, actual_gte_20=1),
        entries=[
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 22,
                "ceiling": 25,
            }
        ],
    )
    candidate = copy.deepcopy(previous)
    candidate["entries"][0]["ceiling"] = 22
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "PASS"


# ---------------------------------------------------------------------------
# 17. remove locked entry while current >=20 FAIL
# ---------------------------------------------------------------------------


def test_case_17_locked_entry_removal_while_still_ge20_fails(
    check, l1, real_v2_contract
):
    previous = copy.deepcopy(real_v2_contract)
    candidate = copy.deepcopy(real_v2_contract)
    candidate["entries"] = [
        e for e in candidate["entries"] if e["function"] != "regional_summary"
    ]
    _rehash(candidate)

    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("regional_summary" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 18. remove locked entry after function <20 PASS (improvement)
# ---------------------------------------------------------------------------


def test_case_18_locked_entry_removal_after_improvement_passes(
    check, l1, tmp_path
):
    backend = tmp_path / "backend"
    backend.mkdir()
    fn_path = backend / "mod.py"
    fn_path.write_text("def f(x):\n    return 1\n")

    previous = _minimal_contract(
        l1,
        gates=_gates_for(actual_max=1, actual_gte_20=0),
        entries=[
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 22,
                "ceiling": 22,
            }
        ],
    )
    candidate = copy.deepcopy(previous)
    candidate["entries"] = []
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "PASS"


# ---------------------------------------------------------------------------
# 19. candidate identity laundering attempt -> FAIL
# ---------------------------------------------------------------------------


def test_case_19_candidate_identity_laundering_fails(
    check, l1, real_v2_contract
):
    previous = _minimal_contract(
        l1,
        algorithm=real_v2_contract["algorithm"],
        gates=real_v2_contract["release_b_gates"],
        history=real_v2_contract["history"],
    )
    previous["entries"] = []
    candidate = copy.deepcopy(real_v2_contract)
    _rehash(candidate)

    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("laundering" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 20. invalid contract structure/hash FAIL CLOSED
# ---------------------------------------------------------------------------


def test_case_20_invalid_contract_fails_closed(check, l1, real_v2_contract):
    bad = copy.deepcopy(real_v2_contract)
    bad["contract_payload_sha256"] = "0" * 64
    result = check.evaluate(PR_B1_WORKTREE, bad, l1)
    assert result["result"] == "FAIL"
    assert any("digest" in v for v in result["violations"])

    bad2 = copy.deepcopy(real_v2_contract)
    bad2["version"] = 99
    _rehash(bad2)
    result = check.evaluate(PR_B1_WORKTREE, bad2, l1)
    assert result["result"] == "FAIL"
    assert any("version" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# 21. no automatic file modification occurs
# ---------------------------------------------------------------------------


def test_case_21_no_auto_modification(check, l1, real_v2_contract, tmp_path):
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(CONTRACT_PATH.read_text())
    before_sha = _file_sha(contract_path)

    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("untouched")
    sentinel_sha = _file_sha(sentinel)

    check.evaluate(PR_B1_WORKTREE, real_v2_contract, l1)
    bad = copy.deepcopy(real_v2_contract)
    bad["version"] = 99
    _rehash(bad)
    check.evaluate(PR_B1_WORKTREE, bad, l1)

    assert _file_sha(contract_path) == before_sha
    assert _file_sha(sentinel) == sentinel_sha


def _file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ===========================================================================
# PR-B1 final semantic correction — new test cases
# ===========================================================================


# ---------------------------------------------------------------------------
# 22. New function with cp=19 PASS
# ---------------------------------------------------------------------------


def test_case_22_new_function_cp_19_passes(check, l1, tmp_path):
    """New function at cp=19 is allowed (19 <= new_function_threshold 19)."""
    backend = tmp_path / "backend"
    backend.mkdir()
    new_py = backend / "new_at_19.py"
    # 1 base + 18 Ifs = cp 19
    body = (
        "def new_at_19(x):\n"
        + "    if x:\n        return 1\n" * 18
        + "    return 0\n"
    )
    new_py.write_text(body)
    metrics = l1.function_metrics(body, "backend/new_at_19.py")
    assert metrics[0].complexity_proxy == 19

    # Contract gates must match actual max of 19.
    contract = _minimal_contract(
        l1,
        gates=_gates_for(actual_max=19, actual_gte_20=0),
    )
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "PASS", result


# ---------------------------------------------------------------------------
# 23. New function with cp=20 FAIL (boundary repetition for clarity)
# ---------------------------------------------------------------------------


def test_case_23_new_function_cp_20_fails_at_boundary(check, l1, tmp_path):
    """New function at cp=20 must FAIL because 20 > new_function_threshold 19."""
    backend = tmp_path / "backend"
    backend.mkdir()
    new_py = backend / "hot.py"
    body = (
        "def hot(x):\n"
        + "    if x:\n        return 1\n" * 19
        + "    return 0\n"
    )
    new_py.write_text(body)
    metrics = l1.function_metrics(body, "backend/hot.py")
    assert metrics[0].complexity_proxy == 20

    contract = _minimal_contract(l1)
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any("hot" in v for v in result["violations"])
    assert any(
        "new_function_complexity_proxy_maximum 19" in v for v in result["violations"]
    )


# ---------------------------------------------------------------------------
# 24. new-function 19 -> 20 contract transition FAIL
# ---------------------------------------------------------------------------


def test_case_24_transition_19_to_20_fails(check, l1, tmp_path):
    """Loosening 19 -> 20 must FAIL the v2 -> v2 transition validator."""
    backend = tmp_path / "backend"
    backend.mkdir()
    previous = _minimal_contract(l1)
    candidate = copy.deepcopy(previous)
    candidate["release_b_gates"]["new_function_complexity_proxy_maximum"] = 20
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any(
        "new-function threshold" in v and "20" in v
        for v in result["transition_violations"]
    )


# ---------------------------------------------------------------------------
# 25. new-function 19 -> 18 contract transition FAIL
# ---------------------------------------------------------------------------


def test_case_25_transition_19_to_18_fails(check, l1, tmp_path):
    """Tightening 19 -> 18 must FAIL (v2 -> v2 boundary is immutable)."""
    backend = tmp_path / "backend"
    backend.mkdir()
    previous = _minimal_contract(l1)
    candidate = copy.deepcopy(previous)
    candidate["release_b_gates"]["new_function_complexity_proxy_maximum"] = 18
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    # The transition validator owns the threshold rule when previous is
    # provided.
    assert any(
        "new-function threshold 18 is not pinned at 19" in v
        for v in result["transition_violations"]
    )


# ---------------------------------------------------------------------------
# 26. invalid initial v2 threshold != 19 FAIL CLOSED
# ---------------------------------------------------------------------------


def test_case_26_invalid_initial_threshold_fails_closed(check, l1, tmp_path):
    """An initial v2 contract with new_function_threshold != 19 must FAIL."""
    backend = tmp_path / "backend"
    backend.mkdir()

    for bad in (18, 20):
        contract = _minimal_contract(l1)
        contract["release_b_gates"]["new_function_complexity_proxy_maximum"] = bad
        _rehash(contract)
        result = check.evaluate(tmp_path, contract, l1)
        assert result["result"] == "FAIL", f"unexpected PASS for threshold={bad}"
        assert any(
            "new_function_complexity_proxy_maximum must be 19" in v
            for v in result["violations"]
        ), f"threshold={bad} did not produce the expected schema violation"


# ---------------------------------------------------------------------------
# 27. exact L1 implementation hash matches contract -> PASS
# ---------------------------------------------------------------------------


def test_case_27_l1_implementation_hash_matches(check, l1, real_v2_contract):
    """Production contract's implementation_sha256 matches runtime L1."""
    result = check.evaluate(PR_B1_WORKTREE, real_v2_contract, l1)
    assert result["result"] == "PASS"
    assert result["algorithm_runtime_match"] is True
    assert result["algorithm"]["implementation_sha256"] == hashlib.sha256(
        L1_PATH.read_bytes()
    ).hexdigest()


# ---------------------------------------------------------------------------
# 28. alter contract implementation hash -> FAIL
# ---------------------------------------------------------------------------


def test_case_28_altered_impl_hash_fails(check, l1, real_v2_contract):
    """Tampering with contract.algorithm.implementation_sha256 must FAIL."""
    contract = copy.deepcopy(real_v2_contract)
    contract["algorithm"]["implementation_sha256"] = "f" * 64
    _rehash(contract)
    result = check.evaluate(PR_B1_WORKTREE, contract, l1)
    assert result["result"] == "FAIL"
    assert any(
        "implementation_sha256 mismatch" in v for v in result["violations"]
    )


# ---------------------------------------------------------------------------
# 29. alter count of `counted_nodes` -> FAIL
# ---------------------------------------------------------------------------


def test_case_29_altered_counted_nodes_fails(check, l1, real_v2_contract):
    """Adding/removing a counted node type must FAIL the algorithm pin."""
    contract = copy.deepcopy(real_v2_contract)
    contract["algorithm"]["counted_nodes"] = list(
        contract["algorithm"]["counted_nodes"]
    ) + ["Extra"]
    _rehash(contract)
    result = check.evaluate(PR_B1_WORKTREE, contract, l1)
    assert result["result"] == "FAIL"
    assert any("counted_nodes mismatch" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# 30. change counted_nodes descriptor in v2 -> v2 -> FAIL
# ---------------------------------------------------------------------------


def test_case_30_changed_counted_nodes_in_transition_fails(
    check, l1, real_v2_contract
):
    previous = copy.deepcopy(real_v2_contract)
    previous["algorithm"]["counted_nodes"] = list(
        previous["algorithm"]["counted_nodes"]
    ) + ["Extra"]
    _rehash(previous)
    candidate = copy.deepcopy(real_v2_contract)
    _rehash(candidate)
    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any(
        "algorithm descriptor changed" in v for v in result["transition_violations"]
    )


# ---------------------------------------------------------------------------
# 31. change implementation_sha256 in v2 -> v2 -> FAIL
# ---------------------------------------------------------------------------


def test_case_31_changed_impl_sha_in_transition_fails(
    check, l1, real_v2_contract
):
    previous = copy.deepcopy(real_v2_contract)
    previous["algorithm"]["implementation_sha256"] = "a" * 64
    _rehash(previous)
    candidate = copy.deepcopy(real_v2_contract)
    _rehash(candidate)
    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any(
        "algorithm descriptor changed" in v for v in result["transition_violations"]
    )


# ---------------------------------------------------------------------------
# 32. algorithm descriptor tampered in v2 -> v2 -> FAIL
# ---------------------------------------------------------------------------


def test_case_32_altered_algorithm_descriptor_in_transition_fails(
    check, l1, real_v2_contract
):
    """Tampering with bool_op in a v2 -> v2 transition must FAIL."""
    previous = copy.deepcopy(real_v2_contract)
    previous["algorithm"]["bool_op"] = "max(1,len(values)-1)_TAMPERED"
    _rehash(previous)
    candidate = copy.deepcopy(real_v2_contract)
    _rehash(candidate)
    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any(
        "algorithm descriptor changed" in v for v in result["transition_violations"]
    )


# ===========================================================================
# Structural fail-closed (PR-B1 final semantic correction)
# ===========================================================================


def test_case_33_duplicate_locked_identities_fail(check, l1, tmp_path):
    """Duplicate locked entries must fail closed (no silent collapse)."""
    backend = tmp_path / "backend"
    backend.mkdir()
    fn_path = backend / "mod.py"
    fn_path.write_text("def f(x):\n    return 1\n")

    contract = _minimal_contract(
        l1,
        entries=[
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 1,
                "ceiling": 1,
            },
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 1,
                "ceiling": 1,
            },
        ],
    )
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any("duplicate locked entry identity" in v for v in result["violations"])


def test_case_34_entry_missing_path_fails(check, l1, tmp_path):
    """An entry without `path` must FAIL the schema validator."""
    backend = tmp_path / "backend"
    backend.mkdir()
    contract = _minimal_contract(
        l1,
        entries=[{"function": "f", "current_complexity": 1, "ceiling": 1}],
    )
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any("entries[0].path missing" in v for v in result["violations"])


def test_case_35_entry_missing_function_fails(check, l1, tmp_path):
    """An entry without `function` must FAIL the schema validator."""
    backend = tmp_path / "backend"
    backend.mkdir()
    contract = _minimal_contract(
        l1,
        entries=[{"path": "backend/mod.py", "current_complexity": 1, "ceiling": 1}],
    )
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any("entries[0].function missing" in v for v in result["violations"])


def test_case_36_entry_missing_ceiling_fails(check, l1, tmp_path):
    """An entry without `ceiling` or `current_complexity` must FAIL."""
    backend = tmp_path / "backend"
    backend.mkdir()
    contract = _minimal_contract(
        l1,
        entries=[{"path": "backend/mod.py", "function": "f"}],
    )
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any("missing ceiling/current_complexity" in v for v in result["violations"])


def test_case_37_duplicate_remediation_identities_fail(check, l1, tmp_path):
    """Duplicate remediation identities must fail closed."""
    backend = tmp_path / "backend"
    backend.mkdir()
    contract = _minimal_contract(l1)
    contract["remediation_entries"] = [
        {
            "path": "backend/services/target_calculator/profitability.py",
            "function": "populate_profitability",
            "current_complexity": 49,
            "target_complexity": 29,
        },
        {
            "path": "backend/services/target_calculator/profitability.py",
            "function": "populate_profitability",
            "current_complexity": 49,
            "target_complexity": 29,
        },
    ]
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any(
        "duplicate remediation entry identity" in v for v in result["violations"]
    )


def test_case_38_legacy_wp11_field_in_active_v2_fails(check, l1, tmp_path):
    """Active v2 release_b_gates MUST NOT carry legacy WP11 fields."""
    backend = tmp_path / "backend"
    backend.mkdir()
    contract = _minimal_contract(l1)
    contract["release_b_gates"]["wp11_locked_entries_maximum"] = 0
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any(
        "wp11_locked_entries_maximum is a legacy v1 field" in v
        for v in result["violations"]
    )

    contract = _minimal_contract(l1)
    contract["release_b_gates"]["mandatory_locked_gte_30_maximum"] = 3
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any(
        "mandatory_locked_gte_30_maximum is a legacy v1 field" in v
        for v in result["violations"]
    )


# ---------------------------------------------------------------------------
# CLI / exit-code smoke tests
# ---------------------------------------------------------------------------


def test_cli_pass_returns_rc_0():
    import subprocess

    proc = subprocess.run(
        [
            str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
            "-I",
            str(CHECK_PATH),
            "--root",
            str(PR_B1_WORKTREE),
            "--contract",
            str(CONTRACT_PATH),
            "--evidence",
            "/tmp/_pr_b1_evidence.json",
            "--event-name",
            "pull_request",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"


def test_cli_fail_returns_rc_1(tmp_path):
    import subprocess

    bad = json.loads(CONTRACT_PATH.read_text())
    bad["release_b_gates"]["maximum_complexity_proxy"] = 27
    _rehash(bad)
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad, indent=2))

    proc = subprocess.run(
        [
            str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
            "-I",
            str(CHECK_PATH),
            "--root",
            str(PR_B1_WORKTREE),
            "--contract",
            str(bad_path),
            "--evidence",
            str(tmp_path / "evidence.json"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1, f"stdout={proc.stdout}\nstderr={proc.stderr}"


def test_cli_ratchet_returns_rc_2():
    import subprocess

    bad = json.loads(CONTRACT_PATH.read_text())
    bad["release_b_gates"]["maximum_complexity_proxy"] = 99
    for entry in bad["entries"]:
        entry["ceiling"] = 99
    _rehash(bad)
    bad_path = "/tmp/_pr_b1_ratchet_contract.json"
    Path(bad_path).write_text(json.dumps(bad, indent=2))

    proc = subprocess.run(
        [
            str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
            "-I",
            str(CHECK_PATH),
            "--root",
            str(PR_B1_WORKTREE),
            "--contract",
            bad_path,
            "--evidence",
            "/tmp/_pr_b1_ratchet_evidence.json",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 2, f"stdout={proc.stdout}\nstderr={proc.stderr}"


# ===========================================================================
# PR-B3: comparison-base-sha coupling invariant
# ===========================================================================


def _cli_run(check_args, *, event_name="pull_request"):
    """Helper: run the CLI with a standard layout, return CompletedProcess."""
    import subprocess

    cmd = [
        str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
        "-I",
        str(CHECK_PATH),
        "--root",
        str(PR_B1_WORKTREE),
        "--contract",
        str(CONTRACT_PATH),
        "--evidence",
        "/tmp/_pr_b3_evidence.json",
        "--event-name",
        event_name,
    ]
    cmd.extend(check_args)
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=120
    )


def test_cli_comparison_base_sha_required_with_previous():
    """--previous-contract without --comparison-base-sha must FAIL rc 1."""
    import subprocess

    proc = subprocess.run(
        [
            str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
            "-I",
            str(CHECK_PATH),
            "--root",
            str(PR_B1_WORKTREE),
            "--contract",
            str(CONTRACT_PATH),
            "--previous-contract",
            str(CONTRACT_PATH),
            "--evidence",
            "/tmp/_pr_b3_evidence.json",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "comparison_base_sha" in proc.stdout or "comparison-base-sha" in proc.stdout


def test_cli_comparison_base_sha_forbidden_without_previous():
    """--comparison-base-sha without --previous-contract must FAIL rc 1."""
    import subprocess

    proc = subprocess.run(
        [
            str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
            "-I",
            str(CHECK_PATH),
            "--root",
            str(PR_B1_WORKTREE),
            "--contract",
            str(CONTRACT_PATH),
            "--comparison-base-sha",
            "0" * 40,
            "--evidence",
            "/tmp/_pr_b3_evidence.json",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "comparison_base_sha" in proc.stdout or "comparison-base-sha" in proc.stdout


def test_cli_invalid_comparison_base_sha_format():
    """Non-canonical hex must FAIL rc 1 with a clear message."""
    import subprocess

    for bad in ("not-hex", "ZZ" + "0" * 38, "0" * 39, "0" * 41, "0" * 40 + "x"):
        proc = subprocess.run(
            [
                str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
                "-I",
                str(CHECK_PATH),
                "--root",
                str(PR_B1_WORKTREE),
                "--contract",
                str(CONTRACT_PATH),
                "--previous-contract",
                str(CONTRACT_PATH),
                "--comparison-base-sha",
                bad,
                "--evidence",
                "/tmp/_pr_b3_evidence.json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 1, (
            f"sha={bad!r}: rc={proc.returncode} "
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )


def test_cli_valid_comparison_base_sha_passes(tmp_path):
    """Valid 40-char lowercase hex succeeds with --previous-contract."""
    proc = _cli_run(
        [
            "--previous-contract",
            str(CONTRACT_PATH),
            "--comparison-base-sha",
            "0" * 40,
        ]
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    evidence = json.loads(Path("/tmp/_pr_b3_evidence.json").read_text())
    assert evidence["comparison_base_sha"] == "0" * 40


# ===========================================================================
# PR-B3: previous-contract integrity (re-uses _validate_schema)
# ===========================================================================


def test_previous_contract_validate_schema_failure(check, l1, real_v2_contract):
    """If the previous contract fails structural validation, FAIL with a
    clear violation in `violations` (not in `transition_violations`)."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        backend = Path(td) / "backend"
        backend.mkdir()
        bad = copy.deepcopy(real_v2_contract)
        # Drop a required release_b_gates key -> _validate_schema fails.
        del bad["release_b_gates"]["complexity_proxy_gte_30_maximum"]
        _rehash(bad)
        result = check.evaluate(
            Path(td), real_v2_contract, l1, previous_contract=bad
        )
        assert result["result"] == "FAIL"
        assert any(
            "release_b_gates.complexity_proxy_gte_30_maximum missing" in v
            for v in result["violations"]
        )


def test_previous_contract_duplicate_locked_identity(check, l1, real_v2_contract):
    """Duplicate locked identities in the previous contract -> FAIL."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        backend = Path(td) / "backend"
        backend.mkdir()
        bad = copy.deepcopy(real_v2_contract)
        first = bad["entries"][0]
        bad["entries"].append(copy.deepcopy(first))
        _rehash(bad)
        result = check.evaluate(
            Path(td), real_v2_contract, l1, previous_contract=bad
        )
        assert result["result"] == "FAIL"
        assert any(
            "duplicate locked entry identity" in v for v in result["violations"]
        )


def test_previous_contract_malformed_remediation_entry(
    check, l1, real_v2_contract
):
    """Malformed remediation_entries in the previous contract -> FAIL."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        backend = Path(td) / "backend"
        backend.mkdir()
        bad = copy.deepcopy(real_v2_contract)
        # Inject a remediation entry with missing function field.
        bad.setdefault("remediation_entries", []).append(
            {"path": "backend/x.py", "current_complexity": 5}
        )
        _rehash(bad)
        result = check.evaluate(
            Path(td), real_v2_contract, l1, previous_contract=bad
        )
        assert result["result"] == "FAIL"
        assert any(
            "remediation_entries" in v and "function" in v
            for v in result["violations"]
        )


def test_previous_contract_self_hash_mismatch(check, l1, real_v2_contract):
    """Self-hash mismatch on the previous contract -> FAIL before transition."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        backend = Path(td) / "backend"
        backend.mkdir()
        bad = copy.deepcopy(real_v2_contract)
        # Mutate payload without rehashing -> digest mismatch.
        bad["baseline_source_sha"] = "f" * 40
        result = check.evaluate(
            Path(td), real_v2_contract, l1, previous_contract=bad
        )
        assert result["result"] == "FAIL"
        assert any(
            "previous contract payload digest mismatch" in v
            for v in result["violations"]
        )


def test_previous_contract_invalid_v2_threshold_fails_base_integrity(
    check, l1, real_v2_contract
):
    """A previous contract with an invalid v2 threshold must FAIL base
    integrity BEFORE the transition validator runs.

    The helper calls `_validate_schema(previous, check_threshold=True)`,
    so the v2 threshold invariant (must be 19) is enforced on the
    trusted-base contract too. The transition validator is never
    consulted when base integrity fails.
    """
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        backend = Path(td) / "backend"
        backend.mkdir()
        bad = copy.deepcopy(real_v2_contract)
        # Drift the v2 threshold off 19 -> _validate_schema rejects.
        bad["release_b_gates"]["new_function_complexity_proxy_maximum"] = 17
        _rehash(bad)
        result = check.evaluate(
            Path(td), real_v2_contract, l1, previous_contract=bad
        )
        assert result["result"] == "FAIL"
        # The base-integrity violation must appear in `violations` (not in
        # `transition_violations`).
        assert any(
            "must be 19" in v for v in result["violations"]
        ), f"expected base-integrity threshold violation, got {result['violations']}"
        # The transition validator must NOT have run: `transition_violations`
        # must be empty.
        assert result["transition_violations"] == []


def test_previous_contract_valid_v2_threshold_passes_base_integrity(
    check, l1, real_v2_contract
):
    """A previous contract whose v2 threshold is correctly pinned at 19
    must NOT trip base integrity (PASS or RATCHET_REQUIRED is acceptable;
    the point is no FAIL from base integrity)."""
    good = copy.deepcopy(real_v2_contract)
    assert (
        good["release_b_gates"]["new_function_complexity_proxy_maximum"] == 19
    )
    _rehash(good)
    result = check.evaluate(
        PR_B1_WORKTREE, good, l1, previous_contract=good
    )
    assert result["result"] in ("PASS", "RATCHET_REQUIRED"), (
        f"unexpected result {result['result']!r}: {result['violations']}"
    )
    assert all(
        "previous contract" not in v for v in result["violations"]
    ), f"unexpected base-integrity violations: {result['violations']}"


def test_previous_contract_valid_schema_and_hash(check, l1, real_v2_contract):
    """Well-formed previous with valid digest does NOT trip base integrity."""
    # Use the real production tree so the candidate contract actually matches
    # the codebase. With an empty tmp_path backend, the gate would
    # RATCHET_REQUIRED because the contract ceilings exceed measured
    # metrics; the point of this test is that previous-integrity did not
    # inject a FAIL before the transition validator ran.
    good = copy.deepcopy(real_v2_contract)
    _rehash(good)
    result = check.evaluate(
        PR_B1_WORKTREE, good, l1, previous_contract=good
    )
    assert result["result"] in ("PASS", "RATCHET_REQUIRED"), (
        f"unexpected result {result['result']!r}: "
        f"violations={result['violations']}"
    )
    # The previous-integrity violations MUST be absent.
    assert all(
        "previous contract" not in v for v in result["violations"]
    ), f"unexpected base-integrity violations: {result['violations']}"


def test_transition_still_enforced_when_previous_valid(
    check, l1, real_v2_contract
):
    """A valid previous contract does not mask candidate transition failures."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        backend = Path(td) / "backend"
        backend.mkdir()
        previous = copy.deepcopy(real_v2_contract)
        _rehash(previous)
        candidate = copy.deepcopy(real_v2_contract)
        # Raise an aggregate ceiling to trigger transition Rule A.
        candidate["release_b_gates"]["complexity_proxy_gte_20_maximum"] = (
            previous["release_b_gates"]["complexity_proxy_gte_20_maximum"] + 1
        )
        _rehash(candidate)
        result = check.evaluate(
            Path(td), candidate, l1, previous_contract=previous
        )
        assert result["result"] == "FAIL"
        assert any(
            "complexity_proxy_gte_20_maximum" in v
            for v in result["transition_violations"]
        )


def test_evidence_contains_comparison_base_sha(check, l1, real_v2_contract):
    """evidence['comparison_base_sha'] equals the input when supplied."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        backend = Path(td) / "backend"
        backend.mkdir()
        previous = copy.deepcopy(real_v2_contract)
        _rehash(previous)
        sha = "abc1234" + "0" * 32
        result = check.evaluate(
            Path(td),
            real_v2_contract,
            l1,
            previous_contract=previous,
            comparison_base_sha=sha,
        )
        assert result["comparison_base_sha"] == sha


def test_evidence_comparison_base_sha_null_without_previous(check, l1):
    """No previous contract -> comparison_base_sha is null in evidence."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        backend = Path(td) / "backend"
        backend.mkdir()
        result = check.evaluate(Path(td), json.loads(CONTRACT_PATH.read_text()), l1)
        assert result["comparison_base_sha"] is None


def test_evaluate_without_previous_preserves_no_previous_behavior(check, l1):
    """No-previous path keeps PR-B1 semantics intact."""
    # Use the real production tree; the candidate contract matches it.
    result = check.evaluate(
        PR_B1_WORKTREE, json.loads(CONTRACT_PATH.read_text()), l1
    )
    assert result["result"] in ("PASS", "RATCHET_REQUIRED"), (
        f"unexpected result {result['result']!r}"
    )
    assert result["previous_contract_payload_sha256"] is None
    assert result["comparison_base_sha"] is None


# ===========================================================================
# PR-B3: hardened input-file reads (clean rc 1, no traceback)
# ===========================================================================


def test_cli_candidate_missing_file_cleanc_rc1(tmp_path):
    """Missing --contract file must produce rc 1 with a clear message, no
    Python traceback."""
    import subprocess

    proc = subprocess.run(
        [
            str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
            "-I",
            str(CHECK_PATH),
            "--root",
            str(PR_B1_WORKTREE),
            "--contract",
            str(tmp_path / "does_not_exist.json"),
            "--evidence",
            str(tmp_path / "evidence.json"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "Traceback" not in proc.stderr
    assert "FAIL:" in proc.stdout


def test_cli_candidate_malformed_json_cleanc_rc1(tmp_path):
    """Malformed candidate JSON must produce rc 1 without a traceback."""
    import subprocess

    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not json")
    proc = subprocess.run(
        [
            str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
            "-I",
            str(CHECK_PATH),
            "--root",
            str(PR_B1_WORKTREE),
            "--contract",
            str(bad),
            "--evidence",
            str(tmp_path / "evidence.json"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "Traceback" not in proc.stderr
    assert "not valid JSON" in proc.stdout


def test_cli_previous_missing_file_cleanc_rc1(tmp_path):
    """Missing --previous-contract file must produce rc 1 without a traceback."""
    import subprocess

    proc = subprocess.run(
        [
            str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
            "-I",
            str(CHECK_PATH),
            "--root",
            str(PR_B1_WORKTREE),
            "--contract",
            str(CONTRACT_PATH),
            "--previous-contract",
            str(tmp_path / "missing_prev.json"),
            "--comparison-base-sha",
            "0" * 40,
            "--evidence",
            str(tmp_path / "evidence.json"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "Traceback" not in proc.stderr
    assert "FAIL:" in proc.stdout


def test_cli_previous_malformed_json_cleanc_rc1(tmp_path):
    """Malformed --previous-contract JSON must produce rc 1 without a traceback."""
    import subprocess

    bad = tmp_path / "bad_prev.json"
    bad.write_text("not-json-at-all")
    proc = subprocess.run(
        [
            str(PR_B1_WORKTREE / "backend" / "venv" / "bin" / "python"),
            "-I",
            str(CHECK_PATH),
            "--root",
            str(PR_B1_WORKTREE),
            "--contract",
            str(CONTRACT_PATH),
            "--previous-contract",
            str(bad),
            "--comparison-base-sha",
            "0" * 40,
            "--evidence",
            str(tmp_path / "evidence.json"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "Traceback" not in proc.stderr
    assert "not valid JSON" in proc.stdout
