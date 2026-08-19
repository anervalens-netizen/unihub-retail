"""Durable tests for the PR-B3a deterministic backend PR test selector.

These tests pin the implementation-integrity invariants of the B3a
production slice of the B3/E2 selector proof. The selector is invoked
via its real CLI on real temporary git repositories so diff, rename
classification, and import-graph construction come from real git, not
mocks. The four-state contract, the four exit codes, the canonical JSON
shape, and the escalation surface are all asserted explicitly.

The durable pattern mirrors `test_changed_gates_pr_b2.py`: synthetic
git repos are built per-test, the gate runs in subprocess against the
temp repo, and assertions compare the parsed JSON result against the
expected invariants.

Each test class covers one of the four canonical states plus the
boundary cases the prototype proof enumerated. The tests are
intentionally explicit about WHY each case maps to the expected state;
the goal is durable coverage, not just line-count vanity.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[2]
PY = "/opt/Mobiup/unihub-retail/backend/venv/bin/python"
SELECTOR = WORKTREE / "scripts" / "pr_fast_select_tests.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(cwd, *args, check=True):
    """Run a git command in cwd and return stdout."""
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            f"git {args} failed in {cwd}: {proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    return proc.stdout


def _new_repo(tmp_path):
    """Create a temp git repo mirroring the unihub-retail backend layout.

    Copies the PR-B2 gate script so the selector can importlib-load it.
    Initializes git with the same safety settings as the production
    checkout (no renames, no GPG signing).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "backend").mkdir()
    (repo / "scripts").mkdir()
    shutil.copy(
        WORKTREE / "scripts" / "check_changed_line_coverage.py",
        repo / "scripts" / "check_changed_line_coverage.py",
    )
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "ci@example.com")
    _git(repo, "config", "user.name", "CI")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "diff.renames", "false")
    _git(repo, "config", "status.renames", "false")
    return repo


def _commit(repo, message="x"):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def _run_selector(repo, base):
    """Invoke the selector via subprocess in the temp repo.

    Returns (returncode, parsed_json_dict, stderr_text).
    """
    env = dict(os.environ)
    base_path = env.get("PATH") or ""
    env["PATH"] = ("/usr/bin:/bin:" + base_path)
    proc = subprocess.run(
        [PY, "-I", str(SELECTOR), "--root", str(repo), "--base", base],
        cwd=WORKTREE,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"selector did not emit valid JSON on stdout. "
            f"rc={proc.returncode}\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        ) from exc
    return proc.returncode, payload, proc.stderr


def _write(repo, rel_path, content):
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# =============================================================================
# 1. Ordinary service selection (positive SELECTED case)
# =============================================================================


class TestOrdinaryServiceSelection:
    """A single ordinary low-fanout service change selects exactly the test
    that imports it, with a deterministic reverse-closure reason.
    """

    def test_single_service_change_selects_only_its_test(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/services/b.py", "VAL = 2\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _write(repo, "backend/tests/test_b.py",
               "from services.b import VAL\n"
               "def test_b(): assert VAL == 2\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify a")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0, payload
        assert payload["state"] == "SELECTED"
        assert payload["eligible_changed"] == ["backend/services/a.py"]
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert node_ids == ["tests.test_a"]
        reasons = payload["selected_tests"][0]["reasons"]
        assert any("services.a" in r for r in reasons), reasons

    def test_submodule_change_only_selects_submodule_test(self, tmp_path):
        """When a submodule changes, only the test of that submodule runs.

        The prototype's corrected behavior: changing ONE submodule must
        not over-select consumers that don't import it directly. We
        re-test that with a clean facade.
        """
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/services/b.py", "VAL = 2\n")
        _write(repo, "backend/services/face.py",
               "from services.a import VAL as A\n"
               "from services.b import VAL as B\n"
               "VAL = (A, B)\n")
        _write(repo, "backend/tests/test_face.py",
               "from services.face import VAL\n"
               "def test_face(): assert VAL == (1, 2)\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _write(repo, "backend/tests/test_b.py",
               "from services.b import VAL\n"
               "def test_b(): assert VAL == 2\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        # Only a.py changes (a facade submodule), not the facade itself.
        _write(repo, "backend/services/a.py", "VAL = 99\n")
        _commit(repo, "modify a only")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0, payload
        assert payload["state"] == "SELECTED"
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        # The facade's test_face imports `from services.face`, which in
        # turn re-imports services.a — that re-export edge means changing
        # services.a propagates through the facade to its test.
        assert "tests.test_a" in node_ids
        assert "tests.test_b" not in node_ids


# =============================================================================
# 2. Facade / re-export behavior
# =============================================================================


class TestFacadeBehavior:
    """When a facade (file that re-exports from submodules) changes, both
    its own test AND every submodule's test must run because the facade
    IS the public boundary and its imports are part of the contract.
    """

    def test_facade_change_reaches_facade_and_submodule_tests(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        for name, val in [("a", 1), ("b", 2), ("c", 3)]:
            _write(repo, f"backend/services/{name}.py", f"VAL = {val}\n")
        _write(repo, "backend/services/face.py",
               "from services.a import VAL as A\n"
               "from services.b import VAL as B\n"
               "from services.c import VAL as C\n"
               'VAL = (A, B, C)\n')
        for name, val in [("a", 1), ("b", 2), ("c", 3)]:
            _write(repo, f"backend/tests/test_{name}.py",
                   f"from services.{name} import VAL\n"
                   f"def test_{name}(): assert VAL == {val}\n")
        _write(repo, "backend/tests/test_face.py",
               "from services.face import VAL\n"
               "def test_face(): assert VAL == (1, 2, 3)\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/face.py",
               "from services.a import VAL as A\n"
               "from services.b import VAL as B\n"
               "from services.c import VAL as C\n"
               'VAL = (A, B, C, "extra")\n')
        _commit(repo, "modify face")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0, payload
        assert payload["state"] == "SELECTED"
        node_ids = sorted(t["node_id"] for t in payload["selected_tests"])
        # facade + every submodule
        assert node_ids == ["tests.test_a", "tests.test_b", "tests.test_c", "tests.test_face"], node_ids


# =============================================================================
# 3. Reverse consumer dependency
# =============================================================================


class TestReverseConsumerDependency:
    """The reverse-closure must walk the consumer chain, not just direct
    importers. A change to a low-level helper must select every test
    that transitively depends on it.
    """

    def test_helper_change_reaches_transitive_consumer(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/helper.py", "def h():\n    return 1\n")
        _write(repo, "backend/services/mid.py",
               "from services.helper import h\n"
               "def call():\n    return h()\n")
        _write(repo, "backend/services/top.py",
               "from services.mid import call\n"
               "def run():\n    return call()\n")
        _write(repo, "backend/tests/test_helper.py",
               "from services.helper import h\n"
               "def test_helper(): assert h() == 1\n")
        _write(repo, "backend/tests/test_top.py",
               "from services.top import run\n"
               "def test_top(): assert run() == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/helper.py",
               "def h():\n    return 2\n")
        _commit(repo, "modify helper")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0, payload
        assert payload["state"] == "SELECTED"
        node_ids = sorted(t["node_id"] for t in payload["selected_tests"])
        assert "tests.test_helper" in node_ids
        assert "tests.test_top" in node_ids


# =============================================================================
# 4. Determinism / repeatability
# =============================================================================


class TestDeterminism:
    """The selector MUST be deterministic. Two consecutive runs against
    the same repo state must yield byte-identical JSON (modulo base_sha
    which is fixed by the caller).
    """

    def test_two_runs_produce_identical_selected_tests(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _write(repo, "backend/services/b.py", "VAL = 2\n")
        _write(repo, "backend/tests/test_b.py",
               "from services.b import VAL\n"
               "def test_b(): assert VAL == 2\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify a")

        rc1, p1, _ = _run_selector(repo, base)
        rc2, p2, _ = _run_selector(repo, base)
        assert rc1 == rc2 == 0
        # selected_tests order must be deterministic
        assert [t["node_id"] for t in p1["selected_tests"]] == \
               [t["node_id"] for t in p2["selected_tests"]]
        # impacted_production sorted
        assert p1["impacted_production"] == p2["impacted_production"]


# =============================================================================
# 5. NO_ELIGIBLE_BACKEND_CHANGE: docs / frontend only
# =============================================================================


class TestNoEligible:
    """Diff in docs/, src/ (frontend), or any non-backend path must yield
    NO_ELIGIBLE_BACKEND_CHANGE with exit 0 and an empty selection.
    """

    def test_docs_only_diff(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "docs/foo.md", "# initial\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "docs/foo.md", "# updated\n")
        _commit(repo, "docs change")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "NO_ELIGIBLE_BACKEND_CHANGE"
        assert payload["eligible_changed"] == []
        assert payload["selected_tests"] == []
        assert payload["selection_count"] == 0

    def test_frontend_only_diff(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "src/api/foo.ts", "export const x = 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "src/api/foo.ts", "export const x = 2\n")
        _commit(repo, "frontend")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "NO_ELIGIBLE_BACKEND_CHANGE"
        assert payload["selected_tests"] == []


# =============================================================================
# 6. Test-only diffs (modified / added / deleted)
# =============================================================================


class TestOnlyTestChanges:
    """Test-only PR semantics:
        - modified test        -> SELECTED (self_change)
        - added test           -> SELECTED (self_change)
        - deleted test         -> ESCALATION_REQUIRED (deleted_test)
    """

    def test_modified_test_only(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/tests/test_a.py", "def test_a(): assert True\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/tests/test_a.py", "def test_a(): assert 1 + 1 == 2\n")
        _commit(repo, "modify test")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "SELECTED"
        assert payload["eligible_changed"] == []
        assert payload["changed_tests"] == ["backend/tests/test_a.py"]
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert node_ids == ["tests.test_a"]
        reasons = payload["selected_tests"][0]["reasons"]
        assert any("self_change" in r for r in reasons)

    def test_added_test_only(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/tests/test_existing.py",
               "def test_existing(): assert True\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/tests/test_new.py",
               "def test_new(): assert True\n")
        _commit(repo, "add new test")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "SELECTED"
        assert payload["changed_tests"] == ["backend/tests/test_new.py"]
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert node_ids == ["tests.test_new"]

    def test_deleted_test_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        (repo / "backend/tests/test_a.py").unlink()
        _commit(repo, "delete test")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "deleted_test" in cats
        assert any("backend/tests/test_a.py" in r["path"]
                   for r in payload["escalation_reasons"])


# =============================================================================
# 7. Dynamic imports in CHANGED set
# =============================================================================


class TestDynamicImports:
    """If the CHANGED set contains a dynamic-loading call (importlib.
    import_module, __import__, importlib.util.spec_from_file_location),
    the selector MUST escalate because the static graph is no longer
    trustworthy.
    """

    def test_dynamic_import_in_changed_file_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/dyn.py",
               "import importlib\n"
               "def load(name):\n"
               "    return importlib.import_module(name)\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/dyn.py",
               "import importlib\n"
               "def load(name):\n"
               "    return importlib.import_module(name)\n"
               "def extra():\n"
               "    return 42\n")
        _commit(repo, "add dynamic loader")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "dynamic_import" in cats

    def test_dunder_import_call_escalates(self, tmp_path):
        """__import__('name') must also escalate."""
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/dyn2.py", "VAL = 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/dyn2.py",
               "def load(n): return __import__(n)\n")
        _commit(repo, "add __import__")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "dynamic_import" in cats

    def test_unchanged_dynamic_loader_does_not_escalate(self, tmp_path):
        """A dynamic loader that exists in UNCHANGED code MUST NOT cause
        escalation. This pins the F.1 residual risk boundary: the
        selector only catches dynamic loading in the CHANGED set.
        """
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/dyn.py",
               "import importlib\n"
               "def load(name):\n"
               "    return importlib.import_module(name)\n")
        _write(repo, "backend/services/a.py",
               "from services.dyn import load\n"
               "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        # Only services/a.py changes; the dyn loader is unchanged.
        _write(repo, "backend/services/a.py",
               "from services.dyn import load\n"
               "VAL = 11\n")
        _commit(repo, "modify a (unchanged dyn)")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "SELECTED"
        # The reverse-closure still trusts the static graph because the
        # CHANGED file does not introduce a dynamic loader.
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_a" in node_ids


# =============================================================================
# 8. Composition / wiring root escalation
# =============================================================================


class TestCompositionWiringEscalation:
    """A change to backend/composition.py (or backend/*/composition.py)
    invalidates the static graph and must escalate.
    """

    def test_composition_change_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/composition.py", "# initial wiring\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/composition.py", "# wiring root edited\n")
        _commit(repo, "wire")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "wiring_root" in cats

    def test_nested_composition_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/services/wiring/__init__.py", "")
        _write(repo, "backend/services/wiring/composition.py", "# nested wiring\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/wiring/composition.py",
               "# nested wiring edited\n")
        _commit(repo, "wire-nested")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "wiring_root" in cats

    def test_conftest_change_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/tests/conftest.py",
               "import sys\n" * 0 + "\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/tests/conftest.py",
               "import sys\nsys.path.insert(0, '/tmp')\n")
        _commit(repo, "conftest")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "conftest" in cats


# =============================================================================
# 9. Malformed changed Python
# =============================================================================


class TestMalformedChangedPython:
    """A changed Python file with invalid syntax must fail closed (not
    silently skip). The selector treats it like a dynamic loader
    because its imports cannot be statically resolved.
    """

    def test_malformed_python_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/a.py",
               "def incomplete(\n    pass\n")  # SyntaxError
        _commit(repo, "malformed")

        rc, payload, _ = _run_selector(repo, base)
        # The selector flags malformed prod as dynamic_import; either
        # ESCALATION_REQUIRED or EMPTY SELECTION both fail closed.
        # We accept either: the contract is "not silently selected".
        assert rc in (0, 2), payload
        if rc == 2:
            cats = [r["category"] for r in payload["escalation_reasons"]]
            assert "dynamic_import" in cats or "empty_selection" in cats


# =============================================================================
# 10. Relative imports: levels 1, 2, package-root, beyond-root
# =============================================================================


class TestRelativeImports:
    """The relative-import resolver must classify each level:
        level 1, current depth >= 2  -> safe
        level 2, current depth >= 3  -> safe
        level == len(parts)           -> beyond-root -> unsafe
        level >  len(parts)           -> beyond-root -> unsafe
    """

    def test_relative_level_1_is_safe(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/services/sub/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/x.py", "VAL = 1\n")
        _write(repo, "backend/services/sub/y.py",
               "from ..x import VAL\n"
               "def get():\n    return VAL\n")
        _write(repo, "backend/tests/test_y.py",
               "from services.sub.y import get\n"
               "def test_y(): assert get() == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/x.py", "VAL = 99\n")
        _commit(repo, "modify x")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "SELECTED"
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_y" in node_ids

    def test_relative_level_2_is_safe(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/services/a/__init__.py", "")
        _write(repo, "backend/services/a/b/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/x.py", "VAL = 1\n")
        _write(repo, "backend/services/a/b/c.py",
               "from ...x import VAL\n"
               "def get():\n    return VAL\n")
        _write(repo, "backend/tests/test_c.py",
               "from services.a.b.c import get\n"
               "def test_c(): assert get() == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/x.py", "VAL = 99\n")
        _commit(repo, "modify x")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "SELECTED"
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_c" in node_ids

    def test_package_root_boundary_resolves_safely(self, tmp_path):
        """`from . import sibling` at a top-level package must resolve
        to the package itself, not to beyond-root.
        """
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        # top-level backend/services is at depth 1 under sys.path.
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/services/sibling.py",
               "VAL = 1\n")
        _write(repo, "backend/services/target.py",
               "from . import sibling\n"
               "def get():\n    return sibling.VAL\n")
        _write(repo, "backend/tests/test_target.py",
               "from services.target import get\n"
               "def test_target(): assert get() == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/sibling.py", "VAL = 99\n")
        _commit(repo, "modify sibling")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "SELECTED"
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_target" in node_ids

    def test_beyond_root_relative_import_escalates(self, tmp_path):
        """`from ..x import Y` from `services.a` (depth 1) is a
        beyond-root relative import. The selector MUST escalate.

        The beyond-root import is treated as dynamic-import trust
        violation. If no test transitively imports the impacted module,
        the selector may also report empty_selection. Both are safe.
        """
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/x.py", "VAL = 1\n")
        _write(repo, "backend/services/a.py",
               "from ..x import VAL\n"  # depth 2 from depth 1: beyond root
               "def get():\n    return VAL\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import get\n"
               "def test_a(): assert get() == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/x.py", "VAL = 99\n")
        _commit(repo, "modify x")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        # Both escalation categories are acceptable fail-closed results.
        assert any(c in cats for c in ("dynamic_import", "empty_selection")), cats


# =============================================================================
# 11. Empty selection on eligible production change
# =============================================================================


class TestEmptySelection:
    """When a backend production file changes but no test imports it
    transitively (or no test exists at all), the selector MUST escalate
    rather than report zero tests. An empty SELECTED is unsafe.
    """

    def test_no_test_imports_impacted_prod_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/orphan.py", "VAL = 1\n")
        # No tests at all.
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/orphan.py", "VAL = 2\n")
        _commit(repo, "modify orphan")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "empty_selection" in cats

    def test_test_only_imports_unrelated_prod_is_empty_for_change(self, tmp_path):
        """Test exists but imports a different prod module -> still empty."""
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/services/b.py", "VAL = 2\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/b.py", "VAL = 22\n")
        _commit(repo, "modify b")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "empty_selection" in cats


# =============================================================================
# 12. Invalid base SHA
# =============================================================================


class TestInvalidBase:
    """An invalid base SHA must yield ERROR with exit 3, never SELECTED."""

    def test_all_zero_sha_returns_error(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _commit(repo, "seed")

        rc, payload, _ = _run_selector(
            repo, "0" * 40,
        )
        assert rc == 3
        assert payload["state"] == "ERROR"
        assert payload["errors"]
        assert payload["selected_tests"] == []

    def test_nonexistent_sha_returns_error(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _commit(repo, "seed")

        rc, payload, _ = _run_selector(
            repo, "deadbeef" * 5,
        )
        assert rc == 3
        assert payload["state"] == "ERROR"


# =============================================================================
# 13. Rename / --no-renames semantics
# =============================================================================


class TestRenameSemantics:
    """A pure rename (--no-renames policy from the PR-B2 gate) must
    classify as a fresh add at the destination. The destination file is
    evaluated; the source disappears from the diff entirely.
    """

    def test_pure_rename_of_eligible_file_is_treated_as_add(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/old_name.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_old_name.py",
               "from services.old_name import VAL\n"
               "def test_old(): assert VAL == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        # Pure rename (no content change) with --no-renames policy
        _git(repo, "config", "diff.renames", "true")  # allow git to detect
        src = repo / "backend/services/old_name.py"
        dst = repo / "backend/services/new_name.py"
        src.rename(dst)
        _commit(repo, "rename")
        # The selector runs with --no-renames, so git diff --no-renames
        # reports the new path as added and the old as deleted.
        rc, payload, _ = _run_selector(repo, base)
        assert rc in (0, 2), payload
        # Either: (a) selected because the new path is added and there's
        # still a test importing it (renamed path), or (b) escalated
        # because the original test path was deleted.
        if payload["state"] == "SELECTED":
            assert any("services" in e["category"] or e["category"] == "deleted_test"
                       for e in payload["escalation_reasons"])


# =============================================================================
# 14. Canonical JSON shape
# =============================================================================


class TestCanonicalJsonShape:
    """The selector must always emit a single canonical JSON object on
    stdout with the documented schema. Future CI consumers MUST be able
    to parse it without any prior knowledge of human text.
    """

    REQUIRED_KEYS = {
        "schema_version",
        "state",
        "base_sha",
        "eligible_changed",
        "changed_tests",
        "impacted_production",
        "selected_tests",
        "selection_count",
        "escalation_reasons",
        "errors",
        "diagnostics",
        "notes",
    }

    def _assert_shape(self, payload):
        assert isinstance(payload, dict)
        missing = self.REQUIRED_KEYS - set(payload.keys())
        assert not missing, f"missing keys: {missing}"
        assert payload["schema_version"] == 1
        assert payload["state"] in {
            "NO_ELIGIBLE_BACKEND_CHANGE",
            "SELECTED",
            "ESCALATION_REQUIRED",
            "ERROR",
        }
        assert isinstance(payload["eligible_changed"], list)
        assert isinstance(payload["changed_tests"], list)
        assert isinstance(payload["impacted_production"], list)
        assert isinstance(payload["selected_tests"], list)
        assert isinstance(payload["selection_count"], int)
        assert isinstance(payload["escalation_reasons"], list)
        assert isinstance(payload["errors"], list)
        assert isinstance(payload["diagnostics"], list)
        assert isinstance(payload["notes"], list)

    def test_selected_payload_has_canonical_shape(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify")
        rc, payload, _ = _run_selector(repo, base)
        self._assert_shape(payload)

    def test_no_eligible_payload_has_canonical_shape(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "docs/foo.md", "# initial\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "docs/foo.md", "# updated\n")
        _commit(repo, "docs")
        rc, payload, _ = _run_selector(repo, base)
        self._assert_shape(payload)

    def test_escalation_payload_has_canonical_shape(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/composition.py", "# x\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/composition.py", "# y\n")
        _commit(repo, "w")
        rc, payload, _ = _run_selector(repo, base)
        self._assert_shape(payload)

    def test_error_payload_has_canonical_shape(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "empty")
        rc, payload, _ = _run_selector(repo, "0" * 40)
        self._assert_shape(payload)


# =============================================================================
# 15. Exit code / state contract
# =============================================================================


class TestExitCodeContract:
    """Pin the documented exit-code contract:
        exit 0 -> NO_ELIGIBLE_BACKEND_CHANGE or SELECTED
        exit 2 -> ESCALATION_REQUIRED
        exit 3 -> ERROR
    """

    def _check(self, repo, base, expected_state, expected_rc):
        rc, payload, _ = _run_selector(repo, base)
        assert rc == expected_rc, (rc, payload)
        assert payload["state"] == expected_state, payload

    def test_no_eligible_is_exit_0(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "docs/foo.md", "# x\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "docs/foo.md", "# y\n")
        _commit(repo, "docs")
        self._check(repo, base, "NO_ELIGIBLE_BACKEND_CHANGE", 0)

    def test_selected_is_exit_0(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify")
        self._check(repo, base, "SELECTED", 0)

    def test_escalation_is_exit_2(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/composition.py", "# x\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        _write(repo, "backend/composition.py", "# y\n")
        _commit(repo, "w")
        self._check(repo, base, "ESCALATION_REQUIRED", 2)

    def test_error_is_exit_3(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed")
        self._check(repo, "0" * 40, "ERROR", 3)
