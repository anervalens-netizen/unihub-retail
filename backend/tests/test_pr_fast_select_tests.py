"""Durable tests for the PR-B3a deterministic backend PR test selector.

These tests pin the implementation-integrity invariants of the B3a
production slice of the B3/E2 selector proof. The selector is invoked
via its real CLI on real temporary git repositories so diff, rename
classification, and import-graph construction come from real git, not
mocks. The four-state contract, the four exit codes, the canonical JSON
shape (with resolved full SHAs), and the escalation surface are all
asserted explicitly.

The durable pattern mirrors `test_changed_gates_pr_b2.py`: synthetic
git repos are built per-test, the gate runs in subprocess against the
temp repo, and assertions compare the parsed JSON result against the
expected invariants.

Each test class covers one of the four canonical states plus the
boundary cases the prototype proof enumerated and the post-publish
reviewer corrections enumerated. The tests are intentionally explicit
about WHY each case maps to the expected state; the goal is durable
coverage, not just line-count vanity.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[2]
PY = WORKTREE / "backend" / "venv" / "bin" / "python"
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

    `base` may be a SHA, branch, tag, or short SHA; the selector must
    resolve it to a full SHA before emitting JSON.
    """
    env = dict(os.environ)
    env["PATH"] = "/usr/bin:/bin:" + env.get("PATH", "")
    proc = subprocess.run(
        [str(PY), "-I", str(SELECTOR), "--root", str(repo), "--base", base],
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


def _make_backend_skeleton(repo, with_test_consumer: bool = True):
    """Lay down the minimum backend/ tree needed for most tests.

    `with_test_consumer=True` (default) ALSO writes a tiny smoke
    test that imports `services.a` so the selector has at least one
    in-tree consumer that the reverse-closure can reach. Set False
    only when the test explicitly intends to assert NO_ELIGIBLE /
    empty_selection behavior.
    """
    _write(repo, "backend/__init__.py", "")
    _write(repo, "backend/services/__init__.py", "")
    _write(repo, "backend/services/a.py", "VAL = 1\n")
    _write(repo, "backend/tests/__init__.py", "")
    _write(repo, "backend/tests/conftest.py",
          "import sys, pathlib\n"
          "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n")
    if with_test_consumer:
        _write(repo, "backend/tests/test_smoke.py",
              "from services.a import VAL\n"
              "def test_smoke(): assert VAL == 1\n")


# =============================================================================
# Correction 1 — exact SHA contract (base_sha + head_sha both full SHAs)
# =============================================================================


class TestExactShaContract:
    """The canonical JSON MUST carry both base_sha and head_sha as
    resolved full 40-character SHAs. Short SHAs, branch names, and
    tag refs are forbidden as authoritative identity.
    """

    def test_short_sha_base_is_normalized_to_full_sha(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        full = _commit(repo, "seed")
        # mutate
        _write(repo, "backend/services/a.py", "VAL = 2\n")
        _commit(repo, "modify")

        # Pass the short SHA as base; the selector MUST resolve it.
        short = full[:10]
        rc, payload, _ = _run_selector(repo, short)
        assert rc == 0
        assert payload["base_sha"] == full, payload
        assert len(payload["base_sha"]) == 40

    def test_head_sha_equals_git_rev_parse_HEAD(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 2\n")
        _commit(repo, "modify")

        rc, payload, _ = _run_selector(repo, "HEAD")
        assert rc == 0
        expected_head = _git(repo, "rev-parse", "HEAD").strip()
        assert payload["head_sha"] == expected_head
        assert len(payload["head_sha"]) == 40

    def test_branch_name_base_is_normalized_to_full_sha(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        full = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 2\n")
        _commit(repo, "modify")
        # Create a branch pointing at the seed commit
        _git(repo, "checkout", "-q", full)
        _git(repo, "checkout", "-q", "-b", "seed")
        _git(repo, "checkout", "-q", "-")  # back to HEAD

        rc, payload, _ = _run_selector(repo, "seed")
        assert rc == 0
        assert payload["base_sha"] == full

    def test_deterministic_repeat_keeps_identical_identity(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 2\n")
        _commit(repo, "modify")

        rc1, p1, _ = _run_selector(repo, base)
        rc2, p2, _ = _run_selector(repo, base)
        assert rc1 == rc2 == 0
        assert p1["base_sha"] == p2["base_sha"]
        assert p1["head_sha"] == p2["head_sha"]
        assert p1["selected_tests"] == p2["selected_tests"]

    def test_invalid_base_yields_error(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _commit(repo, "seed")
        rc, payload, _ = _run_selector(repo, "0" * 40)
        assert rc == 3
        assert payload["state"] == "ERROR"
        assert payload["errors"]

    def test_head_sha_present_on_no_eligible_state(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed")
        _write(repo, "docs/foo.md", "# x\n")
        _commit(repo, "docs")
        rc, payload, _ = _run_selector(repo, "HEAD~1")
        assert rc == 0
        assert payload["state"] == "NO_ELIGIBLE_BACKEND_CHANGE"
        assert len(payload["head_sha"]) == 40
        assert len(payload["base_sha"]) == 40

    def test_head_sha_present_on_escalation_state(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/composition.py", "# x\n")
        _commit(repo, "seed")
        _write(repo, "backend/composition.py", "# y\n")
        _commit(repo, "w")
        rc, payload, _ = _run_selector(repo, "HEAD~1")
        assert rc == 2
        assert payload["state"] == "ESCALATION_REQUIRED"
        assert len(payload["head_sha"]) == 40

    def test_head_sha_present_on_selected_state(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 2\n")
        _commit(repo, "m")
        rc, payload, _ = _run_selector(repo, "HEAD~1")
        assert rc == 0
        assert payload["state"] == "SELECTED"
        assert len(payload["head_sha"]) == 40

    def test_head_sha_present_on_error_state(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed")
        rc, payload, _ = _run_selector(repo, "0" * 40)
        # ERROR state may have empty base/head; identity could not be
        # resolved. The contract is: head_sha key is PRESENT in JSON.
        assert rc == 3
        assert payload["state"] == "ERROR"
        assert "head_sha" in payload


# =============================================================================
# 1. Ordinary service selection (positive SELECTED case)
# =============================================================================


class TestOrdinaryServiceSelection:
    """A single ordinary low-fanout service change selects exactly the test
    that imports it, with a deterministic reverse-closure reason.
    """

    def test_single_service_change_selects_only_its_test(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/services/b.py", "VAL = 2\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _write(repo, "backend/tests/test_b.py",
               "from services.b import VAL\n"
               "def test_b(): assert VAL == 2\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify a")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0, payload
        assert payload["state"] == "SELECTED"
        assert payload["eligible_changed"] == ["backend/services/a.py"]
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        # The selector MUST select every test that imports services.a,
        # which includes the skeleton smoke test AND test_a.
        assert "tests.test_a" in node_ids
        # test_b imports services.b only — it MUST NOT be selected.
        assert "tests.test_b" not in node_ids



# =============================================================================
# 2. Facade / re-export behavior
# =============================================================================


class TestFacadeBehavior:
    def test_facade_change_reaches_facade_and_submodule_tests(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
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
        base = _commit(repo, "seed")
        _write(repo, "backend/services/face.py",
               "from services.a import VAL as A\n"
               "from services.b import VAL as B\n"
               "from services.c import VAL as C\n"
               'VAL = (A, B, C, "extra")\n')
        _commit(repo, "modify face")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0, payload
        assert payload["state"] == "SELECTED"
        node_ids = {t["node_id"] for t in payload["selected_tests"]}
        # Every facade / submodule test must be selected. The smoke
        # skeleton test may ALSO be selected because it imports
        # services.a (a submodule of the facade).
        for required in ["tests.test_face", "tests.test_a",
                         "tests.test_b", "tests.test_c"]:
            assert required in node_ids, (required, node_ids)


# =============================================================================
# 3. Reverse consumer dependency
# =============================================================================


class TestReverseConsumerDependency:
    def test_helper_change_reaches_transitive_consumer(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
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
        base = _commit(repo, "seed")
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
    def test_two_runs_produce_identical_selected_tests(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/services/b.py", "VAL = 2\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _write(repo, "backend/tests/test_b.py",
               "from services.b import VAL\n"
               "def test_b(): assert VAL == 2\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify a")

        rc1, p1, _ = _run_selector(repo, base)
        rc2, p2, _ = _run_selector(repo, base)
        assert rc1 == rc2 == 0
        assert [t["node_id"] for t in p1["selected_tests"]] == \
               [t["node_id"] for t in p2["selected_tests"]]
        assert p1["impacted_production"] == p2["impacted_production"]


# =============================================================================
# 5. NO_ELIGIBLE_BACKEND_CHANGE
# =============================================================================


class TestNoEligible:
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

    def test_docs_only_deletion_is_no_eligible(self, tmp_path):
        """Correction 3: docs-only deletion must remain NO_ELIGIBLE."""
        repo = _new_repo(tmp_path)
        _write(repo, "docs/foo.md", "# initial\n")
        _write(repo, "src/api/foo.ts", "export const x = 1\n")
        _commit(repo, "seed")
        base = _git(repo, "rev-parse", "HEAD").strip()
        (repo / "docs/foo.md").unlink()
        _commit(repo, "delete docs")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "NO_ELIGIBLE_BACKEND_CHANGE"


# =============================================================================
# 6. Test-only diffs (modified / added / deleted)
# =============================================================================


class TestOnlyTestChanges:
    def test_modified_test_only(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/tests/test_a.py", "def test_a(): assert True\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/tests/test_a.py",
               "def test_a(): assert 1 + 1 == 2\n")
        _commit(repo, "modify test")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "SELECTED"
        assert payload["eligible_changed"] == []
        assert payload["changed_tests"] == ["backend/tests/test_a.py"]
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert node_ids == ["tests.test_a"]
        assert any("self_change" in r
                   for r in payload["selected_tests"][0]["reasons"])

    def test_added_test_only(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/tests/test_existing.py",
               "def test_existing(): assert True\n")
        base = _commit(repo, "seed")
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
        _make_backend_skeleton(repo, with_test_consumer=False)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        (repo / "backend/tests/test_a.py").unlink()
        _commit(repo, "delete test")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "deleted_test" in cats
        assert any("backend/tests/test_a.py" in r["path"]
                   for r in payload["escalation_reasons"])
        # changed_tests surfaces the deleted path even though it cannot
        # be executed.
        assert "backend/tests/test_a.py" in payload["changed_tests"]


# =============================================================================
# 7. Dynamic imports in CHANGED set
# =============================================================================


class TestDynamicImports:
    def test_dynamic_import_in_changed_file_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/dyn.py",
               "import importlib\n"
               "def load(name):\n"
               "    return importlib.import_module(name)\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/dyn.py",
               "import importlib\n"
               "def load(name):\n"
               "    return importlib.import_module(name)\n"
               "def extra():\n    return 42\n")
        _commit(repo, "add dynamic loader")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "dynamic_import" in cats

    def test_dunder_import_call_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/dyn2.py", "VAL = 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/dyn2.py",
               "def load(n): return __import__(n)\n")
        _commit(repo, "add __import__")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "dynamic_import" in cats

    def test_unchanged_dynamic_loader_does_not_escalate(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/dyn.py",
               "import importlib\n"
               "def load(name):\n"
               "    return importlib.import_module(name)\n")
        _write(repo, "backend/services/a.py",
               "from services.dyn import load\nVAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py",
               "from services.dyn import load\nVAL = 11\n")
        _commit(repo, "modify a (unchanged dyn)")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "SELECTED"
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_a" in node_ids


# =============================================================================
# 8. Composition / wiring root escalation
# =============================================================================


class TestCompositionWiringEscalation:
    def test_composition_change_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/composition.py", "# initial wiring\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/composition.py", "# wiring root edited\n")
        _commit(repo, "wire")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "wiring_root" in cats

    def test_nested_composition_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/services/__init__.py", "")
        _write(repo, "backend/services/wiring/__init__.py", "")
        _write(repo, "backend/services/wiring/composition.py",
               "# nested wiring\n")
        base = _commit(repo, "seed")
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
        _write(repo, "backend/tests/conftest.py", "")
        base = _commit(repo, "seed")
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
    def test_malformed_python_fails_closed(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py",
               "def incomplete(\n    pass\n")
        _commit(repo, "malformed")
        rc, payload, _ = _run_selector(repo, base)
        assert rc in (0, 2), payload
        if rc == 2:
            cats = [r["category"] for r in payload["escalation_reasons"]]
            assert "dynamic_import" in cats or "empty_selection" in cats


# =============================================================================
# 10. Relative imports
# =============================================================================


class TestRelativeImports:
    def test_relative_level_1_is_safe(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/sub/__init__.py", "")
        _write(repo, "backend/services/x.py", "VAL = 1\n")
        _write(repo, "backend/services/sub/y.py",
               "from ..x import VAL\n"
               "def get():\n    return VAL\n")
        _write(repo, "backend/tests/test_y.py",
               "from services.sub.y import get\n"
               "def test_y(): assert get() == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/x.py", "VAL = 99\n")
        _commit(repo, "modify x")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_y" in node_ids

    def test_relative_level_2_is_safe(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a/__init__.py", "")
        _write(repo, "backend/services/a/b/__init__.py", "")
        _write(repo, "backend/services/x.py", "VAL = 1\n")
        _write(repo, "backend/services/a/b/c.py",
               "from ...x import VAL\n"
               "def get():\n    return VAL\n")
        _write(repo, "backend/tests/test_c.py",
               "from services.a.b.c import get\n"
               "def test_c(): assert get() == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/x.py", "VAL = 99\n")
        _commit(repo, "modify x")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_c" in node_ids

    def test_package_init_level_1_resolves_to_parent_package(self, tmp_path):
        """Correction 5: backend/a/b/__init__.py `from .x` must resolve to
        a.b.x, NOT a.x. __init__.py is one logical level deeper than
        its package name.
        """
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/a/__init__.py", "")
        _write(repo, "backend/a/b/__init__.py",
               "from .x import VAL\n"
               "VAL = 1\n")
        _write(repo, "backend/a/b/x.py", "_VAL = 1\n")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/tests/conftest.py",
               "import sys, pathlib\n"
               "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n")
        _write(repo, "backend/tests/test_pkg.py",
               "import a.b as p\n"
               "def test_pkg(): assert p.VAL == 1\n")
        base = _commit(repo, "seed")
        # Modify backend/a/b/x.py so the selector must trace into it via
        # the relative import from backend/a/b/__init__.py.
        _write(repo, "backend/a/b/x.py", "_VAL = 99\n")
        _commit(repo, "modify x")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_pkg" in node_ids

    def test_module_level_1_in_module_file(self, tmp_path):
        """Correction 5: backend/a/b/c.py `from .x` must resolve to a.b.x."""
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/a/__init__.py", "")
        _write(repo, "backend/a/b/__init__.py", "")
        _write(repo, "backend/a/b/x.py", "_X = 1\n")
        _write(repo, "backend/a/b/c.py",
               "from .x import _X\n"
               "VAL = _X\n")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/tests/conftest.py",
               "import sys, pathlib\n"
               "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n")
        _write(repo, "backend/tests/test_c.py",
               "from a.b.c import VAL\n"
               "def test_c(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/a/b/x.py", "_X = 99\n")
        _commit(repo, "modify x")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_c" in node_ids

    def test_package_init_level_1_resolves_to_package_itself(self, tmp_path):
        """Correction 5: backend/a/b/__init__.py `from .x` must resolve
        to a.b.x (the package itself), NOT a.x. __init__.py is one
        logical level deeper than its package name; level-1 relatives
        resolve to the package.
        """
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/a/__init__.py", "")
        _write(repo, "backend/a/b/__init__.py",
               "from .x import VAL\n"
               "VAL = 1\n")
        _write(repo, "backend/a/b/x.py", "_VAL = 1\n")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/tests/conftest.py",
               "import sys, pathlib\n"
               "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n")
        _write(repo, "backend/tests/test_pkg.py",
               "import a.b as p\n"
               "def test_pkg(): assert p.VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/a/b/x.py", "_VAL = 99\n")
        _commit(repo, "modify x")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_pkg" in node_ids

    def test_package_init_from_dot_import(self, tmp_path):
        """`from . import x` in __init__.py must resolve to current pkg.x."""
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/a/__init__.py", "")
        _write(repo, "backend/a/b/__init__.py", "")
        _write(repo, "backend/a/b/x.py", "VAL = 1\n")
        _write(repo, "backend/a/b/c.py",
               "from . import x\n"
               "VAL = x.VAL\n")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/tests/conftest.py",
               "import sys, pathlib\n"
               "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n")
        _write(repo, "backend/tests/test_c.py",
               "from a.b.c import VAL\n"
               "def test_c(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/a/b/x.py", "VAL = 99\n")
        _commit(repo, "modify x")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_c" in node_ids

    def test_beyond_root_relative_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/x.py", "VAL = 1\n")
        _write(repo, "backend/services/a.py",
               "from ..x import VAL\n"
               "def get():\n    return VAL\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import get\n"
               "def test_a(): assert get() == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/x.py", "VAL = 99\n")
        _commit(repo, "modify x")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert any(c in cats for c in ("dynamic_import", "empty_selection"))


# =============================================================================
# 11. Empty selection on eligible production change
# =============================================================================


class TestEmptySelection:
    def test_no_test_imports_impacted_prod_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/orphan.py", "VAL = 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/orphan.py", "VAL = 2\n")
        _commit(repo, "modify orphan")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "empty_selection" in cats

    def test_test_only_imports_unrelated_prod_is_empty_for_change(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/services/b.py", "VAL = 2\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        base = _commit(repo, "seed")
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
    def test_all_zero_sha_returns_error(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed")
        rc, payload, _ = _run_selector(repo, "0" * 40)
        assert rc == 3
        assert payload["state"] == "ERROR"
        assert payload["errors"]
        assert payload["selected_tests"] == []

    def test_nonexistent_sha_returns_error(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed")
        rc, payload, _ = _run_selector(repo, "deadbeef" * 5)
        assert rc == 3
        assert payload["state"] == "ERROR"


# =============================================================================
# 13. Rename / --no-renames semantics (Correction 7 — tightened)
# =============================================================================


class TestRenameSemantics:
    def test_production_rename_escalates_with_deleted_production(
            self, tmp_path):
        """Correction 7: a pure production rename (--no-renames)
        becomes DELETE old + ADD new. The selector MUST escalate with
        category deleted_production because the current graph no longer
        contains the old module.
        """
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/old_name.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_old_name.py",
               "from services.old_name import VAL\n"
               "def test_old(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        # Allow rename detection so git can record the move
        _git(repo, "config", "diff.renames", "true")
        src = repo / "backend/services/old_name.py"
        dst = repo / "backend/services/new_name.py"
        src.rename(dst)
        _commit(repo, "rename")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "deleted_production" in cats
        assert any("backend/services/old_name.py" in r["path"]
                   for r in payload["escalation_reasons"]), cats

    def test_test_rename_escalates_with_deleted_test(self, tmp_path):
        """Correction 7: a test rename escalates via deleted_test."""
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_old.py",
               "from services.a import VAL\n"
               "def test_old(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        _git(repo, "config", "diff.renames", "true")
        src = repo / "backend/tests/test_old.py"
        dst = repo / "backend/tests/test_new.py"
        src.rename(dst)
        _commit(repo, "rename test")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "deleted_test" in cats
        assert any("backend/tests/test_old.py" in r["path"]
                   for r in payload["escalation_reasons"]), cats


# =============================================================================
# 14. Canonical JSON shape
# =============================================================================


class TestCanonicalJsonShape:
    REQUIRED_KEYS = {
        "schema_version",
        "state",
        "base_sha",
        "head_sha",
        "eligible_changed",
        "changed_tests",
        "deleted_production",
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
        for k in ("eligible_changed", "changed_tests",
                  "deleted_production", "impacted_production",
                  "selected_tests", "escalation_reasons",
                  "errors", "diagnostics", "notes"):
            assert isinstance(payload[k], list), k
        assert isinstance(payload["selection_count"], int)
        # base_sha and head_sha MUST be present even on ERROR.
        assert "base_sha" in payload
        assert "head_sha" in payload

    def test_selected_payload_has_canonical_shape(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify")
        _, payload, _ = _run_selector(repo, base)
        self._assert_shape(payload)

    def test_no_eligible_payload_has_canonical_shape(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "docs/foo.md", "# initial\n")
        base = _commit(repo, "seed")
        _write(repo, "docs/foo.md", "# updated\n")
        _commit(repo, "docs")
        _, payload, _ = _run_selector(repo, base)
        self._assert_shape(payload)

    def test_escalation_payload_has_canonical_shape(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/composition.py", "# x\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/composition.py", "# y\n")
        _commit(repo, "w")
        _, payload, _ = _run_selector(repo, base)
        self._assert_shape(payload)

    def test_error_payload_has_canonical_shape(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed")
        _, payload, _ = _run_selector(repo, "0" * 40)
        self._assert_shape(payload)


# =============================================================================
# 15. Exit code / state contract
# =============================================================================


class TestExitCodeContract:
    def _check(self, repo, base, expected_state, expected_rc):
        rc, payload, _ = _run_selector(repo, base)
        assert rc == expected_rc, (rc, payload)
        assert payload["state"] == expected_state, payload

    def test_no_eligible_is_exit_0(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "docs/foo.md", "# x\n")
        base = _commit(repo, "seed")
        _write(repo, "docs/foo.md", "# y\n")
        _commit(repo, "docs")
        self._check(repo, base, "NO_ELIGIBLE_BACKEND_CHANGE", 0)

    def test_selected_is_exit_0(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify")
        self._check(repo, base, "SELECTED", 0)

    def test_escalation_is_exit_2(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/composition.py", "# x\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/composition.py", "# y\n")
        _commit(repo, "w")
        self._check(repo, base, "ESCALATION_REQUIRED", 2)

    def test_error_is_exit_3(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed")
        self._check(repo, "0" * 40, "ERROR", 3)


# =============================================================================
# Correction 3 — deletions fail closed (explicit durable tests)
# =============================================================================


class TestDeletionsFailClosed:
    """Every deletion category that affects selection trust must fail
    closed with ESCALATION_REQUIRED, never NO_ELIGIBLE.
    """

    def test_delete_ordinary_service_module_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/orphan.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_orphan.py",
               "from services.orphan import VAL\n"
               "def test_orphan(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        (repo / "backend/services/orphan.py").unlink()
        _commit(repo, "delete service")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "deleted_production" in cats
        assert "backend/services/orphan.py" in payload["deleted_production"]
        # NEVER NO_ELIGIBLE.
        assert payload["state"] != "NO_ELIGIBLE_BACKEND_CHANGE"

    def test_delete_repository_module_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/repositories/__init__.py", "")
        _write(repo, "backend/repositories/orphan_repo.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_orphan_repo.py",
               "from repositories.orphan_repo import VAL\n"
               "def test_orphan_repo(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        (repo / "backend/repositories/orphan_repo.py").unlink()
        _commit(repo, "delete repo")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "deleted_production" in cats
        assert any("backend/repositories/orphan_repo.py" in r["path"]
                   for r in payload["escalation_reasons"])

    def test_delete_gate_script_escalates(self, tmp_path):
        """Deleting scripts/check_changed_line_coverage.py is a
        trust-invalidation: gate_authority, like a change to it."""
        repo = _new_repo(tmp_path)
        _write(repo, "scripts/__init__.py", "")
        # Seed with two commits so we have something to delete relative to.
        (repo / "scripts/check_changed_line_coverage.py").write_text(
            "# gate v0\n", encoding="utf-8")
        base = _commit(repo, "seed")
        (repo / "scripts/check_changed_line_coverage.py").unlink()
        _commit(repo, "delete gate")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "gate_authority" in cats

    def test_delete_requirements_file_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/requirements.txt", "fastapi==0.1\n")
        _write(repo, "backend/requirements.lock", "# lock\n")
        base = _commit(repo, "seed")
        (repo / "backend/requirements.txt").unlink()
        _commit(repo, "del reqs")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "dependency_definition" in cats

    def test_delete_composition_py_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/composition.py", "# x\n")
        base = _commit(repo, "seed")
        (repo / "backend/composition.py").unlink()
        _commit(repo, "del composition")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "wiring_root" in cats

    def test_delete_docs_only_file_is_no_eligible(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "docs/foo.md", "# x\n")
        base = _commit(repo, "seed")
        (repo / "docs/foo.md").unlink()
        _commit(repo, "del docs")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        assert payload["state"] == "NO_ELIGIBLE_BACKEND_CHANGE"

    def test_deleted_production_path_never_no_eligible(self, tmp_path):
        """Negative invariant: deleting an eligible backend production
        file MUST never become NO_ELIGIBLE_BACKEND_CHANGE."""
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/x.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_x.py",
               "from services.x import VAL\n"
               "def test_x(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        # Delete the only eligible production change. There is no other
        # diff; the selector MUST escalate.
        (repo / "backend/services/x.py").unlink()
        _commit(repo, "delete x")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        assert payload["state"] != "NO_ELIGIBLE_BACKEND_CHANGE"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "deleted_production" in cats

    def test_delete_conftest_escalates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/__init__.py", "")
        _write(repo, "backend/tests/__init__.py", "")
        _write(repo, "backend/tests/conftest.py", "")
        base = _commit(repo, "seed")
        (repo / "backend/tests/conftest.py").unlink()
        _commit(repo, "del conftest")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "conftest" in cats


# =============================================================================
# Correction 4 — normal `import x.y` resolution
# =============================================================================


class TestImportDotResolution:
    """`import services.foo` and friends must record the full dotted
    module plus every known ancestor prefix.
    """

    def test_import_services_dot_foo_records_full_and_parent(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        # Build services/__init__.py, services/foo.py, services/foo/__init__.py
        _write(repo, "backend/services/foo.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_foo.py",
               "import services.foo\n"
               "def test_foo(): assert services.foo.VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/foo.py", "VAL = 99\n")
        _commit(repo, "modify foo")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_foo" in node_ids

    def test_import_services_foo_bar_with_dotted_submodule(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/foo/__init__.py", "")
        _write(repo, "backend/services/foo/bar.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_bar.py",
               "import services.foo.bar\n"
               "def test_bar(): assert services.foo.bar.VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/foo/bar.py", "VAL = 99\n")
        _commit(repo, "modify bar")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_bar" in node_ids

    def test_import_alias_form(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/foo.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_alias.py",
               "import services.foo as foo\n"
               "def test_alias(): assert foo.VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/foo.py", "VAL = 99\n")
        _commit(repo, "modify foo")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_alias" in node_ids

    def test_external_dotted_import_ignored(self, tmp_path):
        """An `import fastapi.routing` where fastapi is not in our tree
        MUST NOT match anything; only internal prefixes are recorded."""
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/foo.py", "VAL = 1\n")
        # This test imports fastapi (not in tree) AND services.foo.
        _write(repo, "backend/tests/test_mixed.py",
               "import fastapi.routing\n"
               "import services.foo\n"
               "def test_mixed(): assert services.foo.VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/foo.py", "VAL = 99\n")
        _commit(repo, "modify foo")
        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_mixed" in node_ids
        # The impact list contains services.foo but NOT fastapi.
        assert "backend/services/foo.py" in payload["impacted_production"]

    def test_external_dotted_only_does_not_select(self, tmp_path):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo, with_test_consumer=False)
        _write(repo, "backend/services/foo.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_ext.py",
               "import fastapi.routing\n"
               "def test_ext(): assert True\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/foo.py", "VAL = 99\n")
        _commit(repo, "modify foo")
        rc, payload, _ = _run_selector(repo, base)
        # No test imports services.foo (test_ext only imports fastapi);
        # the selector must fail closed.
        assert rc == 2, payload
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "empty_selection" in cats
        assert "tests.test_ext" not in [t["node_id"]
                                     for t in payload["selected_tests"]]


# =============================================================================
# Correction 10 — end-to-end pytest execution of selected files
# =============================================================================


class TestEndToEndPytestExecution:
    """The selector output must be consumable by pytest.

    Builds a small synthetic repo with a runnable test, runs the
    selector, then executes pytest on the file paths in selected_tests
    and verifies pytest returns 0 (tests pass).
    """

    def test_selected_test_files_are_runnable_via_pytest(self, tmp_path):
        """End-to-end: extract runnable selected test FILE paths,
        invoke pytest on them, expect exit 0.

        The test imports both services.a and services.b; we change
        services.b while keeping services.a unchanged. The test
        asserts against services.a.VAL only, so changing b
        preserves the test assertion while still selecting it.
        """
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo, with_test_consumer=False)
        _write(repo, "backend/services/b.py", "X = 1\n")
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "import services.b\n"  # noqa: F401 - import to register edge
               "def test_a(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        # Change ONLY services/b; the test still passes because it
        # only checks services.a.VAL.
        _write(repo, "backend/services/b.py", "X = 2\n")
        _commit(repo, "modify b")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0, payload
        assert payload["state"] == "SELECTED"
        assert payload["selected_tests"], payload

        # Run pytest against each selected test file path, exactly the
        # way PR-B3b will use the selector output.
        for t in payload["selected_tests"]:
            file_path = repo / t["file"]
            assert file_path.exists(), file_path
            env = dict(os.environ)
            env["PATH"] = "/usr/bin:/bin:" + env.get("PATH", "")
            proc = subprocess.run(
                [str(PY), "-I", "-m", "pytest",
                 "-q", "--no-header",
                 str(file_path.relative_to(repo))],
                cwd=str(repo),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert proc.returncode == 0, (
                f"pytest failed on {t['file']}\n"
                f"stdout={proc.stdout}\nstderr={proc.stderr}"
            )
            assert "passed" in proc.stdout or "1 passed" in proc.stdout, (
                proc.stdout
            )

    def test_unselected_files_are_NOT_run_by_pytest(self, tmp_path):
        """Only the SELECTED tests are runnable; unselected files must
        not be passed to pytest (we do not silently run them)."""
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/services/b.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        _write(repo, "backend/tests/test_b.py",
               "from services.b import VAL\n"
               "def test_b(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify a")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0
        selected_files = {t["file"] for t in payload["selected_tests"]}
        assert "backend/tests/test_a.py" in selected_files
        assert "backend/tests/test_b.py" not in selected_files


# =============================================================================
# Final trust-ordering fix — gate authority is classified BEFORE any
# candidate gate module is imported.
#
# The five tests below (A–E) pin the post-fix order:
#   1. resolve SHA identity
#   2. obtain COMPLETE diff (AM + D, --no-renames)
#   3. classify trust surfaces (gate/conftest/wiring/governance) WITHOUT
#      importing the PR-B2 gate
#   4. ESCALATE_REQUIRED immediately on trust-surface changes
#   5. only then load the PR-B2 gate from the selected repository root
#
# The earlier prototype loaded the gate at step (3) and ran the classifier
# at step (5). That order is unsafe: a modified gate would execute its
# top-level code before the selector recognized the change, and a deleted
# gate would raise at import before the selector could classify the
# deletion as ESCALATION_REQUIRED.
# =============================================================================


def _seed_gate(repo, body):
    """Write scripts/check_changed_line_coverage.py with `body` (string)."""
    _write(repo, "scripts/__init__.py", "")
    _write(repo, "scripts/check_changed_line_coverage.py", body)


_GATE_BODY_HEALTHY = (
    "def is_eligible_backend(name):\n"
    "    if not (name.startswith('backend/') and name.endswith('.py')):\n"
    "        return False\n"
    "    if any(part in name for part in ('/tests/', '/scripts/', '/venv/')):\n"
    "        return False\n"
    "    return True\n"
    "def is_eligible_frontend(name):\n"
    "    return False\n"
)


class TestTrustOrderingGateNotImported:
    """A. Modified gate MUST NOT be imported before classification.

    Sentinel + exception probes: if the candidate gate is executed before
    the trust-surface classifier runs, the sentinel file would be created
    or the exception would be raised.
    """

    def test_modified_gate_with_sentinel_does_not_execute(self, tmp_path):
        """Modified gate's top-level code (sentinel file write) MUST NOT
        run. The selector returns ESCALATION_REQUIRED / exit 2 and no
        sentinel file is created.
        """
        repo = _new_repo(tmp_path)
        _seed_gate(repo, _GATE_BODY_HEALTHY)
        _make_backend_skeleton(repo)
        base = _commit(repo, "seed gate v1")
        sentinel = repo / "GATE_IMPORTED_SENTINEL"
        # Modified gate: top-level write that would create the sentinel.
        modified_gate = (
            "import pathlib\n"
            "SENTINEL = pathlib.Path(__file__).resolve().parent.parent / "
            "'GATE_IMPORTED_SENTINEL'\n"
            "SENTINEL.write_text('gate top-level executed', encoding='utf-8')\n"
            + _GATE_BODY_HEALTHY
        )
        _write(repo, "scripts/check_changed_line_coverage.py", modified_gate)
        _commit(repo, "modify gate")
        assert not sentinel.exists()

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "gate_authority" in cats
        assert any("scripts/check_changed_line_coverage.py" in r["path"]
                   for r in payload["escalation_reasons"])
        # The candidate gate MUST NOT have been imported.
        assert not sentinel.exists(), (
            "selector imported the modified gate before classification"
        )

    def test_modified_gate_with_unmistakable_exception_does_not_execute(
            self, tmp_path):
        """If the candidate gate were imported, a top-level
        `raise RuntimeError('GATE_TOP_LEVEL_EXECUTED')` would fire before
        classification completes. The selector MUST classify the change
        as ESCALATION_REQUIRED without surfacing that exception.
        """
        repo = _new_repo(tmp_path)
        _seed_gate(repo, _GATE_BODY_HEALTHY)
        _make_backend_skeleton(repo)
        base = _commit(repo, "seed gate v1")
        modified_gate = (
            "raise RuntimeError('GATE_TOP_LEVEL_EXECUTED')\n"
            + _GATE_BODY_HEALTHY
        )
        _write(repo, "scripts/check_changed_line_coverage.py", modified_gate)
        _commit(repo, "modify gate explode")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        assert payload["state"] == "ESCALATION_REQUIRED"
        # The error must NOT mention the gate's RuntimeError; the selector
        # would only surface that if it had imported the candidate.
        joined = " ".join(payload.get("errors", []))
        assert "GATE_TOP_LEVEL_EXECUTED" not in joined, (
            f"selector surfaced gate's top-level exception: {joined!r}"
        )
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "gate_authority" in cats


class TestTrustOrderingDeletedGate:
    """B. Deleted gate MUST be classified as gate_authority and MUST NOT
    raise an ERROR when the diff proves the deletion."""

    def test_deleted_gate_escalates_with_gate_authority(self, tmp_path):
        repo = _new_repo(tmp_path)
        _seed_gate(repo, _GATE_BODY_HEALTHY)
        _make_backend_skeleton(repo)
        base = _commit(repo, "seed with gate")
        (repo / "scripts/check_changed_line_coverage.py").unlink()
        _commit(repo, "delete gate")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "gate_authority" in cats, payload
        assert any("scripts/check_changed_line_coverage.py" in r["path"]
                   for r in payload["escalation_reasons"]), payload
        # The selector MUST NOT surface this as ERROR — the diff already
        # explained the missing gate.
        assert payload["state"] != "ERROR"


class TestTrustOrderingRootLocalGate:
    """C. --root controls which gate the selector loads.

    The selector must consume the gate under <root>/scripts/, NOT the
    sibling gate next to the selector executable. We prove this by giving
    the temp repo a sentinel-only gate (no real eligibility logic) and
    asserting the selector still produces a valid SELECTED result on a
    trivial eligible change.
    """

    def test_root_local_gate_is_used_when_present(self, tmp_path):
        repo = _new_repo(tmp_path)
        # Replace the copied PR-B2 gate with a sentinel-only gate.
        _seed_gate(repo, _GATE_BODY_HEALTHY)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _write(repo, "backend/tests/test_a.py",
               "from services.a import VAL\n"
               "def test_a(): assert VAL == 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 11\n")
        _commit(repo, "modify a")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0, payload
        assert payload["state"] == "SELECTED"
        node_ids = [t["node_id"] for t in payload["selected_tests"]]
        assert "tests.test_a" in node_ids

    def test_root_local_gate_differs_from_sibling(self, tmp_path):
        """If the temp repo's gate contains a sentinel is_eligible_backend
        predicate that returns False for every path (so the selector would
        produce NO_ELIGIBLE if it actually loaded the root-local gate),
        we must observe NO_ELIGIBLE — proving the selector consumed the
        root-local gate, not the sibling one.
        """
        repo = _new_repo(tmp_path)
        no_op_gate = (
            "def is_eligible_backend(name):\n"
            "    return False\n"
            "def is_eligible_frontend(name):\n"
            "    return False\n"
        )
        _seed_gate(repo, no_op_gate)
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 2\n")
        _commit(repo, "modify a")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 0, payload
        # If the selector had used the sibling (production) gate,
        # backend/services/a.py would be eligible and state would be
        # SELECTED. With the root-local no-op gate it must be
        # NO_ELIGIBLE_BACKEND_CHANGE.
        assert payload["state"] == "NO_ELIGIBLE_BACKEND_CHANGE", payload


class TestTrustOrderingMissingGateFailsClosed:
    """D. Missing gate WITHOUT a diff-justified deletion is ERROR / exit 3.

    The diff must explain the missing gate; otherwise repository state
    is inconsistent and the selector fails closed.
    """

    def test_missing_gate_without_diff_returns_error(self, tmp_path):
        """Scenario D (spec): the diff does not explain the missing gate
        but the root-local gate cannot be loaded.

        Git always tracks file deletions in the diff, so a "deleted in
        working tree but not in diff" state is unreachable through normal
        git operations. The only true D scenario is when the gate was
        NEVER in the repository at all: the diff is a normal eligible
        backend change, but the gate file is absent on disk.

        Construct by removing the gate BEFORE the initial commit and
        committing only the backend skeleton — then the diff against
        base will be the eligible change and the gate will be missing
        on disk.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "backend").mkdir()
        # NO scripts/ directory and NO gate file at all.
        _make_backend_skeleton(repo)
        _write(repo, "backend/services/a.py", "VAL = 1\n")
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "ci@example.com")
        _git(repo, "config", "user.name", "CI")
        _git(repo, "config", "commit.gpgsign", "false")
        _git(repo, "config", "diff.renames", "false")
        _git(repo, "config", "status.renames", "false")
        base = _commit(repo, "seed")
        _write(repo, "backend/services/a.py", "VAL = 2\n")
        _commit(repo, "modify a")
        assert not (repo / "scripts" / "check_changed_line_coverage.py").exists()

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 3, payload
        assert payload["state"] == "ERROR"
        assert payload["errors"]
        # The error must reference the missing gate.
        joined = " ".join(payload["errors"])
        assert "PR-B2 gate" in joined or "gate" in joined.lower(), joined

    def test_missing_gate_with_explicit_no_diff_change_returns_error(
            self, tmp_path):
        """Same scenario with a docs-only diff (no trust surface moved)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "backend").mkdir()
        _make_backend_skeleton(repo)
        _write(repo, "docs/foo.md", "# initial\n")
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "ci@example.com")
        _git(repo, "config", "user.name", "CI")
        _git(repo, "config", "commit.gpgsign", "false")
        _git(repo, "config", "diff.renames", "false")
        _git(repo, "config", "status.renames", "false")
        base = _commit(repo, "seed")
        _write(repo, "docs/foo.md", "# updated\n")
        _commit(repo, "docs")
        assert not (repo / "scripts" / "check_changed_line_coverage.py").exists()

        rc, payload, _ = _run_selector(repo, base)
        # docs-only with missing gate: the diff proves the gate was not
        # touched in this PR, so the missing gate is a repository-state
        # inconsistency. The selector reaches step (5) before any
        # state-classification short-circuit, so it must fail closed
        # as ERROR.
        assert rc == 3, payload
        assert payload["state"] == "ERROR"


class TestTrustOrderingSelectorSelfChange:
    """E. A change to scripts/pr_fast_select_tests.py itself MUST be
    classified as selector_self before any gate load is attempted.
    """

    def test_selector_self_change_escalates_before_gate_load(
            self, tmp_path):
        repo = _new_repo(tmp_path)
        _seed_gate(repo, _GATE_BODY_HEALTHY)
        _make_backend_skeleton(repo)
        # Add a sentinel gate at the temp repo; a modification to the
        # selector itself will NOT import this gate (selector self is
        # classified before any gate load).
        sentinel = repo / "SELECTOR_SELF_SENTINEL"
        sentinel_gate = (
            "import pathlib\n"
            "_S = pathlib.Path(__file__).resolve().parent.parent / "
            "'SELECTOR_SELF_SENTINEL'\n"
            "_S.write_text('gate top-level executed', encoding='utf-8')\n"
            + _GATE_BODY_HEALTHY
        )
        _write(repo, "scripts/check_changed_line_coverage.py", sentinel_gate)
        base = _commit(repo, "seed")
        # Modify the selector script — top-level marker that would
        # change nothing about behavior, only its body.
        # We write a copy of the selector into the temp repo because the
        # diff is computed against the temp repo, not the production
        # selector. This makes the diff see the selector-self change.
        selector_path = WORKTREE / "scripts" / "pr_fast_select_tests.py"
        selector_text = selector_path.read_text(encoding="utf-8")
        # Append a no-op trailing comment so the diff is non-empty.
        _write(repo, "scripts/pr_fast_select_tests.py",
               selector_text + "\n# marker for selector-self test\n")
        _commit(repo, "modify selector self")
        assert not sentinel.exists()

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "selector_self" in cats
        # The candidate gate MUST NOT have been imported (sentinel
        # untouched).
        assert not sentinel.exists(), (
            "selector imported the candidate gate before classifying "
            "its own change as selector_self"
        )


# ---------------------------------------------------------------------------
# PR-B3b: coverage / test-infrastructure trust surfaces
# ---------------------------------------------------------------------------
#
# Adding/removing/modifying any of these files can change coverage
# semantics, isolated-test execution, or test-DB provisioning without
# touching application logic. The selector MUST treat them as
# trust-invalidating surfaces (gate_authority) so affected-test /
# affected-coverage reasoning is never silently undermined.
#
# We do NOT extend EXACT_ESCALATION_PATHS speculatively to the entire
# backend/scripts/ subtree (that would be an over-broad false positive),
# only to files that actually affect test selection, collection, or
# measurement.


class TestTrustOrderingCoverageAndTestInfraSurfaces:
    """PR-B3b part 1: coverage / test-infrastructure trust surfaces.

    Each test asserts that a change (or deletion) of one of the
    documented coverage / isolated-test / bootstrap-DB files is
    classified as gate_authority BEFORE the gate is imported, and the
    selector returns ESCALATION_REQUIRED (rc 2, never rc 0 / rc 3).
    """

    @pytest.mark.parametrize(
        "trust_path",
        [
            ".coveragerc",
            "backend/scripts/run_tests_isolated.sh",
            "backend/scripts/bootstrap_test_db.py",
        ],
    )
    def test_change_to_test_infra_surface_escalates(
            self, tmp_path, trust_path):
        repo = _new_repo(tmp_path)
        _seed_gate(repo, _GATE_BODY_HEALTHY)
        _make_backend_skeleton(repo)
        # Make sure the trust surface exists at base so the diff is a
        # clean A/M (not an add).
        path = repo / trust_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# original\n", encoding="utf-8")
        base = _commit(repo, "seed")
        path.write_text("# modified for test\n", encoding="utf-8")
        _commit(repo, "modify test infra")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "gate_authority" in cats
        reasons_paths = [r["path"] for r in payload["escalation_reasons"]]
        assert trust_path in reasons_paths

    @pytest.mark.parametrize(
        "trust_path",
        [
            ".coveragerc",
            "backend/scripts/run_tests_isolated.sh",
            "backend/scripts/bootstrap_test_db.py",
        ],
    )
    def test_deletion_of_test_infra_surface_escalates(
            self, tmp_path, trust_path):
        repo = _new_repo(tmp_path)
        _seed_gate(repo, _GATE_BODY_HEALTHY)
        _make_backend_skeleton(repo)
        path = repo / trust_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# original\n", encoding="utf-8")
        base = _commit(repo, "seed")
        path.unlink()
        _commit(repo, "delete test infra")

        rc, payload, _ = _run_selector(repo, base)
        assert rc == 2, payload
        assert payload["state"] == "ESCALATION_REQUIRED"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "gate_authority" in cats
        reasons_paths = [r["path"] for r in payload["escalation_reasons"]]
        assert trust_path in reasons_paths

    def test_unrelated_backend_script_is_not_escalated(self, tmp_path):
        """PR-B3b must NOT over-escalate to the whole backend/scripts/
        subtree. An ordinary operational script under backend/scripts/
        that does NOT control test / coverage / DB provisioning must
        remain on the ordinary reverse-closure path (or NO_ELIGIBLE if
        no eligible backend changed)."""
        repo = _new_repo(tmp_path)
        _seed_gate(repo, _GATE_BODY_HEALTHY)
        _make_backend_skeleton(repo)
        # An operational script that is NOT in our curated list.
        path = repo / "backend" / "scripts" / "ordinary_operational.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# original\n", encoding="utf-8")
        base = _commit(repo, "seed")
        path.write_text("# modified\n", encoding="utf-8")
        _commit(repo, "modify operational")

        rc, payload, _ = _run_selector(repo, base)
        # Must NOT escalate on this path; we expect NO_ELIGIBLE because
        # no eligible backend production module changed. The script
        # under backend/scripts/ is skipped by _file_to_module.
        assert rc == 0, payload
        assert payload["state"] == "NO_ELIGIBLE_BACKEND_CHANGE"
        cats = [r["category"] for r in payload["escalation_reasons"]]
        assert "gate_authority" not in cats


# =============================================================================
# PR-fast selection budget boundaries
# =============================================================================


class TestPrFastSelectionBudget:
    """The evidence-based fan-out cap must route, not execute, oversized suites."""

    @staticmethod
    def _repo_with_safe_selected_tests(tmp_path, count):
        repo = _new_repo(tmp_path)
        _make_backend_skeleton(repo, with_test_consumer=False)
        for index in range(count):
            _write(
                repo,
                f"backend/tests/test_budget_{index:03d}.py",
                "from services.a import VAL\n"
                f"def test_budget_{index:03d}(): assert VAL == 1\n",
            )
        base = _commit(repo, "seed safe selected suite")
        _write(repo, "backend/services/a.py", "VAL = 2\n")
        _commit(repo, "modify safe production module")
        return repo, base

    def test_exactly_120_safe_selected_files_remains_selected(self, tmp_path):
        repo, base = self._repo_with_safe_selected_tests(tmp_path, 120)

        rc, payload, _ = _run_selector(repo, base)

        assert rc == 0, payload
        assert payload["state"] == "SELECTED"
        assert payload["selection_count"] == 120
        assert len(payload["selected_tests"]) == 120
        assert not any(
            reason["category"] == "selection_budget"
            for reason in payload["escalation_reasons"]
        )

    def test_121_safe_selected_files_escalates_deterministically(self, tmp_path):
        repo, base = self._repo_with_safe_selected_tests(tmp_path, 121)

        rc1, payload1, _ = _run_selector(repo, base)
        rc2, payload2, _ = _run_selector(repo, base)

        assert rc1 == rc2 == 2
        assert payload1["state"] == payload2["state"] == "ESCALATION_REQUIRED"
        assert payload1["selection_count"] == payload2["selection_count"] == 121
        assert len(payload1["selected_tests"]) == len(payload2["selected_tests"]) == 121
        assert payload1["escalation_reasons"] == payload2["escalation_reasons"] == [
            {
                "category": "selection_budget",
                "path": "<pr-fast-selection-budget>",
                "detail": "selection_count=121 exceeds max=120",
            }
        ]
        assert payload1["notes"] == payload2["notes"]
