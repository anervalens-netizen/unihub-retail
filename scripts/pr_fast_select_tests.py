#!/usr/bin/env python3
"""PR-B3a deterministic backend PR test selector.

This script is the PRODUCTION slice of the B3/E2 selector proof. It decides
which backend pytest test nodes must run for a pull request, given:

  * the exact repository state (`--root`, default: script's parent),
  * the base commit (`--base`),
  * the optional `HEAD` tree (default: working tree).

It is intentionally self-contained: there is no cache, no testmon, no
previous-run state, no filename-only authority, no network. It reuses
the existing PR-B2 backend eligibility authority via importlib (we load
`scripts/check_changed_line_coverage.py` from a sibling script path and
call its public predicates). The PR-B2 gate is NOT modified by this PR.

Four-state contract:
    NO_ELIGIBLE_BACKEND_CHANGE  -> exit 0
    SELECTED                    -> exit 0
    ESCALATION_REQUIRED         -> exit 2
    ERROR                       -> exit 3

The selector writes canonical JSON to stdout (one object, schema_version=1).
Human summaries, when needed, go to stderr only. Future CI consumers MUST
parse the JSON, never the human text.

Residual risks documented here (do NOT claim they are solved):
  * F.1  Dynamic-loading code in UNCHANGED files (e.g. importlib.import_module
        inside a still-loaded test) is out of scope. Static analysis cannot
        detect it without running the code. The selector only catches dynamic
        loading that lives inside the CHANGED set.
  * F.2  Composition root uses explicit multi-name imports (verified 2026-08-19
        on backend/composition.py: 0 star imports). A future `from X import *`
        in the composition root would explode the reverse closure; this is
        documented as a coding-rule boundary, not enforced by this script.

This is the B3a slice only. Wiring `pr-fast` and the future `PR-DEEP`
workflow happens in PR-B3b in a separate, additive change.
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

STATE_NO_ELIGIBLE = "NO_ELIGIBLE_BACKEND_CHANGE"
STATE_SELECTED = "SELECTED"
STATE_ESCALATION = "ESCALATION_REQUIRED"
STATE_ERROR = "ERROR"

EXIT_OK = 0
EXIT_ESCALATION = 2
EXIT_ERROR = 3


# ---------------------------------------------------------------------------
# Backend tree conventions (mirrors backend/tests/conftest.py sys.path setup)
# ---------------------------------------------------------------------------

BACKEND_ROOT_NAME = "backend"
BACKEND_TREE_SUBDIRS_TO_SKIP = ("/venv/", "/__pycache__/", "/scripts/", "/tests/")
PROD_SUBDIRS_TO_COLLECT = ("services", "routers", "repositories", "schemas",
                           "grile", "domain", "observability", "db")


# ---------------------------------------------------------------------------
# PR-B2 gate authority (loaded by importlib from a sibling script).
# ---------------------------------------------------------------------------

_GATE_PATH = Path(__file__).resolve().parent / "check_changed_line_coverage.py"


def _load_pr_b2_gate():
    """Load scripts/check_changed_line_coverage.py as a trusted sibling.

    The PR-B2 gate is the single source of truth for backend eligibility and
    diff collection. We deliberately do NOT copy its predicates here.
    """
    spec = importlib.util.spec_from_file_location("pr_b2_gate", _GATE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load PR-B2 gate from {_GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class SelectedTest:
    node_id: str
    file: str
    reasons: list

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "file": self.file,
            "reasons": list(self.reasons),
        }


@dataclasses.dataclass
class EscalationReason:
    category: str
    path: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "path": self.path,
            "detail": self.detail,
        }


@dataclasses.dataclass
class SelectionResult:
    state: str
    base: str
    eligible_changed: list = dataclasses.field(default_factory=list)
    impacted_production: list = dataclasses.field(default_factory=list)
    selected_tests: list = dataclasses.field(default_factory=list)
    selection_count: int = 0
    escalation_reasons: list = dataclasses.field(default_factory=list)
    errors: list = dataclasses.field(default_factory=list)
    diagnostics: list = dataclasses.field(default_factory=list)
    notes: list = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "state": self.state,
            "base_sha": self.base,
            "eligible_changed": list(self.eligible_changed),
            "changed_tests": [
                t.file for t in self.selected_tests
                if any("self_change" in r for r in t.reasons)
            ],
            "impacted_production": list(self.impacted_production),
            "selected_tests": [t.to_dict() for t in self.selected_tests],
            "selection_count": self.selection_count,
            "escalation_reasons": [
                r.to_dict() if hasattr(r, "to_dict") else r
                for r in self.escalation_reasons
            ],
            "errors": list(self.errors),
            "diagnostics": list(self.diagnostics),
            "notes": list(self.notes),
        }


def exit_code_for(state: str) -> int:
    return {
        STATE_NO_ELIGIBLE: EXIT_OK,
        STATE_SELECTED: EXIT_OK,
        STATE_ESCALATION: EXIT_ESCALATION,
        STATE_ERROR: EXIT_ERROR,
    }.get(state, EXIT_ERROR)


# ---------------------------------------------------------------------------
# Module <-> file mapping helpers
# ---------------------------------------------------------------------------


def _file_to_module(rel_path: str) -> str | None:
    """Map a repo-relative backend path to its Python dotted module name.

    Examples (relative to repo root):
        backend/services/asm_salary.py        -> 'services.asm_salary'
        backend/services/target_calculator/__init__.py
                                            -> 'services.target_calculator'
        backend/grile/api/views.py           -> 'grile.api.views'
        backend/services/__init__.py         -> 'services'
        backend/main.py                      -> 'main'

    Returns None for paths outside backend/ or for untracked parts of the
    backend tree (tests/scripts/venv/__pycache__) which are NOT eligible.
    """
    if not rel_path.startswith(BACKEND_ROOT_NAME + "/"):
        return None
    if not rel_path.endswith(".py"):
        return None
    rel = rel_path[len(BACKEND_ROOT_NAME) + 1:]
    parts = rel.split("/")
    # Drop __pycache__ / venv / scripts / tests as a defense in depth
    if any(p in ("__pycache__", "venv", "scripts", "tests") for p in parts):
        return None
    # Drop __init__ suffix; keep package namespace
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    else:
        return None
    if not parts:
        return None
    return ".".join(parts)


def _module_candidates(module: str) -> list:
    """Repo-relative file paths that could correspond to a dotted module.

    e.g. 'services.foo' -> ['backend/services/foo.py', 'backend/services/foo/__init__.py']
    """
    dotted = module.replace(".", "/")
    return [
        f"{BACKEND_ROOT_NAME}/{dotted}.py",
        f"{BACKEND_ROOT_NAME}/{dotted}/__init__.py",
    ]


def collect_python_files(root: Path) -> dict:
    """Walk the backend tree and return {module: rel_path} for every prod file.

    Production-only: tests/, scripts/, venv/, __pycache__/ are skipped.
    """
    backend = root / BACKEND_ROOT_NAME
    if not backend.is_dir():
        raise FileNotFoundError(f"backend tree missing under {root}")
    file_to_module: dict = {}
    for path in backend.rglob("*.py"):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if any(seg in rel for seg in BACKEND_TREE_SUBDIRS_TO_SKIP):
            continue
        mod = _file_to_module(rel)
        if mod is None:
            continue
        file_to_module.setdefault(mod, rel)
    return file_to_module


def _test_module(rel_path: str) -> str | None:
    """Map a backend/tests/* path to its pytest node id.

    backend/tests/test_asm_salary.py        -> 'tests.test_asm_salary'
    backend/tests/grile/test_x.py           -> 'tests.grile.test_x'
    backend/tests/__init__.py               -> 'tests'
    """
    if not rel_path.startswith(BACKEND_ROOT_NAME + "/tests/"):
        return None
    if not rel_path.endswith(".py"):
        return None
    rel = rel_path[len(BACKEND_ROOT_NAME) + 1:]
    parts = rel.split("/")
    if any(p == "__pycache__" for p in parts):
        return None
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    else:
        return None
    if not parts:
        return None
    return ".".join(parts)


def collect_test_files(root: Path) -> dict:
    """Walk backend/tests/ and return {module: rel_path} for every test file."""
    tests = root / BACKEND_ROOT_NAME / "tests"
    if not tests.is_dir():
        return {}
    out: dict = {}
    for path in tests.rglob("*.py"):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if "/__pycache__/" in rel:
            continue
        mod = _test_module(rel)
        if mod is None:
            continue
        out.setdefault(mod, rel)
    return out


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _snippet(node: ast.AST) -> str:
    """Best-effort source snippet for diagnostics. Safe on unparseable nodes."""
    try:
        text = ast.unparse(node)
    except Exception:
        return "<unparseable>"
    return text.splitlines()[0][:120]


def _is_dynamic_call(node: ast.Call) -> bool:
    """Return True if the AST Call node looks like a dynamic loader.

    Recognized patterns (validated in the B3/E2 proof):
        importlib.import_module('x')
        __import__('x')
        importlib.util.spec_from_file_location('x', path)
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr == "import_module":
            # importlib.import_module OR <x>.import_module (we trust the
            # latter only when <x> is the literal name 'importlib').
            value = func.value
            if isinstance(value, ast.Name) and value.id == "importlib":
                return True
            return False
        if func.attr == "spec_from_file_location":
            value = func.value
            if isinstance(value, ast.Attribute) and value.attr == "util":
                holder = value.value
                if isinstance(holder, ast.Name) and holder.id == "importlib":
                    return True
            return False
    if isinstance(func, ast.Name) and func.id == "__import__":
        return True
    return False


def _resolve_relative_unsafe(level: int, module: str | None,
                             current_parts: list) -> tuple:
    """Resolve a relative import to a dotted module name.

    Returns (resolved_module_or_None, safe_bool).
    `safe_bool == False` means the resolver could not safely determine a
    unique in-tree target. Callers MUST treat unsafe results as
    ESCALATION_REQUIRED (or ERROR, depending on the surrounding invariant).

    Semantics (validated corrected from the prototype):
        level 1, current = a.b.c -> parent (a.b) ; module X -> a.b.X
        level 2, current = a.b.c -> parent (a)   ; module X -> a.X
        level >= len(current_parts): beyond-root  -> (None, False)
        level < 1: not a relative import          -> (None, False)
    """
    if level < 1:
        return None, False
    if level >= len(current_parts):
        return None, False
    base = current_parts[: len(current_parts) - level]
    if module:
        return ".".join(base + [module]), True
    return ".".join(base), True


def _is_known_import(name: str, module_to_files: dict) -> bool:
    """Decide if an imported name maps to a known module in this tree.

    Imports starting with 'services.', 'routers.', etc. are local if the
    corresponding file exists. We do NOT absolutize: the backend tree uses
    its parent on sys.path (see backend/tests/conftest.py), so a bare
    'foo' could be an installed package or a backend sibling. We treat
    'foo' as known only if there is a backend file for it AND it is not
    also a stdlib / common third-party name (the latter is impossible to
    decide deterministically without an importer; the gate's
    eligibility is the safer authority).
    """
    return name in module_to_files


def parse_imports(source: str, current_module: str,
                  module_to_files: dict) -> tuple:
    """Return (set of known imported backend module names, has_dynamic_import).

    Modules outside the backend tree (e.g. fastapi, asyncpg) are ignored.
    Only imports that resolve to a file in our tree (forward-graph edges)
    are returned. Star imports (`from x import *`) are preserved as a
    single edge to x and flagged via has_star_import.
    """
    tree = ast.parse(source)
    known: set = set()
    has_dynamic_import = False
    has_star_import = False
    current_parts = current_module.split(".") if current_module else []

    def visit(node: ast.AST) -> None:
        nonlocal has_dynamic_import, has_star_import
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if _is_known_import(top, module_to_files):
                    known.add(top)
            return
        if isinstance(node, ast.ImportFrom):
            level = node.level or 0
            if level > 0:
                resolved, safe = _resolve_relative_unsafe(
                    level, node.module, current_parts,
                )
                if not safe:
                    # Mark as dynamic so the caller escalates; we treat a
                    # relative beyond-root or unsafe as dynamic for the
                    # purposes of trust.
                    has_dynamic_import = True
                    return
                target = resolved
            else:
                target = node.module
            if not target:
                # `from . import X` style with no module name is treated as
                # a package import — the resolved name is the parent
                # package (see _resolve_relative_unsafe, module=None).
                if level > 0:
                    for child in current_parts:
                        pass  # already resolved
                return
            # Walk the alias list; only add names that resolve in-tree.
            top = target.split(".")[0]
            if not _is_known_import(top, module_to_files):
                # Module not in our tree — ignore; treat whole stmt as
                # external.
                return
            for alias in node.names:
                if alias.name == "*":
                    has_star_import = True
                    known.add(target)
                    continue
                # A 'from x.y import z' edge is x.y; if z is a submodule
                # that also exists in our tree, we add x.y.z too (so
                # facades re-exporting from submodules still propagate).
                edge = f"{target}.{alias.name}"
                if _is_known_import(edge, module_to_files):
                    known.add(edge)
                else:
                    known.add(target)
            return
        if isinstance(node, ast.Call) and _is_dynamic_call(node):
            has_dynamic_import = True
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return known, has_dynamic_import, has_star_import


# ---------------------------------------------------------------------------
# Static graph + reverse closure
# ---------------------------------------------------------------------------


def build_graph(root: Path) -> tuple:
    """Build the forward static-import graph over the backend production tree.

    Returns (file_to_module, prod_forward_edges, test_file_to_module,
             dynamic_files, star_files).
      * file_to_module: {module: rel_path} for production files
      * prod_forward_edges: {module: set(imported_modules)} for production
      * test_file_to_module: {test_module: rel_path} for backend/tests/*
      * dynamic_files: set(rel_path) of files that contain dynamic loaders
      * star_files: set(rel_path) of files that contain star imports

    Test files are indexed separately and are NOT part of the production
    reverse-closure graph; they are consumers of production modules only.
    """
    file_to_module = collect_python_files(root)
    test_file_to_module = collect_test_files(root)
    # The combined module -> file map used by parse_imports so that test
    # imports of prod modules (and vice-versa) both resolve.
    combined = dict(file_to_module)
    combined.update(test_file_to_module)

    forward: dict = {m: set() for m in file_to_module}
    dynamic_files: set = set()
    star_files: set = set()

    for module, rel in file_to_module.items():
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            edges, has_dyn, has_star = parse_imports(
                source, module, combined,
            )
        except SyntaxError:
            # Unparseable production file -> escalate (not the gate's job).
            dynamic_files.add(rel)
            continue
        forward[module].update(edges)
        if has_dyn:
            dynamic_files.add(rel)
        if has_star:
            star_files.add(rel)

    # Also scan test files for dynamic loaders so dynamic detection is
    # complete (the gate caller can then decide per policy).
    for test_module, rel in test_file_to_module.items():
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            _, has_dyn, has_star = parse_imports(
                source, test_module, combined,
            )
        except SyntaxError:
            continue
        if has_dyn:
            dynamic_files.add(rel)
        if has_star:
            star_files.add(rel)

    return file_to_module, forward, test_file_to_module, dynamic_files, star_files


def reverse_prod_graph(forward: dict) -> dict:
    """Invert the forward graph: {module: set(modules that import it)}."""
    reverse: dict = {m: set() for m in forward}
    for src, targets in forward.items():
        for tgt in targets:
            if tgt in reverse:
                reverse[tgt].add(src)
    return reverse


def reverse_closure(starts: Iterable[str], reverse: dict) -> set:
    """BFS over the reverse graph to collect all transitive importers."""
    seen: set = set()
    frontier: list = list(starts)
    while frontier:
        nxt = frontier.pop()
        if nxt in seen:
            continue
        seen.add(nxt)
        for importer in reverse.get(nxt, ()):
            if importer not in seen:
                frontier.append(importer)
    return seen


# ---------------------------------------------------------------------------
# Changed-path classification (escalation surface)
# ---------------------------------------------------------------------------

EXACT_ESCALATION_PATHS = frozenset({
    "backend/conftest.py",
    "backend/tests/conftest.py",
    "requirements.txt",
    "requirements.lock",
    "backend/requirements.txt",
    "backend/requirements.lock",
    "backend/requirements-dev.txt",
    "backend/requirements-dev.lock",
    "backend/architecture_contract.json",
})

_PREFIX_ESCALATION_PATTERNS = (
    re.compile(r"^backend/tests/conftest\..+\.py$"),
    re.compile(r"^backend/.+/conftest\.py$"),
    re.compile(r"^conftest\.py$"),
    re.compile(r"^backend/venv/.*"),
    re.compile(r"^scripts/prototype_b3e2_selector/"),
    re.compile(r"^scripts/pr_fast_select_tests\.py$"),
    re.compile(r"^scripts/check_changed_function_complexity\.py$"),
    re.compile(r"^scripts/check_changed_line_coverage\.py$"),
    re.compile(r"^scripts/_python_complexity\.py$"),
    re.compile(r"^scripts/check_complexity_ratchet\.py$"),
    re.compile(r"^scripts/python-complexity-contract-v2\.json$"),
    re.compile(r"^scripts/complexity-ratchet\.json$"),
    re.compile(r"^scripts/frontend-critical-coverage\.json$"),
    re.compile(r"^scripts/structural-characterization-baseline-v1\.json$"),
    re.compile(r"^scripts/target-mutation-contract-v2\.json$"),
    re.compile(r"^ops/systemd/"),
    re.compile(r"^ops/caddy/"),
    re.compile(r"^\.github/workflows/"),
    re.compile(r"^\.github/governance/"),
    re.compile(r"^\.github/dependabot\.yml$"),
)

_CONFTEST_DETAIL = "pytest conftest affects every test"
_DEPENDENCY_DETAIL = "dependency change can invalidate the import graph"
_ARCHITECTURE_DETAIL = "architecture contract rewires service/repo classification"
_GATE_DETAIL = "this script is the changed-line gate itself"
_WIRING_DETAIL = "wiring/composition root invalidates the static graph"
_SELECTOR_DETAIL = "change invalidates the selector under test"
_VENV_DETAIL = "venv must never be in the diff"


def _classify_path(rel_path: str) -> EscalationReason | None:
    if rel_path in EXACT_ESCALATION_PATHS:
        name = Path(rel_path).name
        if name == "conftest.py" or name.startswith("conftest"):
            return EscalationReason("conftest", rel_path, _CONFTEST_DETAIL)
        if name.startswith("requirements") or "/requirements" in rel_path:
            return EscalationReason("dependency_definition", rel_path, _DEPENDENCY_DETAIL)
        if name == "architecture_contract.json":
            return EscalationReason("architecture_contract", rel_path, _ARCHITECTURE_DETAIL)
    base = os.path.basename(rel_path)
    if base == "conftest.py":
        return EscalationReason("conftest", rel_path, _CONFTEST_DETAIL)
    if rel_path.startswith("scripts/check_"):
        return EscalationReason("gate_authority", rel_path, _GATE_DETAIL)
    if base == "_python_complexity.py":
        return EscalationReason("gate_authority", rel_path, _GATE_DETAIL)
    if rel_path.startswith("backend/") and rel_path.endswith("/composition.py"):
        return EscalationReason("wiring_root", rel_path, _WIRING_DETAIL)
    if rel_path == "scripts/pr_fast_select_tests.py":
        return EscalationReason("selector_self", rel_path, _SELECTOR_DETAIL)
    if rel_path.startswith("scripts/prototype_b3e2_selector/"):
        return EscalationReason("selector_self", rel_path, _SELECTOR_DETAIL)
    if rel_path.startswith("backend/venv/"):
        return EscalationReason("venv", rel_path, _VENV_DETAIL)
    for pattern in _PREFIX_ESCALATION_PATTERNS:
        if pattern.match(rel_path):
            if pattern.pattern.startswith("^backend/tests/conftest"):
                return EscalationReason("conftest", rel_path, _CONFTEST_DETAIL)
            if pattern.pattern.startswith("^backend/.+/conftest"):
                return EscalationReason("conftest", rel_path, _CONFTEST_DETAIL)
            if pattern.pattern.startswith("^conftest"):
                return EscalationReason("conftest", rel_path, _CONFTEST_DETAIL)
            if pattern.pattern.startswith("^backend/venv"):
                return EscalationReason("venv", rel_path, _VENV_DETAIL)
            if pattern.pattern.startswith("^scripts/pr_fast"):
                return EscalationReason("selector_self", rel_path, _SELECTOR_DETAIL)
            if "check_" in pattern.pattern:
                return EscalationReason("gate_authority", rel_path, _GATE_DETAIL)
            if "_python_complexity" in pattern.pattern:
                return EscalationReason("gate_authority", rel_path, _GATE_DETAIL)
            if "complexity-contract" in pattern.pattern or "complexity-ratchet" in pattern.pattern:
                return EscalationReason("gate_authority", rel_path, _GATE_DETAIL)
            if ".github/workflows" in pattern.pattern or ".github/governance" in pattern.pattern:
                return EscalationReason("wiring_root", rel_path, _WIRING_DETAIL)
            if "dependabot" in pattern.pattern:
                return EscalationReason("dependency_definition", rel_path, _DEPENDENCY_DETAIL)
            if "ops/systemd" in pattern.pattern or "ops/caddy" in pattern.pattern:
                return EscalationReason("wiring_root", rel_path, _WIRING_DETAIL)
    return None


def classify_changed_paths(paths: Iterable[str]) -> list:
    seen: set = set()
    out: list = []
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        reason = _classify_path(p)
        if reason is not None:
            out.append(reason)
    return out


# ---------------------------------------------------------------------------
# Diff / eligibility helpers (reuse gate authority)
# ---------------------------------------------------------------------------


def _all_changed_paths(base: str, root: Path) -> list:
    """Return all AM (no renames) paths added/modified between base and HEAD."""
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=AM", "--no-renames",
         base, "--"],
        cwd=root,
        text=True,
    )
    return [line for line in output.splitlines() if line]


def _all_deleted_paths(base: str, root: Path) -> list:
    """Return all D (deleted) paths between base and HEAD."""
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=D", base, "--"],
        cwd=root,
        text=True,
    )
    return [line for line in output.splitlines() if line]


def _validate_base(base: str, root: Path) -> None:
    subprocess.run(
        ["git", "rev-parse", "--verify", f"{base}^{{" + "commit" + "}}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _module_to_path(module: str, file_to_module: dict) -> str | None:
    return file_to_module.get(module)


def _head_sha(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
    ).strip()


# ---------------------------------------------------------------------------
# Main algorithm
# ---------------------------------------------------------------------------


def select_tests(base: str, root: Path, head_tree: str | None = None) -> SelectionResult:
    """Compute the deterministic SelectionResult for `base`..HEAD at `root`."""
    result = SelectionResult(state=STATE_ERROR, base=base)

    try:
        _validate_base(base, root)
    except subprocess.CalledProcessError as exc:
        result.errors.append(f"invalid base {base!r}: git rev-parse failed (rc={exc.returncode})")
        result.state = STATE_ERROR
        return result

    try:
        gate = _load_pr_b2_gate()
    except Exception as exc:
        result.errors.append(f"failed to load PR-B2 gate: {exc}")
        result.state = STATE_ERROR
        return result

    try:
        all_added = _all_changed_paths(base, root)
        all_deleted = _all_deleted_paths(base, root)
    except subprocess.CalledProcessError as exc:
        result.errors.append(f"git diff failed (rc={exc.returncode})")
        result.state = STATE_ERROR
        return result

    # Build the static graph over the CURRENT working tree.
    try:
        file_to_module, forward, test_file_to_module, dynamic_files, star_files = (
            build_graph(root)
        )
    except FileNotFoundError as exc:
        result.errors.append(str(exc))
        result.state = STATE_ERROR
        return result

    # Escalation surfaces from the diff (static, minimal, justified).
    static_escalations = classify_changed_paths(all_added)
    deleted_test_paths = [
        p for p in all_deleted
        if p.startswith("backend/tests/") and p.endswith(".py")
    ]

    # Test-only changes: handle BEFORE prod-eligibility so docs/frontend-only
    # diffs classify cleanly as NO_ELIGIBLE_BACKEND_CHANGE.
    changed_test_paths = [
        p for p in all_added
        if p.startswith("backend/tests/") and p.endswith(".py")
        and not p.endswith("/conftest.py")
        and not p.endswith("/__init__.py")
    ]
    is_test_only_diff = bool(changed_test_paths) and not any(
        gate.is_eligible_backend(p) for p in all_added
    )

    if deleted_test_paths and not static_escalations:
        for p in deleted_test_paths:
            result.escalation_reasons.append(EscalationReason(
                category="deleted_test",
                path=p,
                detail="test file removed in diff; reverse closure cannot be trusted",
            ))
        result.notes.append(
            "deleted backend test(s); cannot determine what consumers relied on them"
        )
        result.state = STATE_ESCALATION
        return result

    if static_escalations:
        for r in static_escalations:
            result.escalation_reasons.append(r)
        result.notes.append(
            "untrusted surface(s) changed; caller must run FULL"
        )
        result.state = STATE_ESCALATION
        return result

    # Dynamic import census on CHANGED files.
    changed_dynamic: list = []
    for rel in all_added:
        if rel in dynamic_files:
            changed_dynamic.append(rel)
    if changed_dynamic:
        for rel in changed_dynamic:
            result.escalation_reasons.append(EscalationReason(
                category="dynamic_import",
                path=rel,
                detail="dynamic import detected; reverse closure is unsafe",
            ))
        result.notes.append(
            "dynamic import in changed set; caller must run FULL"
        )
        result.state = STATE_ESCALATION
        return result

    eligible_changed = sorted({
        p for p in all_added if gate.is_eligible_backend(p)
    })
    result.eligible_changed = eligible_changed

    if not eligible_changed and not changed_test_paths:
        result.notes.append("no eligible backend production files changed")
        result.state = STATE_NO_ELIGIBLE
        return result

    # Test-only PR semantics: modified/added tests are SELECTED for self.
    if is_test_only_diff:
        selected: list = []
        for rel in sorted(changed_test_paths):
            mod = _test_module(rel)  # backend/tests/test_x.py -> tests.test_x
            node_id = _node_id_for_test_module(mod) if mod else rel
            selected.append(SelectedTest(
                node_id=node_id,
                file=rel,
                reasons=["self_change: test file modified in diff"],
            ))
        result.selected_tests = selected
        result.selection_count = len(selected)
        result.state = STATE_SELECTED
        result.notes.append("test-only diff; selecting every changed test")
        return result

    # Build the reverse closure from eligible production modules.
    starts: set = set()
    for rel in eligible_changed:
        mod = _file_to_module(rel)
        if mod is not None:
            starts.add(mod)
    if not starts:
        result.errors.append("eligible_changed is non-empty but no module mapping")
        result.state = STATE_ERROR
        return result

    reverse = reverse_prod_graph(forward)
    # Reverse closure: every transitive importer of any changed module.
    impacted = reverse_closure(starts, reverse)
    # Forward expansion at depth 1: every module the changed module directly
    # imports (re-exports / facade pattern). When a facade changes, its
    # submodules' tests must run because the facade re-exports from them.
    # We do NOT recurse beyond depth 1 because that would over-select.
    for s_mod in list(starts):
        for fwd in forward.get(s_mod, ()):
            impacted.add(fwd)
    # impacted is in module-name space; map back to file paths.
    impacted_paths: list = []
    for mod in sorted(impacted):
        path = _module_to_path(mod, file_to_module)
        if path is not None:
            impacted_paths.append(path)
    result.impacted_production = impacted_paths

    # Collect tests that import any impacted module.
    selected_tests: list = []
    seen_node_ids: set = set()
    combined_map = dict(file_to_module)
    combined_map.update(test_file_to_module)
    for test_module, rel in test_file_to_module.items():
        # Tests import prod modules from backend/ root; parse their imports.
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            edges, _, _ = parse_imports(source, test_module, combined_map)
        except SyntaxError:
            # Malformed test file: skip rather than escalate; tests can be
            # invalid for transient reasons and pytest will surface them.
            continue
        hit = edges & impacted
        if not hit:
            continue
        node_id = _node_id_for_test_module(test_module)
        if node_id in seen_node_ids:
            continue
        seen_node_ids.add(node_id)
        hit_sorted = sorted(hit)
        reasons = [f"reverse_closure: imports {hit_sorted[0]}"]
        if len(hit_sorted) > 1:
            reasons.append(
                "additional impacted imports: "
                + ", ".join(hit_sorted[1:])
            )
        selected_tests.append(SelectedTest(
            node_id=node_id,
            file=rel,
            reasons=reasons,
        ))

    # Self-change reason for any test file that is also in all_added.
    for rel in sorted(all_added):
        if not (rel.startswith("backend/tests/") and rel.endswith(".py")):
            continue
        test_module = _test_module(rel)
        if test_module is None:
            continue
        node_id = _node_id_for_test_module(test_module)
        if node_id in seen_node_ids:
            # Already selected via reverse closure — annotate the reason.
            for t in selected_tests:
                if t.node_id == node_id:
                    if "self_change: test file modified in diff" not in t.reasons:
                        t.reasons.append("self_change: test file modified in diff")
                    break
            continue
        selected_tests.append(SelectedTest(
            node_id=node_id,
            file=rel,
            reasons=["self_change: test file modified in diff"],
        ))
        seen_node_ids.add(node_id)

    result.selected_tests = selected_tests
    result.selection_count = len(selected_tests)

    if not selected_tests:
        # Empty selection on eligible production change is unsafe: the gate
        # caller cannot prove we covered anything.
        result.escalation_reasons.append(EscalationReason(
            category="empty_selection",
            path=",".join(eligible_changed) if eligible_changed else "<no eligible>",
            detail="no test file imports any impacted production module",
        ))
        result.notes.append(
            "reverse closure produced an empty test set; caller must run FULL"
        )
        result.state = STATE_ESCALATION
        return result

    result.notes.append(
        f"reverse-closure over {len(eligible_changed)} eligible change(s) "
        f"reached {len(impacted_paths)} impacted module(s) and "
        f"{len(selected_tests)} test(s)"
    )
    result.state = STATE_SELECTED
    return result


# ---------------------------------------------------------------------------
# Test module node-id helper
# ---------------------------------------------------------------------------


def _node_id_for_test_module(module: str) -> str:
    """Return a pytest node id for a backend test file by module name."""
    if not module:
        return ""
    return module  # pytest collects backend.tests.X from conftest sys.path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_root(root_arg: str | None) -> Path:
    if root_arg is None:
        root = Path(__file__).resolve().parent.parent
    else:
        root = Path(root_arg).resolve()
    if not root.is_dir():
        raise ValueError(f"--root path is not a directory: {root}")
    return root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="PR-B3a deterministic backend PR test selector."
    )
    parser.add_argument("--base", required=True,
                        help="Base commit SHA (or ref) to diff against.")
    parser.add_argument(
        "--root", default=None,
        help="Path to the git working tree root. Defaults to script's parent.",
    )
    args = parser.parse_args(argv)

    try:
        root = _resolve_root(args.root)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR

    try:
        result = select_tests(args.base, root)
    except Exception as exc:  # noqa: BLE001 - last-resort fail-closed
        print(f"pr_fast_select_tests: unhandled error: {exc}", file=sys.stderr)
        sys.stdout.write(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "state": STATE_ERROR,
            "base_sha": args.base,
            "eligible_changed": [],
            "changed_tests": [],
            "impacted_production": [],
            "selected_tests": [],
            "selection_count": 0,
            "escalation_reasons": [],
            "errors": [f"unhandled: {exc}"],
            "diagnostics": [],
            "notes": [],
        }, indent=2, sort_keys=False))
        sys.stdout.write("\n")
        return EXIT_ERROR

    payload = result.to_dict()
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=False))
    sys.stdout.write("\n")

    # Brief human summary on stderr (CI consumers MUST parse stdout JSON).
    summary = (
        f"pr_fast_select_tests: state={result.state} "
        f"base={result.base} eligible={len(result.eligible_changed)} "
        f"impacted={len(result.impacted_production)} "
        f"selected={result.selection_count} "
        f"escalations={len(result.escalation_reasons)} "
        f"errors={len(result.errors)}"
    )
    print(summary, file=sys.stderr)

    return exit_code_for(result.state)


if __name__ == "__main__":
    raise SystemExit(main())
