"""Tests for the monotonic Python complexity contract v2.

These tests verify the contract-check script's three-state result
(PASS / FAIL / RATCHET_REQUIRED) and the optional --previous-contract
monotonic transition validator against the 21 cases the reviewer
specified. Most cases build synthetic contracts on a temp tree
so the production tree is not modified.
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
    """Deep-copy a contract and set a value at a nested path.

    path_segments is a tuple/list of dict keys.
    """
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


def _baseline_gates() -> dict:
    return {
        "complexity_proxy_gte_20_maximum": 33,
        "complexity_proxy_gte_30_maximum": 3,
        "maximum_complexity_proxy": 62,
        "new_function_complexity_proxy_maximum": 19,
        "wp11_locked_entries_maximum": 0,
        "mandatory_locked_gte_30_maximum": 3,
    }


def _gates_for(actual_max: int, actual_gte_20: int = 0) -> dict:
    """Build release_b_gates that match the synthetic code exactly.

    Use this for tightening/PASS tests where the contract must equal
    the actual code (so the ratchet logic does not fire on the
    global gate).
    """
    return {
        "complexity_proxy_gte_20_maximum": actual_gte_20,
        "complexity_proxy_gte_30_maximum": 0,
        "maximum_complexity_proxy": actual_max,
        "new_function_complexity_proxy_maximum": 19,
        "wp11_locked_entries_maximum": 0,
        "mandatory_locked_gte_30_maximum": 0,
    }


def _baseline_history() -> dict:
    return {"v1": {"version": 1, "baseline_source_sha": "placeholder"}}


# ---------------------------------------------------------------------------
# 1. PASS on exact-main
# ---------------------------------------------------------------------------


def test_case_1_pass_on_exact_main(check, l1, real_v2_contract):
    result = check.evaluate(PR_B1_WORKTREE, real_v2_contract, l1)
    assert result["result"] == "PASS"
    assert result["metrics"]["production_functions"] == 2935
    assert result["metrics"]["complexity_proxy_gte_20"] == 33
    assert result["metrics"]["complexity_proxy_gte_30"] == 3
    assert result["metrics"]["maximum_complexity_proxy"] == 62


# ---------------------------------------------------------------------------
# 2. New function with cp=20 should FAIL
# ---------------------------------------------------------------------------


def test_case_2_new_function_cp_20_fails(check, l1, tmp_path):
    """Build a synthetic root with one new cp=20 function; v2 contract
    must FAIL because new_function_complexity_proxy_maximum=19."""
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
    # Verify cp=20 with L1
    spec = importlib.util.spec_from_file_location("_t", str(L1_PATH))
    _l1 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = _l1
    spec.loader.exec_module(_l1)
    metrics = _l1.function_metrics(body, "backend/new_hot.py")
    assert metrics[0].complexity_proxy == 20

    contract = {
        "version": 2,
        "release_b_gates": _baseline_gates(),
        "history": _baseline_history(),
        "entries": [],
    }
    _rehash(contract)
    result = check.evaluate(tmp_path, contract, l1)
    assert result["result"] == "FAIL"
    assert any("new_hot" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# 3. aggregate gte_20 33 -> 34 FAIL (transition validator)
# ---------------------------------------------------------------------------


def test_case_3_aggregate_gte_20_increase_fails(check, l1, real_v2_contract):
    """Weakening the aggregate gte_20 limit must FAIL the
    monotonic transition validator."""
    previous = copy.deepcopy(real_v2_contract)
    candidate = _set_path(
        real_v2_contract,
        ("release_b_gates", "complexity_proxy_gte_20_maximum"),
        34,
    )
    _rehash(candidate)
    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("gte_20" in v and "34" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 4. aggregate gte_30 3 -> 4 FAIL (transition validator)
# ---------------------------------------------------------------------------


def test_case_4_aggregate_gte_30_increase_fails(check, l1, real_v2_contract):
    previous = copy.deepcopy(real_v2_contract)
    candidate = _set_path(
        real_v2_contract,
        ("release_b_gates", "complexity_proxy_gte_30_maximum"),
        4,
    )
    _rehash(candidate)
    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("gte_30" in v and "4" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 5. max 62 -> 63 FAIL (transition validator)
# ---------------------------------------------------------------------------


def test_case_5_max_increase_fails(check, l1, real_v2_contract):
    previous = copy.deepcopy(real_v2_contract)
    candidate = _set_path(
        real_v2_contract,
        ("release_b_gates", "maximum_complexity_proxy"),
        63,
    )
    _rehash(candidate)
    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("maximum" in v and "63" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 6. existing entry exceeds its ceiling FAIL
# ---------------------------------------------------------------------------


def test_case_6_entry_exceeds_ceiling_fails(check, l1, real_v2_contract):
    """Lower build_target_excel's ceiling to 60. Actual is 62 -> FAIL."""
    contract = copy.deepcopy(real_v2_contract)
    for entry in contract["entries"]:
        if entry["function"] == "build_target_excel":
            entry["ceiling"] = 60
    _rehash(contract)
    result = check.evaluate(PR_B1_WORKTREE, contract, l1)
    assert result["result"] == "FAIL"
    assert any("build_target_excel" in v for v in result["entry_violations"])


# ---------------------------------------------------------------------------
# 7. code improves but contract remains stale -> RATCHET_REQUIRED rc=2
# ---------------------------------------------------------------------------


def test_case_7_ratchet_required_when_code_better(check, l1, real_v2_contract):
    """Loosen contract ceiling + max so code is strictly better -> ratchet."""
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
    """Default v2 contract matches current main: PASS."""
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
    # cp=24 (1 base + 23 Ifs)
    fn_path.write_text(
        "def f(x):\n"
        + "    if x:\n        return 1\n" * 23
        + "    return 0\n"
    )

    contract = {
        "version": 2,
        "release_b_gates": _baseline_gates(),
        "history": _baseline_history(),
        "entries": [
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 24,
                "ceiling": 22,  # tightened from 25 to 22
            }
        ],
    }
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
    # cp=20 (1 base + 19 Ifs)
    fn_path.write_text(
        "def f(x):\n"
        + "    if x:\n        return 1\n" * 19
        + "    return 0\n"
    )

    contract = {
        "version": 2,
        "release_b_gates": _baseline_gates(),
        "history": _baseline_history(),
        "entries": [
            {
                "path": "backend/b.py",
                "function": "f",
                "current_complexity": 20,
                "ceiling": 19,  # tightened
            }
        ],
    }
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

    previous = {
        "version": 2,
        "release_b_gates": _baseline_gates(),
        "history": _baseline_history(),
        "entries": [
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 22,
                "ceiling": 22,
            }
        ],
    }
    candidate = copy.deepcopy(previous)
    candidate["entries"][0]["ceiling"] = 24  # loosening
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
    previous = {
        "version": 2,
        "release_b_gates": _baseline_gates(),
        "history": _baseline_history(),
        "entries": [],
    }
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
    previous = {
        "version": 2,
        "release_b_gates": _baseline_gates(),
        "history": _baseline_history(),
        "entries": [],
    }
    candidate = copy.deepcopy(previous)
    candidate["release_b_gates"]["new_function_complexity_proxy_maximum"] = 20
    _rehash(candidate)

    result = check.evaluate(
        tmp_path, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("new-function" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 14. history rewrite FAIL
# ---------------------------------------------------------------------------


def test_case_14_history_rewrite_fails(check, l1, tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    previous = {
        "version": 2,
        "history": {"v1": {"version": 1, "baseline_source_sha": "abc"}},
        "release_b_gates": _baseline_gates(),
        "entries": [],
    }
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
    previous = {
        "version": 2,
        "history": {"v1": {"version": 1, "baseline_source_sha": "abc"}},
        "release_b_gates": _gates_for(actual_max=0, actual_gte_20=0),
        "entries": [],
    }
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
    # cp=22 (1 base + 21 Ifs)
    fn_path.write_text(
        "def f(x):\n"
        + "    if x:\n        return 1\n" * 21
        + "    return 0\n"
    )
    previous = {
        "version": 2,
        "release_b_gates": _gates_for(actual_max=22, actual_gte_20=1),
        "history": _baseline_history(),
        "entries": [
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 22,
                "ceiling": 25,  # looser
            }
        ],
    }
    candidate = copy.deepcopy(previous)
    candidate["entries"][0]["ceiling"] = 22  # tightened from 25 to 22
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
        e for e in candidate["entries"] if e["function"] != "build_target_excel"
    ]
    _rehash(candidate)

    result = check.evaluate(
        PR_B1_WORKTREE, candidate, l1, previous_contract=previous
    )
    assert result["result"] == "FAIL"
    assert any("build_target_excel" in v for v in result["transition_violations"])


# ---------------------------------------------------------------------------
# 18. remove locked entry after function <20 PASS (improvement)
# ---------------------------------------------------------------------------


def test_case_18_locked_entry_removal_after_improvement_passes(
    check, l1, tmp_path
):
    backend = tmp_path / "backend"
    backend.mkdir()
    fn_path = backend / "mod.py"
    fn_path.write_text("def f(x):\n    return 1\n")  # cp=1, below 20

    previous = {
        "version": 2,
        "release_b_gates": _gates_for(actual_max=1, actual_gte_20=0),
        "history": _baseline_history(),
        "entries": [
            {
                "path": "backend/mod.py",
                "function": "f",
                "current_complexity": 22,
                "ceiling": 22,
            }
        ],
    }
    candidate = copy.deepcopy(previous)
    candidate["entries"] = []  # removed; current cp=1 below 20 -> OK
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
    """Pretend 'previous' had no entries. Candidate adds an entry for
    build_target_excel (which is at cp=62 currently). The transition
    validator must flag this as laundering because the function was
    not in the previous >=20 locked set."""
    previous = {
        "version": 2,
        "release_b_gates": real_v2_contract["release_b_gates"],
        "history": real_v2_contract["history"],
        "entries": [],  # No previous entries
    }
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
    # Wrong hash
    bad = copy.deepcopy(real_v2_contract)
    bad["contract_payload_sha256"] = "0" * 64
    result = check.evaluate(PR_B1_WORKTREE, bad, l1)
    assert result["result"] == "FAIL"
    assert any("digest" in v for v in result["violations"])

    # Wrong version
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
    """Running the evaluator must not modify the contract file or
    any other tracked file."""
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


# ---------------------------------------------------------------------------
# CLI / exit-code smoke tests
# ---------------------------------------------------------------------------


def test_cli_pass_returns_rc_0():
    """Run the actual CLI on exact-main; expect rc 0."""
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
    """Run CLI with a strict contract (max=29); expect rc 1."""
    import subprocess

    bad = json.loads(CONTRACT_PATH.read_text())
    bad["release_b_gates"]["maximum_complexity_proxy"] = 29
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
    """Run CLI with a loose contract (max=99, ceiling=99); expect rc 2."""
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
