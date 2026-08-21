"""Tests for the shared Python AST-complexity metric module (L1).

These tests verify:
  - the public API surface exposed by scripts/_python_complexity.py;
  - the exact metric semantics preserved from exact-main
    76a71d9bcf339385712ae1207824624af603a12f
    (scripts/check_python_complexity_contract.py and
     scripts/check_changed_function_complexity.py);
  - python -I exact-path importability via
    importlib.util.spec_from_file_location;
  - fail-closed behavior when L1 is absent.

Zero drift is enforced by collecting metrics from the production
tree using L1 and comparing against the preserved reference
implementation. The reference uses the same algorithm shape that
was live at exact-main; we compare identity, start line, end line,
and complexity for every production function.

Current Target Calculator complexity characterization:
    build_target_excel          = 1
    populate_profitability      = 16
    manager_allocation_analysis = 10
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# L1 loading and discovery
# ---------------------------------------------------------------------------


PR_B1_WORKTREE = Path(__file__).resolve().parents[2]
L1_PATH = PR_B1_WORKTREE / "scripts" / "_python_complexity.py"


def _load_l1():
    """Load L1 by exact trusted sibling path, matching how
    scripts/check_python_complexity_contract.py loads it.

    Fails the test (not silently swallows) if L1 is absent or
    malformed.
    """
    assert L1_PATH.is_file(), f"L1 module missing at {L1_PATH}"
    spec = importlib.util.spec_from_file_location(
        "_unihub_python_complexity_l1", str(L1_PATH)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def l1():
    return _load_l1()


# ---------------------------------------------------------------------------
# Reference implementation (preserved from exact-main)
# ---------------------------------------------------------------------------


# Inline copy of the COUNTED_NODES set from exact-main
# scripts/check_python_complexity_contract.py and
# scripts/check_changed_function_complexity.py at SHA
# 76a71d9bcf339385712ae1207824624af603a12f.
#
# This set is duplicated here ONLY so the zero-drift test compares L1
# against the previous implementation rather than against itself.
REFERENCE_COUNTED_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.IfExp,
    ast.Assert,
    ast.comprehension,
    ast.Match,
    ast.ExceptHandler,
)


def reference_score(node: ast.AST) -> int:
    """The exact pre-PR-B1 scoring algorithm.

    Walks descendants with ast.walk (descends into nested bodies),
    starts at 1, increments by 1 for each descendant whose type is
    in REFERENCE_COUNTED_NODES, and for ast.BoolOp descendants
    increments by max(1, len(values) - 1).
    """
    score = 1
    for child in ast.walk(node):
        if isinstance(child, REFERENCE_COUNTED_NODES):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(1, len(child.values) - 1)
    return score


def reference_metrics(source: str, path: str) -> list:
    """The exact pre-PR-B1 function-metric enumeration."""
    tree = ast.parse(source, filename=path)
    out = []

    def visit(body, prefix=()):
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*prefix, node.name))
                continue
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            function = ".".join((*prefix, node.name))
            end_line = node.end_lineno or node.lineno
            from dataclasses import dataclass

            @dataclass(frozen=True, slots=True)
            class _M:
                path: str
                function: str
                start_line: int
                end_line: int
                line_count: int
                complexity_proxy: int

            out.append(
                _M(
                    path=path,
                    function=function,
                    start_line=node.lineno,
                    end_line=end_line,
                    line_count=end_line - node.lineno + 1,
                    complexity_proxy=reference_score(node),
                )
            )
            visit(node.body, (*prefix, node.name, "<locals>"))

    visit(tree.body)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_counted_nodes_constant_has_13_types(l1):
    """COUNTED_NODES lists exactly the 13 control-flow AST node types.

    BoolOp is scored separately via the elif branch in score() and is
    NOT in COUNTED_NODES.
    """
    assert isinstance(l1.COUNTED_NODES, tuple)
    assert len(l1.COUNTED_NODES) == 13
    expected = {
        "If",
        "For",
        "AsyncFor",
        "While",
        "Try",
        "TryStar",
        "With",
        "AsyncWith",
        "IfExp",
        "Assert",
        "comprehension",
        "Match",
        "ExceptHandler",
    }
    assert set(l1.COUNTED_NODES) == expected


def test_algorithm_descriptor_exposed(l1):
    """L1 must expose ALGORITHM_NAME, ALGORITHM_VERSION, and
    algorithm_spec() so the contract can pin the metric algorithm."""
    assert l1.ALGORITHM_NAME == "python_complexity_proxy_v1"
    assert isinstance(l1.ALGORITHM_VERSION, str) and l1.ALGORITHM_VERSION
    spec = l1.algorithm_spec()
    assert spec["initial_score"] == 1
    assert list(spec["counted_nodes"]) == list(l1.COUNTED_NODES)
    assert spec["bool_op"] == "max(1,len(values)-1)"
    assert spec["walk"] == "ast.walk_including_nested_bodies"
    # Mutating the returned dict must not affect subsequent calls.
    spec["counted_nodes"].append("MUTATED")
    spec2 = l1.algorithm_spec()
    assert spec2["counted_nodes"][-1] != "MUTATED"


def test_score_zero_input_rejected(l1):
    with pytest.raises(TypeError):
        l1.score(None)


def test_score_trivial_function_is_one(l1):
    tree = ast.parse("def f():\n    return 1\n")
    assert l1.score(tree.body[0]) == 1


def test_score_async_function_trivial_is_one(l1):
    tree = ast.parse("async def f():\n    return 1\n")
    assert l1.score(tree.body[0]) == 1


def test_score_increments_for_each_if(l1):
    src = """
def f(x):
    if x:
        return 1
    if x:
        return 2
    if x:
        return 3
    return 0
"""
    tree = ast.parse(src)
    assert l1.score(tree.body[0]) == 4  # 1 + 3 ifs


def test_score_boolop_two_arg(l1):
    src = """
def f(a, b):
    if a and b:
        return 1
    return 0
"""
    tree = ast.parse(src)
    # 1 (base) + 1 (If) + 1 (BoolOp with 2 values -> +1) = 3
    assert l1.score(tree.body[0]) == 3


def test_score_boolop_three_arg(l1):
    src = """
def f(a, b, c):
    if a and b and c:
        return 1
    return 0
"""
    tree = ast.parse(src)
    # 1 + 1 (If) + 2 (BoolOp with 3 values -> +2) = 4
    assert l1.score(tree.body[0]) == 4


def test_score_walks_nested_function_bodies(l1):
    """ast.walk descends into nested function/class bodies by design;
    this is preserved. Note that FunctionDef nodes themselves do NOT
    contribute (only their inner control-flow nodes do, via the walk).
    """
    src = """
def outer():
    def inner():
        if x:
            return 1
        elif y:
            return 2
        return 3
    return inner()
"""
    tree = ast.parse(src)
    # ast.walk from outer: inner If (x) +1, inner elif (y) +1
    # FunctionDef nodes do not match any type name in COUNTED_NODES.
    # So: 1 (base) + 1 (If x) + 1 (elif y) = 3
    assert l1.score(tree.body[0]) == 3


def test_score_matches_reference_on_nested(l1):
    """L1 score must match reference on nested functions."""
    src = """
def outer():
    def inner():
        if x:
            return 1
        elif y:
            return 2
        return 3
    return inner()
"""
    tree = ast.parse(src)
    assert l1.score(tree.body[0]) == reference_score(tree.body[0])


def test_score_matches_reference_for_all_kinds(l1):
    """L1 score must match reference on a synthetic function that
    exercises every node type in COUNTED_NODES + BoolOp."""
    src = """
def f(xs, ys, zs):
    if xs:
        pass
    for x in xs:
        pass
    async for x in xs:
        pass
    while xs:
        pass
    try:
        pass
    except Exception:
        pass
    try:
        pass
    except* Exception:
        pass
    with xs as g:
        pass
    async with xs as g:
        pass
    z = 1 if xs else 0
    assert xs
    [x for x in xs]
    match xs:
        case 1:
            pass
    return xs and ys and zs
"""
    tree = ast.parse(src)
    assert l1.score(tree.body[0]) == reference_score(tree.body[0])


def test_function_metrics_class_method_identity(l1):
    src = """
class C:
    def m(self):
        return 1
"""
    metrics = l1.function_metrics(src, "x.py")
    assert len(metrics) == 1
    assert metrics[0].function == "C.m"
    assert metrics[0].path == "x.py"


def test_function_metrics_nested_locals_identity(l1):
    src = """
def outer():
    def inner():
        return 1
    return inner
"""
    metrics = l1.function_metrics(src, "x.py")
    names = [m.function for m in metrics]
    assert "outer" in names
    assert "outer.<locals>.inner" in names


def test_function_metrics_start_end_lines(l1):
    src = """
def f():
    if x:
        return 1
    return 0
"""
    metrics = l1.function_metrics(src, "x.py")
    assert len(metrics) == 1
    m = metrics[0]
    assert m.start_line == 2
    assert m.end_line == 5
    assert m.line_count == 4


def test_function_metrics_async_function(l1):
    src = """
async def f():
    return 1
"""
    metrics = l1.function_metrics(src, "x.py")
    assert len(metrics) == 1
    assert metrics[0].function == "f"
    assert metrics[0].complexity_proxy == 1


def test_function_metrics_zero_drift_against_reference(l1):
    """Every production file's metrics must match the reference
    exactly across identity, start_line, end_line, complexity.
    """
    root = PR_B1_WORKTREE
    backend = root / "backend"
    EXCLUDED = {"tests", "venv", ".venv", "__pycache__"}
    total = 0
    drift: list = []
    for path in sorted(backend.rglob("*.py")):
        rel = path.relative_to(root)
        if not path.is_file():
            continue
        if any(part in EXCLUDED for part in rel.parts):
            continue
        text = path.read_text(encoding="utf-8")
        rel_str = rel.as_posix()
        l1_metrics = l1.function_metrics(text, rel_str)
        ref_metrics = reference_metrics(text, rel_str)
        assert len(l1_metrics) == len(ref_metrics), (
            f"count drift in {rel_str}: l1={len(l1_metrics)} ref={len(ref_metrics)}"
        )
        for a, b in zip(l1_metrics, ref_metrics):
            if (
                a.path != b.path
                or a.function != b.function
                or a.start_line != b.start_line
                or a.end_line != b.end_line
                or a.complexity_proxy != b.complexity_proxy
            ):
                drift.append((a, b))
        total += len(l1_metrics)
    assert drift == [], f"zero-drift invariant violated: {drift[:3]}"
    assert total > 0, "no production functions measured"


def test_zero_drift_across_all_production_functions(l1):
    """Hotspot check: known hotspots must match exactly."""
    metrics = l1.collect_metrics(PR_B1_WORKTREE)
    by_identity = {(m.path, m.function): m for m in metrics}
    expected = [
        (
            "backend/services/target_calculator/export.py",
            "build_target_excel",
            1,
        ),
        (
            "backend/services/target_calculator/profitability.py",
            "populate_profitability",
            16,
        ),
        (
            "backend/services/target_calculator/manager_allocation.py",
            "manager_allocation_analysis",
            10,
        ),
    ]
    for path, function, expected_cp in expected:
        m = by_identity.get((path, function))
        assert m is not None, f"missing hotspot: {path}::{function}"
        assert m.complexity_proxy == expected_cp, (
            f"hotspot drift: {path}::{function} "
            f"expected={expected_cp} got={m.complexity_proxy}"
        )


def test_total_production_function_count_is_2963(l1):
    """Production tree must contain exactly 2963 measured functions.

    The C6 Target Calculator repository decomposition intentionally
    adds 8 focused helper functions (+2 in target_calculator_sources.py,
    +3 in target_calculator_scenarios.py, +3 in target_calculator_detail.py);
    baseline moved from 2953 to 2961. The C7 Campaigns service decomposition
    adds 2 focused helper functions in backend/services/campaigns/ to
    preserve the architecture ratchet facade while splitting the loader path;
    baseline moved from 2961 to 2963. The function count ratchet remains
    monotonic — no unrelated functions were added elsewhere.
    """
    metrics = l1.collect_metrics(PR_B1_WORKTREE)
    assert len(metrics) == 2963, (
        f"production count drift: expected 2963, got {len(metrics)}"
    )


def test_import_under_dash_i():
    """L1 must import successfully under `python -I` from this test
    file's invocation context. We simulate by re-loading via
    spec_from_file_location with a fresh importlib context."""
    # The pytest harness is unlikely to be invoked with -I, but the
    # spec_from_file_location mechanism that the contract check uses
    # is the same one we use to load L1 here. We assert that
    # loading via spec_from_file_location (the exact mechanism
    # documented in the contract check) works.
    spec = importlib.util.spec_from_file_location(
        "_l1_dash_i_check", str(L1_PATH)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
        # Public surface check
        assert callable(mod.score)
        assert callable(mod.collect_metrics)
        assert callable(mod.function_metrics)
        assert isinstance(mod.COUNTED_NODES, tuple)
        assert mod.FunctionMetric is not None
    finally:
        sys.modules.pop(spec.name, None)


def test_load_l1_fail_closed_when_missing(tmp_path, monkeypatch):
    """If the L1 file is absent, the contract-check loader raises
    L1LoadError (subclass of RuntimeError), not silently importing
    something else.
    """
    # Move the existing L1 out of the way by pointing the script
    # at a directory where the sibling is missing.
    fake_root = tmp_path / "scripts"
    fake_root.mkdir()
    check_mod_path = PR_B1_WORKTREE / "scripts" / "check_python_complexity_contract.py"
    # Patch L1_PATH to a non-existent sibling and call _load_l1 directly
    import importlib.util
    sys.path.insert(0, str(PR_B1_WORKTREE / "scripts"))
    try:
        check_mod = importlib.import_module("check_python_complexity_contract")
        original_l1_path = check_mod.L1_PATH
        monkeypatch.setattr(check_mod, "L1_PATH", fake_root / "_python_complexity.py")
        with pytest.raises(check_mod.L1LoadError):
            check_mod._load_l1()
    finally:
        sys.path.pop(0)
