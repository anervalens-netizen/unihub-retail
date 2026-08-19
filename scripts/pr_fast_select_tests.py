#!/usr/bin/env python3
"""PR-B3a deterministic backend PR test selector.

This script is the PRODUCTION slice of the B3/E2 selector proof. It decides
which backend pytest test nodes must run for a pull request, given:

  * the exact repository state (--root, default: script's parent),
  * the base commit reference (--base, resolved to a full SHA),
  * the current HEAD at --root (resolved to a full SHA).

It is intentionally self-contained: there is no cache, no testmon, no
previous-run state, no filename-only authority, no network. It reuses
the existing PR-B2 backend eligibility authority via importlib (we load
`scripts/check_changed_line_coverage.py` from the selected repository
root and call its public predicates). The PR-B2 gate is NOT modified
by this PR.

TRUST ORDER (security-critical — do NOT reorder without rereading):

    1. resolve base SHA + HEAD SHA
    2. obtain COMPLETE git diff using git only
       (AM additions + D deletions, --no-renames)
    3. classify trust-surface changes/deletions WITHOUT importing
       the PR-B2 gate
    4. if any selector/gate/conftest/dependency/wiring/governance
       trust surface changed:
           return ESCALATION_REQUIRED immediately
    5. only after trust surfaces are proven unchanged:
           load the PR-B2 gate from the selected repository root
    6. continue eligibility / graph / deletion-production logic

Statement (claim scope deliberately narrow):

    Untrusted PR changes to selector/gate/control-plane surfaces are
    classified before executable gate code is imported.

This guarantees that a PR which MODIFIES the gate cannot execute the
modified gate before the selector recognizes the change, and a PR
which DELETES the gate cannot fail at import time before the
selector recognizes the deletion as ESCALATION_REQUIRED.

Four-state contract:
    NO_ELIGIBLE_BACKEND_CHANGE  -> exit 0
    SELECTED                    -> exit 0
    ESCALATION_REQUIRED         -> exit 2
    ERROR                       -> exit 3

The selector writes canonical JSON to stdout (one object, schema_version=1)
with the resolved base_sha AND head_sha as full 40-character SHAs (never
short SHAs or branch names). Human summaries, when needed, go to stderr
only. Future CI consumers MUST parse the JSON, never the human text.

Residual risks documented here (do NOT claim they are solved):
  * F.1  Dynamic-loading code in UNCHANGED files (e.g. importlib.import_module
        inside a still-loaded test) is out of scope. Static analysis cannot
        detect it without running the code. The selector only catches dynamic
        loading that lives inside the CHANGED set.
  * F.2  Composition root uses explicit multi-name imports (verified 2026-08-19
        on backend/composition.py: 0 star imports). A future `from X import *`
        in the composition root would explode the reverse closure; this is
        documented as a coding-rule boundary, not enforced by this script.

This is the B3a slice only. PR-B3b will wire `pr-fast` and the future
`PR-DEEP` workflow in a separate, additive change. PR-B3b is responsible
for checkout-ing the exact intended HEAD before invoking this script; the
selector itself does NOT take a working-tree argument.
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


# ---------------------------------------------------------------------------
# PR-B2 gate authority (loaded by importlib from the selected repository root).
# ---------------------------------------------------------------------------
#
# The PR-B2 gate is the single source of truth for backend eligibility and
# diff collection. We deliberately do NOT copy its predicates here.
#
# Trust-ordering invariant: the gate file is ONLY loaded AFTER the trust-
# surface classifier has confirmed that no selector/gate/control-plane
# path changed in the diff. Loading it earlier would (a) execute the
# candidate gate from a PR that modifies it and (b) crash on import for
# a PR that deletes it — both before the selector can classify the
# change as ESCALATION_REQUIRED.
#
# When `--root=<repo>` is supplied, the gate authority is loaded from
# `<repo>/scripts/check_changed_line_coverage.py` (root-local). When
# `--root` is omitted, it is loaded from the directory containing this
# selector script (production invocation), which is naturally identical
# because the selector lives next to the gate in the production checkout.


def _gate_path_for_root(root: Path) -> Path:
    """Return the candidate path to the PR-B2 gate for the given repo root.

    Always `<root>/scripts/check_changed_line_coverage.py`. The path is
    NOT required to exist at this point; the caller decides whether a
    missing gate is an ERROR (diff did not explain it) or part of the
    normal ESCALATION path (diff already proved deletion).
    """
    return (root / "scripts" / "check_changed_line_coverage.py").resolve()


def _load_pr_b2_gate(gate_path: Path):
    """Load `gate_path` as the trusted PR-B2 gate module.

    Raises FileNotFoundError if the file does not exist. Raises
    RuntimeError if importlib cannot build a spec. Any exception raised
    during module execution propagates to the caller — this is the only
    safe behavior because we must surface the truth to the caller rather
    than silently fall back to a different module.
    """
    if not gate_path.exists():
        raise FileNotFoundError(
            f"PR-B2 gate file does not exist at {gate_path}"
        )
    spec = importlib.util.spec_from_file_location("pr_b2_gate", gate_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot build spec for PR-B2 gate at {gate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class SelectedTest:
    """A runnable test that exists at HEAD and can be executed by pytest.

    `file` is the authoritative repo-relative path the CI caller will pass
    to pytest. `node_id` is informational/stably-named; consumers MUST
    NOT assume it is a valid pytest selector unless they explicitly
    opt into dotted-node collection (we currently do not).
    """
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
    head: str
    eligible_changed: list = dataclasses.field(default_factory=list)
    changed_tests: list = dataclasses.field(default_factory=list)
    deleted_production: list = dataclasses.field(default_factory=list)
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
            "head_sha": self.head,
            "eligible_changed": list(self.eligible_changed),
            "changed_tests": list(self.changed_tests),
            "deleted_production": list(self.deleted_production),
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
    if any(p in ("__pycache__", "venv", "scripts", "tests") for p in parts):
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


def _test_module(rel_path: str) -> str | None:
    """Map a backend/tests/* path to its dotted pytest-style module name.

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


def _is_package_init(rel_path: str) -> bool:
    """True iff `rel_path` is a `__init__.py` (i.e. a package initializer)."""
    return rel_path.endswith("/__init__.py")


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


def _current_relative_parts(rel_path: str, current_module: str) -> list:
    """Return the parts list used by relative-import resolution.

    For a normal module file (e.g. backend/a/b/c.py -> current_module 'a.b.c')
    the parts are the dotted module split on '.': ['a', 'b', 'c'].

    For a PACKAGE INITIALIZER file (e.g. backend/a/b/__init__.py -> current_module
    'a.b'), Python's __name__ is still 'a.b' but the file conceptually
    occupies the deepest position of the package. We extend the parts with
    a sentinel so that level-1 relatives resolve to the package itself,
    matching Python's actual import semantics for a package init file.
    Without this sentinel, level-1 in a/b/__init__.py would resolve to
    `a` (the parent of package a.b), which silently misroutes edge cases
    like facade re-exports from package init files.
    """
    parts = current_module.split(".") if current_module else []
    if _is_package_init(rel_path):
        # Match Python: __init__.py is one logical level deeper than its
        # dotted package name; level-1 relatives resolve to the package
        # itself, not to its parent.
        if not parts or parts[-1] != "__init__":
            parts = parts + ["__init__"]
    return parts


def _resolve_relative(level: int, module: str | None,
                      current_parts: list) -> tuple:
    """Resolve a relative import to a dotted module name.

    Returns (resolved_module_or_None, safe_bool).
    safe_bool == False means the resolver could not safely determine a
    unique in-tree target. Callers MUST treat unsafe results as a
    dynamic-import trust violation (ESCALATION_REQUIRED).

    Semantics (validated corrected from the prototype):
        level 1, current = a.b.c       -> drop c, base = a.b
        level 2, current = a.b.c       -> drop c,b, base = a
        level 3, current = a.b.c       -> beyond root -> (None, False)
        level == len(parts)            -> beyond root -> (None, False)
        level >  len(parts)            -> beyond root -> (None, False)
        level < 1                      -> (None, False)
    """
    if level < 1:
        return None, False
    if level >= len(current_parts):
        return None, False
    base = current_parts[: len(current_parts) - level]
    if not base:
        # `from . import x` at a top-level package init: base is empty;
        # the resolved name is the alias name (no parent prefix).
        if module:
            return module, True
        return None, False
    if module:
        return ".".join(base + [module]), True
    return ".".join(base), True


def _all_known_prefixes(dotted: str, known: set) -> list:
    """Return [dotted, dotted[:-1], dotted[:-2], ..., first-segment] for
    every prefix that exists in `known`. Order: longest first.

    Used to record the full import chain so that Python's package
    __init__.py execution order is preserved in the static graph.
    """
    out: list = []
    cur = dotted
    while cur:
        if cur in known and cur not in out:
            out.append(cur)
        if "." not in cur:
            break
        cur = cur.rsplit(".", 1)[0]
    return out


def parse_imports(source: str, current_module: str,
                  rel_path: str,
                  module_to_files: dict) -> tuple:
    """Return (set of known imported backend module names, has_dynamic_import).

    `rel_path` is needed so we can apply correct Python relative-import
    semantics for `__init__.py` package initializer files vs. normal
    module files.

    Modules outside the backend tree (e.g. fastapi, asyncpg) are ignored.
    Only imports that resolve to a file in our tree (forward-graph edges)
    are returned.

    For `import x.y.z` style imports, we record the full dotted name plus
    every known ancestor prefix so package __init__.py execution order
    is honored.
    """
    tree = ast.parse(source)
    known: set = set()
    has_dynamic_import = False
    current_parts = _current_relative_parts(rel_path, current_module)

    def add_dotted(dotted: str) -> None:
        if not dotted:
            return
        # Record full dotted name + every known ancestor prefix.
        for prefix in _all_known_prefixes(dotted, module_to_files):
            known.add(prefix)

    def visit(node: ast.AST) -> None:
        nonlocal has_dynamic_import
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Normal `import x.y.z` (with optional `as` alias).
                # The dotted module name is what Python imports; the
                # `asname` is irrelevant for graph construction.
                add_dotted(alias.name)
            return
        if isinstance(node, ast.ImportFrom):
            level = node.level or 0
            if level > 0:
                resolved, safe = _resolve_relative(
                    level, node.module, current_parts,
                )
                if not safe:
                    has_dynamic_import = True
                    return
                target_pkg = resolved
            else:
                target_pkg = node.module
            if not target_pkg and not node.names:
                return
            # Walk alias list. For `from X import a, b` we record X plus
            # any X.a / X.b submodules that exist in our tree (so facade
            # re-exports propagate).
            for alias in node.names:
                if alias.name == "*":
                    # Star import — record the target package itself.
                    if target_pkg:
                        add_dotted(target_pkg)
                    continue
                if target_pkg:
                    # `from X.Y import Z` -> edge X.Y + edge X.Y.Z if Z is
                    # itself an in-tree submodule.
                    add_dotted(target_pkg)
                    if alias.name != "*":
                        # `from . import X` style (level>0, no module):
                        # alias.name is the submodule to import.
                        edge = f"{target_pkg}.{alias.name}"
                        add_dotted(edge)
                else:
                    # `from . import X` style with module=None:
                    # target is the alias name itself (no parent prefix).
                    add_dotted(alias.name)
            return
        if isinstance(node, ast.Call) and _is_dynamic_call(node):
            has_dynamic_import = True
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return known, has_dynamic_import


# ---------------------------------------------------------------------------
# Static graph + reverse closure
# ---------------------------------------------------------------------------


def build_graph(root: Path) -> tuple:
    """Build the forward static-import graph over the backend production tree.

    Returns (file_to_module, prod_forward_edges, test_file_to_module,
             dynamic_files).
      * file_to_module: {module: rel_path} for production files
      * prod_forward_edges: {module: set(imported_modules)} for production
      * test_file_to_module: {test_module: rel_path} for backend/tests/*
      * dynamic_files: set(rel_path) of files that contain dynamic loaders

    Test files are indexed separately and are NOT part of the production
    reverse-closure graph; they are consumers of production modules only.
    """
    file_to_module = collect_python_files(root)
    test_file_to_module = collect_test_files(root)
    combined = dict(file_to_module)
    combined.update(test_file_to_module)

    forward: dict = {m: set() for m in file_to_module}
    dynamic_files: set = set()

    for module, rel in file_to_module.items():
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            edges, has_dyn = parse_imports(
                source, module, rel, combined,
            )
        except SyntaxError:
            dynamic_files.add(rel)
            continue
        forward[module].update(edges)
        if has_dyn:
            dynamic_files.add(rel)

    for test_module, rel in test_file_to_module.items():
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            _, has_dyn = parse_imports(
                source, test_module, rel, combined,
            )
        except SyntaxError:
            continue
        if has_dyn:
            dynamic_files.add(rel)

    return file_to_module, forward, test_file_to_module, dynamic_files


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
# Diff helpers
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
    """Return all D paths deleted between base and HEAD.

    Uses --no-renames so a pure rename (R100) becomes DELETE old +
    ADD new, and the deleted production path appears here.
    """
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=D", "--no-renames",
         base, "--"],
        cwd=root,
        text=True,
    )
    return [line for line in output.splitlines() if line]


def _resolve_full_sha(ref: str, root: Path) -> str:
    """Resolve a git ref (branch/tag/SHA) to a full 40-character SHA.

    Raises subprocess.CalledProcessError if the ref cannot be resolved.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _head_full_sha(root: Path) -> str:
    """Resolve HEAD to a full 40-character SHA.

    Raises subprocess.CalledProcessError if HEAD cannot be resolved.
    """
    return _resolve_full_sha("HEAD", root)


def _validate_base(base_full: str, root: Path) -> None:
    """Re-verify that the resolved full base is a valid commit object."""
    subprocess.run(
        ["git", "rev-parse", "--verify", f"{base_full}^{{commit}}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


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
    "scripts/check_changed_line_coverage.py",
    "scripts/check_changed_function_complexity.py",
    "scripts/_python_complexity.py",
    "scripts/check_python_complexity_contract.py",
    "scripts/python-complexity-contract-v2.json",
    "scripts/python-complexity-contract-v1.json",
    "scripts/complexity-ratchet.json",
    "scripts/frontend-critical-coverage.json",
    "scripts/structural-characterization-baseline-v1.json",
    "scripts/target-mutation-contract-v2.json",
    "scripts/check_complexity_ratchet.py",
    "scripts/pr_fast_select_tests.py",
    "scripts/check_high_risk_pr_governance.py",
    "scripts/is_high_risk_category_touched.py",
})

_PREFIX_ESCALATION_PATTERNS = (
    (re.compile(r"^backend/tests/conftest\..+\.py$"), "conftest",
     "pytest conftest affects every test"),
    (re.compile(r"^backend/.+/conftest\.py$"), "conftest",
     "pytest conftest affects every test"),
    (re.compile(r"^conftest\.py$"), "conftest",
     "pytest conftest affects every test"),
    (re.compile(r"^backend/venv/.*"), "venv", "venv must never be in the diff"),
    (re.compile(r"^scripts/prototype_b3e2_selector/"), "selector_self",
     "change invalidates the selector under test"),
    (re.compile(r"^scripts/check_high_risk_pr_governance\.py$"),
     "gate_authority", "this script is the A3 governance checker"),
    (re.compile(r"^scripts/is_high_risk_category_touched\.py$"),
     "gate_authority", "this script is the A3 governance helper"),
    (re.compile(r"^scripts/check_complexity_ratchet\.py$"),
     "gate_authority",
     "complexity ratchet is part of gate authority"),
    (re.compile(r"^scripts/python-complexity-contract"),
     "gate_authority",
     "complexity contract config is part of gate authority"),
    (re.compile(r"^scripts/complexity-ratchet\.json$"),
     "gate_authority",
     "complexity ratchet baseline is part of gate authority"),
    (re.compile(r"^scripts/frontend-critical-coverage\.json$"),
     "gate_authority",
     "frontend critical coverage baseline is part of gate authority"),
    (re.compile(r"^scripts/structural-characterization-baseline-v1\.json$"),
     "gate_authority",
     "structural characterization baseline is part of gate authority"),
    (re.compile(r"^scripts/target-mutation-contract-v2\.json$"),
     "gate_authority",
     "target mutation contract is part of gate authority"),
    (re.compile(r"^ops/systemd/"), "wiring_root",
     "systemd / deployment wiring invalidates the static graph"),
    (re.compile(r"^ops/caddy/"), "wiring_root",
     "caddy / deployment wiring invalidates the static graph"),
    (re.compile(r"^\.github/workflows/"), "wiring_root",
     "runner workflow changes invalidate CI topology trust"),
    (re.compile(r"^\.github/governance/"), "wiring_root",
     "governance manifest changes invalidate A3 classification"),
    (re.compile(r"^\.github/dependabot\.yml$"), "dependency_definition",
     "dependency change can invalidate the import graph"),
    (re.compile(r"^requirements.*\.txt$"), "dependency_definition",
     "dependency change can invalidate the import graph"),
    (re.compile(r"^requirements.*\.lock$"), "dependency_definition",
     "dependency change can invalidate the import graph"),
    (re.compile(r"^backend/requirements.*\.txt$"), "dependency_definition",
     "dependency change can invalidate the import graph"),
    (re.compile(r"^backend/requirements.*\.lock$"), "dependency_definition",
     "dependency change can invalidate the import graph"),
    (re.compile(r"^backend/.+/composition\.py$"), "wiring_root",
     "wiring/composition root invalidates the static graph"),
    (re.compile(r"^backend/composition\.py$"), "wiring_root",
     "wiring/composition root invalidates the static graph"),
)


def _classify_path(rel_path: str) -> EscalationReason | None:
    """Return an EscalationReason if the path is a trust surface, else None.

    The same category applies whether the diff is A/M (added/modified) or
    D (deleted): a deletion of a trust surface invalidates selection
    just as surely as a change to it.
    """
    if rel_path in EXACT_ESCALATION_PATHS:
        name = Path(rel_path).name
        if name == "conftest.py" or name.startswith("conftest"):
            return EscalationReason("conftest", rel_path,
                                   "pytest conftest affects every test")
        if name.startswith("requirements"):
            return EscalationReason("dependency_definition", rel_path,
                                   "dependency change can invalidate the import graph")
        if name == "architecture_contract.json":
            return EscalationReason("architecture_contract", rel_path,
                                   "architecture contract rewires service/repo classification")
        if rel_path == "scripts/pr_fast_select_tests.py":
            return EscalationReason("selector_self", rel_path,
                                   "change invalidates the selector under test")
        # Everything else in EXACT_ESCALATION_PATHS is gate/contract
        # authority; the selector's reverse closure cannot be trusted
        # when these move.
        return EscalationReason("gate_authority", rel_path,
                               "this script is part of the changed-line / "
                               "complexity gate authority")
    base_name = os.path.basename(rel_path)
    if base_name == "conftest.py":
        return EscalationReason("conftest", rel_path,
                               "pytest conftest affects every test")
    for pattern, category, detail in _PREFIX_ESCALATION_PATTERNS:
        if pattern.match(rel_path):
            return EscalationReason(category, rel_path, detail)
    return None


def classify_changed_paths(paths: Iterable[str]) -> list:
    """Return EscalationReasons for every trust-surface path in `paths`.

    Operates over the COMPLETE diff (additions + modifications + deletions),
    not AM only. A deletion of a gate/selector/wiring/governance path is
    just as much a trust violation as a change to it.
    """
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
# Main algorithm
# ---------------------------------------------------------------------------


def _emit_error(errors: list, state: str, msg: str) -> SelectionResult:
    """Return an ERROR-typed SelectionResult with deterministic identity.

    base and head are filled with empty strings because identity could
    not be resolved; the `errors` list carries the diagnostic detail.
    """
    errors.append(msg)
    result = SelectionResult(state=STATE_ERROR, base="", head="")
    result.errors.extend(errors)
    return result


def select_tests(base: str, root: Path) -> SelectionResult:
    """Compute the deterministic SelectionResult for `base`..HEAD at `root`.

    TRUST ORDER (security-critical):

      1. resolve base SHA + HEAD SHA through git
      2. collect COMPLETE diff (AM additions + D deletions, --no-renames)
      3. classify trust-surface changes/deletions WITHOUT importing the
         PR-B2 gate
      4. if any trust surface changed:
            return ESCALATION_REQUIRED immediately
      5. only then load the PR-B2 gate from the selected repository root
      6. continue with eligibility / graph / deletion-production logic

    Claim scope (deliberately narrow):

      Untrusted PR changes to selector/gate/control-plane surfaces are
      classified before executable gate code is imported.
    """
    # ----- 1. Resolve both SHAs through git ----------------------------
    # base may arrive as a short SHA, branch name, tag, or full SHA.
    # HEAD is resolved as a separate step. Both must be full 40-char SHAs
    # in the canonical JSON.
    try:
        base_full = _resolve_full_sha(base, root)
    except subprocess.CalledProcessError:
        return _emit_error([], STATE_ERROR,
                           f"invalid base {base!r}: git rev-parse failed")
    try:
        head_full = _head_full_sha(root)
    except subprocess.CalledProcessError:
        return _emit_error([], STATE_ERROR,
                           "HEAD cannot be resolved")
    try:
        _validate_base(base_full, root)
    except subprocess.CalledProcessError:
        return _emit_error([], STATE_ERROR,
                           f"base {base_full!r} is not a valid commit object")

    result = SelectionResult(state=STATE_ERROR, base=base_full, head=head_full)

    # ----- 2. Collect the COMPLETE diff using git ONLY ----------------
    # We deliberately do this BEFORE importing the PR-B2 gate so that a
    # modified or deleted gate cannot execute its top-level code during
    # import before we have a chance to classify the change as
    # ESCALATION_REQUIRED. The git diff is the only authority consulted
    # at this stage.
    try:
        all_added = _all_changed_paths(base_full, root)
        all_deleted = _all_deleted_paths(base_full, root)
    except subprocess.CalledProcessError as exc:
        result.errors.append(f"git diff failed (rc={exc.returncode})")
        return result

    # ----- 3. Classify trust surfaces WITHOUT importing the gate -----
    # Same classifier for AM and D: a deletion of a trust surface
    # invalidates selection trust just as surely as a change.
    surface_paths = list(all_added) + list(all_deleted)
    static_escalations = classify_changed_paths(surface_paths)

    # ----- 4. Trust-surface short-circuit (gate NOT yet loaded) -----
    # The candidate PR-B2 gate at <root>/scripts/check_changed_line_coverage.py
    # may itself be in `surface_paths`. If so, we MUST NOT load it. This
    # is the security boundary the previous prototype violated: it loaded
    # the candidate gate via importlib BEFORE the trust-surface
    # classifier ran, so a PR that modified or deleted the gate could
    # execute the modified gate's top-level code (or crash at import)
    # before the selector had a chance to ESCALATE_REQUIRED.
    if static_escalations:
        for r in static_escalations:
            result.escalation_reasons.append(r)
        result.notes.append(
            "trust surface changed (added/modified/deleted); caller must run FULL"
        )
        result.state = STATE_ESCALATION
        return result

    # ----- 5. Trust surfaces proven unchanged -> load PR-B2 gate -----
    # The gate is loaded from the SELECTED repository root so a
    # --root=<temp_repo> invocation consumes the gate under that temp
    # repo's scripts/ directory (root-local authority). For normal
    # production invocation where --root is the checkout containing the
    # selector, the path naturally resolves to the sibling gate.
    gate_path = _gate_path_for_root(root)
    try:
        gate = _load_pr_b2_gate(gate_path)
    except FileNotFoundError as exc:
        # Diff did NOT explain the missing gate (no static escalation was
        # raised). Repository state is inconsistent: fail closed as ERROR.
        result.errors.append(
            f"PR-B2 gate unexpectedly missing at {gate_path} "
            f"after diff classified no gate deletion: {exc}"
        )
        result.state = STATE_ERROR
        return result
    except Exception as exc:
        result.errors.append(
            f"failed to load PR-B2 gate at {gate_path}: {exc}"
        )
        result.state = STATE_ERROR
        return result

    # ----- 6. Continue eligibility / graph / deletion-production ------

    # ----- Build the static graph over the CURRENT working tree -----
    try:
        file_to_module, forward, test_file_to_module, dynamic_files = (
            build_graph(root)
        )
    except FileNotFoundError as exc:
        result.errors.append(str(exc))
        return result

    # ----- Deleted-test surface (must fail closed) ----
    deleted_test_paths = [
        p for p in all_deleted
        if p.startswith("backend/tests/") and p.endswith(".py")
    ]

    # ----- Deleted-eligible-production surface (must fail closed) ----
    # A deleted production module disappears from the current graph;
    # therefore the reverse-closure cannot prove coverage of consumers.
    deleted_eligible_production_paths = sorted({
        p for p in all_deleted if gate.is_eligible_backend(p)
    })
    result.deleted_production = deleted_eligible_production_paths

    # ----- Test-only diffs (changed test files in AM) ----
    changed_test_paths = [
        p for p in all_added
        if p.startswith("backend/tests/") and p.endswith(".py")
        and not p.endswith("/conftest.py")
        and not p.endswith("/__init__.py")
    ]
    # CORRECTION 8: changed_tests is the authoritative diff-derived
    # list of changed test paths (added + deleted). Populate it
    # BEFORE any escalation short-circuit so the contract holds even
    # when we ESCALATE_REQUIRED on a deleted test.
    result.changed_tests = sorted(set(changed_test_paths) | set(deleted_test_paths))
    is_test_only_diff = bool(changed_test_paths) and not any(
        gate.is_eligible_backend(p) for p in all_added
    )

    # ----- 2. Deleted backend test files — must fail closed. -------
    if deleted_test_paths:
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

    # ----- 3. Deleted eligible backend production files — must fail closed.
    if deleted_eligible_production_paths:
        for p in deleted_eligible_production_paths:
            result.escalation_reasons.append(EscalationReason(
                category="deleted_production",
                path=p,
                detail="eligible backend production file removed in diff; "
                        "current-tree graph no longer contains the node",
            ))
        result.notes.append(
            "deleted eligible backend production file(s); cannot safely prove "
            "coverage of affected tests"
        )
        result.state = STATE_ESCALATION
        return result

    # ----- 4. Dynamic-import census on CHANGED files (only matters for AM).
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

    # ----- changed_tests: explicit from diff (AM + D test paths) ----
    # The previous implementation reconstructed changed_tests indirectly
    # from selected-test reasons. The CORRECTION is to populate it
    # explicitly from the diff so deleted test paths are visible even
    # though they are no longer runnable.
    result.changed_tests = sorted(set(changed_test_paths) | set(deleted_test_paths))

    if not eligible_changed and not changed_test_paths:
        # docs-only / frontend-only diff: NO_ELIGIBLE_BACKEND_CHANGE.
        # Note: deleted-eligible-production was already handled above as
        # ESCALATION_REQUIRED.
        result.notes.append("no eligible backend production files changed")
        result.state = STATE_NO_ELIGIBLE
        return result

    # ----- Test-only diff semantics: SELECTED for self_change ----
    if is_test_only_diff:
        selected: list = []
        for rel in sorted(changed_test_paths):
            mod = _test_module(rel)
            node_id = _test_module_id(mod) if mod else rel
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

    # ----- Reverse-closure over eligible production -----
    starts: set = set()
    for rel in eligible_changed:
        mod = _file_to_module(rel)
        if mod is not None:
            starts.add(mod)
    if not starts:
        result.errors.append("eligible_changed is non-empty but no module mapping")
        return result

    reverse = reverse_prod_graph(forward)
    impacted = reverse_closure(starts, reverse)
    # Depth-1 forward expansion for facade re-exports.
    for s_mod in list(starts):
        for fwd in forward.get(s_mod, ()):
            impacted.add(fwd)
    impacted_paths: list = []
    for mod in sorted(impacted):
        path = file_to_module.get(mod)
        if path is not None:
            impacted_paths.append(path)
    result.impacted_production = impacted_paths

    # ----- Collect runnable tests that import any impacted module -----
    selected_tests: list = []
    seen_node_ids: set = set()
    combined_map = dict(file_to_module)
    combined_map.update(test_file_to_module)
    for test_module, rel in test_file_to_module.items():
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            edges, _ = parse_imports(source, test_module, rel, combined_map)
        except SyntaxError:
            continue
        hit = edges & impacted
        if not hit:
            continue
        node_id = _test_module_id(test_module)
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

    # ----- self_change reason for any test file in AM ----
    for rel in sorted(changed_test_paths):
        mod = _test_module(rel)
        if mod is None:
            continue
        node_id = _test_module_id(mod)
        if node_id in seen_node_ids:
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


def _test_module_id(module: str) -> str:
    """Return a stable, dotted-style identifier for a backend test module.

    This identifier is informational; consumers MUST treat `file` as
    the authoritative pytest path and MUST NOT assume `node_id` is a
    valid pytest CLI selector.
    """
    return module


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


def _emit(payload: dict, exit_code: int) -> int:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=False))
    sys.stdout.write("\n")
    return exit_code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="PR-B3a deterministic backend PR test selector."
    )
    parser.add_argument("--base", required=True,
                        help="Base commit ref (SHA / branch / tag); "
                             "resolved to a full 40-char SHA.")
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
        return _emit({
            "schema_version": SCHEMA_VERSION,
            "state": STATE_ERROR,
            "base_sha": "",
            "head_sha": "",
            "eligible_changed": [],
            "changed_tests": [],
            "deleted_production": [],
            "impacted_production": [],
            "selected_tests": [],
            "selection_count": 0,
            "escalation_reasons": [],
            "errors": [f"unhandled: {exc}"],
            "diagnostics": [],
            "notes": [],
        }, EXIT_ERROR)

    payload = result.to_dict()
    rc = _emit(payload, exit_code_for(result.state))

    summary = (
        f"pr_fast_select_tests: state={result.state} "
        f"base={result.base[:12]} head={result.head[:12]} "
        f"eligible={len(result.eligible_changed)} "
        f"impacted={len(result.impacted_production)} "
        f"selected={result.selection_count} "
        f"escalations={len(result.escalation_reasons)} "
        f"errors={len(result.errors)}"
    )
    print(summary, file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
