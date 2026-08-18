"""Focused tests for the PR-B2 incremental complexity and coverage gates.

These tests pin the implementation-integrity invariants required by the
PR-B2 spec:

  * The changed-function complexity gate consumes the shared L1 metric,
    applies --no-renames rename safety, and fails closed on invalid
    inputs.

  * The changed-line coverage gate enforces active coverage lanes,
    fails closed when an eligible changed source is absent from the
    active coverage report, fails closed on malformed input, and
    proves pure rename safety for both backend and frontend.

Each test runs the gate in a real temporary git repository so diff
and rename classification come from real git, not mocks. Coverage
inputs are synthesized on disk from the same temporary repo state.
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
FN_SCRIPT = WORKTREE / "scripts" / "check_changed_function_complexity.py"
COV_SCRIPT = WORKTREE / "scripts" / "check_changed_line_coverage.py"
L1_PATH = WORKTREE / "scripts" / "_python_complexity.py"


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
    """Create a temp git repo mirroring the unihub-retail layout."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "backend").mkdir()
    (repo / "src").mkdir()
    (repo / "scripts").mkdir()
    shutil.copy(L1_PATH, repo / "scripts" / "_python_complexity.py")

    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "ci@example.com")
    _git(repo, "config", "user.name", "CI")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "diff.renames", "false")
    _git(repo, "config", "status.renames", "false")
    return repo


def _commit(repo, message):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def _run_gate(script, repo, *extra_args):
    """Invoke the gate via subprocess in the temp repo."""
    env = dict(os.environ)
    # The venv python (subprocess target) often runs without PATH set;
    # make sure /usr/bin and /bin are present so git is findable.
    base_path = env.get("PATH") or ""
    env["PATH"] = (
        "/usr/bin:/bin:" + str(PY.parent) + ":" + base_path
    )
    proc = subprocess.run(
        [str(PY), "-I", str(script), "--root", str(repo), *extra_args],
        cwd=WORKTREE,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return proc


def _hot_function_body(ifs):
    """Return source for a function with cp == 1 + ifs."""
    return (
        f"def f(x):\n"
        + "".join(f"    if x:\n        return {i}\n" for i in range(ifs))
        + "    return -1\n"
    )


def _write(repo, rel_path, content):
    """Write a file under repo and return its absolute path."""
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# =============================================================================
# 6A. CHANGED-FUNCTION TESTS
# =============================================================================


class TestChangedFunctionComplexity:
    """PR-B2 changed-function gate semantics."""

    # ----- (1) Shared metric parity ----------------------------------------

    def test_uses_l1_metric_not_duplicate_algorithm(self, tmp_path):
        """The gate scores via L1, not a duplicate inline AST walk."""
        repo = _new_repo(tmp_path)
        _write(
            repo,
            "backend/a.py",
            "def a(x):\n    return 1\n",
        )
        _commit(repo, "seed")
        _write(
            repo,
            "backend/a.py",
            _hot_function_body(10),
        )
        _commit(repo, "modify")
        base = _git(repo, "rev-parse", "HEAD~1").strip()

        # L1 present -> gate works (10 ifs -> cp 11, <= maximum 20).
        ok = _run_gate(FN_SCRIPT, repo, "--base", base)
        assert ok.returncode == 0, ok.stdout + ok.stderr

        # The gate must not contain its own AST scoring algorithm. The
        # negative-shape checks prove the gate is NOT re-implementing the
        # metric and is consuming L1 instead.
        text = FN_SCRIPT.read_text(encoding="utf-8")
        assert "def complexity(" not in text, (
            "check_changed_function_complexity.py defines a duplicate "
            "complexity() function; it must call l1.score() instead."
        )
        assert "ast.walk" not in text, (
            "check_changed_function_complexity.py walks the AST itself; "
            "it must delegate to l1.score() instead."
        )
        assert "l1.function_metrics" in text, (
            "check_changed_function_complexity.py must consume the shared "
            "L1 module's function_metrics() API."
        )
        assert "spec_from_file_location" in text, (
            "check_changed_function_complexity.py must load L1 via "
            "importlib.util.spec_from_file_location (trusted sibling)."
        )
        assert L1_PATH.is_file(), "L1 module must exist for the gate"

    # ----- (2) New function <= maximum -> PASS ------------------------------

    def test_new_function_below_maximum_passes(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed-empty")
        _write(
            repo,
            "backend/new_small.py",
            _hot_function_body(5),  # cp 6, well below default max 20
        )
        _commit(repo, "add small")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        ok = _run_gate(FN_SCRIPT, repo, "--base", base)
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert "passed" in ok.stdout.lower()

    # ----- (3) New function > maximum -> FAIL ------------------------------

    def test_new_function_above_maximum_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed-empty")
        # cp = 1 + 25 ifs = 26, > maximum 20
        _write(repo, "backend/new_hot.py", _hot_function_body(25))
        _commit(repo, "add hot")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = _run_gate(FN_SCRIPT, repo, "--base", base, "--maximum", "20")
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "new_hot" in bad.stdout
        assert "maximum" in bad.stdout

    # ----- (4) Existing hotspot strictly improved -> PASS ------------------

    def test_existing_hotspot_strictly_improves_passes(self, tmp_path):
        repo = _new_repo(tmp_path)
        # 22 ifs -> cp 23 (> maximum 20, but this is the baseline).
        _write(repo, "backend/existing.py", _hot_function_body(22))
        _commit(repo, "baseline hotspot")
        # Improve to 18 ifs -> cp 19 (<= 20).
        _write(repo, "backend/existing.py", _hot_function_body(18))
        _commit(repo, "improve hotspot")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        ok = _run_gate(FN_SCRIPT, repo, "--base", base, "--maximum", "20")
        assert ok.returncode == 0, ok.stdout + ok.stderr

    # ----- (5) Existing hotspot equal or worse -> FAIL ---------------------

    def test_existing_hotspot_unchanged_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/existing.py", _hot_function_body(22))
        _commit(repo, "baseline hotspot")
        # Touch a line INSIDE the function body without changing its
        # control-flow complexity (e.g., insert a pass after the def
        # line). The function now appears in the diff but its complexity
        # is unchanged.
        body = _hot_function_body(22)
        modified = body.replace("def f(x):", "def f(x):" + chr(10) + "    pass", 1)
        _write(repo, "backend/existing.py", modified)
        _commit(repo, "no improvement")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = _run_gate(FN_SCRIPT, repo, "--base", base, "--maximum", "20")
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "existing" in bad.stdout

    def test_existing_hotspot_worsens_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/existing.py", _hot_function_body(22))
        _commit(repo, "baseline")
        # Worsen to 30 ifs -> cp 31.
        _write(repo, "backend/existing.py", _hot_function_body(30))
        _commit(repo, "worsen")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = _run_gate(FN_SCRIPT, repo, "--base", base, "--maximum", "20")
        assert bad.returncode == 1, bad.stdout + bad.stderr

    # ----- (6) Pure R100 rename of >maximum -> MUST NOT disappear ----------

    def test_pure_r100_rename_of_hotspot_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _git(repo, "config", "diff.renames", "true")
        _git(repo, "config", "status.renames", "true")
        _write(repo, "backend/old_name.py", _hot_function_body(22))
        _commit(repo, "baseline")
        # Pure rename: same content, new path.
        (repo / "backend/old_name.py").rename(repo / "backend/new_name.py")
        _commit(repo, "rename")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = _run_gate(FN_SCRIPT, repo, "--base", base, "--maximum", "20")
        assert bad.returncode == 1, bad.stdout + bad.stderr
        # Destination (new_name.py) must be evaluated.
        assert "new_name.py" in bad.stdout

    # ----- (7) Pure rename of small <=maximum -> PASS ----------------------

    def test_pure_r100_rename_of_small_function_passes(self, tmp_path):
        repo = _new_repo(tmp_path)
        _git(repo, "config", "diff.renames", "true")
        _git(repo, "config", "status.renames", "true")
        _write(repo, "backend/small_old.py", _hot_function_body(3))
        _commit(repo, "baseline")
        (repo / "backend/small_old.py").rename(repo / "backend/small_new.py")
        _commit(repo, "rename")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        ok = _run_gate(FN_SCRIPT, repo, "--base", base)
        assert ok.returncode == 0, ok.stdout + ok.stderr

    # ----- (8) Rename + harmless edit of >maximum -> MUST NOT escape ------

    def test_rename_plus_harmless_edit_of_hotspot_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _git(repo, "config", "diff.renames", "true")
        _git(repo, "config", "status.renames", "true")
        _write(repo, "backend/hot_old.py", _hot_function_body(22))
        _commit(repo, "baseline")
        # Rename + add a comment that touches the function body.
        new_text = "# new comment\n" + _hot_function_body(22)
        (repo / "backend/hot_old.py").write_text(new_text, encoding="utf-8")
        (repo / "backend/hot_old.py").rename(repo / "backend/hot_new.py")
        _commit(repo, "rename + comment")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = _run_gate(FN_SCRIPT, repo, "--base", base, "--maximum", "20")
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "hot_new.py" in bad.stdout

    # ----- (9) Rename/move across backend directories -> MUST NOT escape ---

    def test_rename_across_backend_directories_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _git(repo, "config", "diff.renames", "true")
        _git(repo, "config", "status.renames", "true")
        (repo / "backend/services").mkdir()
        _write(
            repo,
            "backend/services/hot_old.py",
            _hot_function_body(22),
        )
        _commit(repo, "baseline")
        # Force the rename path: backend/services/hot_old.py -> backend/root_hot.py.
        target = repo / "backend" / "root_hot.py"
        if target.exists():
            target.unlink()
        (repo / "backend" / "services" / "hot_old.py").rename(target)
        _commit(repo, "cross-dir rename")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = _run_gate(FN_SCRIPT, repo, "--base", base, "--maximum", "20")
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "root_hot.py" in bad.stdout

    # ----- (10) Invalid base -> FAIL ---------------------------------------

    def test_invalid_base_fails_closed(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/a.py", "def a():\n    return 1\n")
        _commit(repo, "seed")
        bad = _run_gate(
            FN_SCRIPT, repo, "--base", "definitely_not_a_real_commit_xyz",
        )
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "invalid base" in bad.stdout.lower()


# =============================================================================
# 6B. CHANGED-LINE COVERAGE TESTS
# =============================================================================


def _make_python_coverage(repo, files_with_lines, missing=None):
    """Build a coverage.py JSON file mapping each repo-relative path to
    a set of executed line numbers. ``missing`` is an optional dict of
    {rel: [missing_line_numbers]} so tests can model partially-covered
    files."""
    payload = {"files": {}}
    miss = missing or {}
    for rel, lines in files_with_lines.items():
        payload["files"][rel] = {
            "executed_lines": sorted(lines),
            "missing_lines": sorted(miss.get(rel, [])),
        }
    path = repo / "_coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_lcov(repo, files_with_lines):
    """Build an LCOV file mapping each repo-relative path to line numbers."""
    out = ["TN:"]
    for rel, lines in files_with_lines.items():
        out.append("SF:" + str(repo / rel))
        for line in sorted(lines):
            out.append(f"DA:{line},1")
        out.append("end_of_record")
    path = repo / "_coverage.lcov"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


class TestChangedLineCoverage:
    """PR-B2 changed-line coverage gate semantics."""

    # ----- (1) Backend sufficient coverage -> PASS --------------------------

    def test_backend_sufficient_coverage_passes(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/mod.py", "def f():\n    return 1\n")
        _commit(repo, "seed")
        _write(
            repo,
            "backend/mod.py",
            "def f():\n    if True:\n        return 1\n    return 2\n",
        )
        _commit(repo, "add if")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        cov = _make_python_coverage(repo, {"backend/mod.py": {3, 5}})
        ok = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--backend-json", str(cov),
        )
        assert ok.returncode == 0, ok.stdout + ok.stderr

    # ----- (2) Backend insufficient coverage -> FAIL -----------------------

    def test_backend_insufficient_coverage_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/mod.py", "def f():\n    return 1\n")
        _commit(repo, "seed")
        _write(
            repo,
            "backend/mod.py",
            "def f():\n    if True:\n        return 1\n    return 2\n",
        )
        _commit(repo, "add if")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        # Line 3 covered (inner return), line 4 NOT covered. Changed
        # lines are 2/3/4; intersection is {3, 4}; half-covered -> fails
        # at minimum 100%.
        cov = _make_python_coverage(
            repo,
            {"backend/mod.py": {3}},
            missing={"backend/mod.py": [4]},
        )
        bad = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--backend-json", str(cov),
            "--minimum", "100.0",
        )
        assert bad.returncode == 1, bad.stdout + bad.stderr

    # ----- (3) Backend file absent from JSON -> FAIL ------------------------

    def test_backend_file_absent_from_coverage_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed-empty")
        _write(repo, "backend/mod.py", "def f():\n    return 1\n")
        _commit(repo, "add backend file")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        # Coverage JSON exists but does NOT mention backend/mod.py.
        cov = _make_python_coverage(repo, {})
        bad = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--backend-json", str(cov),
        )
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "absent" in bad.stdout.lower()

    # ----- (4) Malformed backend JSON / record -> FAIL ----------------------

    def test_malformed_backend_json_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/mod.py", "def f():\n    return 1\n")
        _commit(repo, "seed")
        _write(repo, "backend/mod.py", "def f():\n    if x:\n        return 1\n    return 2\n")
        _commit(repo, "change")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = (repo / "_bad.json")
        bad.write_text("not json at all {", encoding="utf-8")
        proc = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--backend-json", str(bad),
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "parse" in proc.stdout.lower() or "json" in proc.stdout.lower()

    def test_malformed_backend_record_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/mod.py", "def f():\n    return 1\n")
        _commit(repo, "seed")
        _write(repo, "backend/mod.py", "def f():\n    if x:\n        return 1\n    return 2\n")
        _commit(repo, "change")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = repo / "_bad.json"
        bad.write_text(json.dumps({"files": {"backend/mod.py": "not-a-dict"}}), encoding="utf-8")
        proc = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--backend-json", str(bad),
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "record" in proc.stdout.lower() or "object" in proc.stdout.lower()

    # ----- (5) Comments-only changed lines in valid record -> PASS --------

    def test_comments_only_change_with_valid_record_passes(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(
            repo,
            "backend/mod.py",
            "def f():\n    return 1\n",
        )
        _commit(repo, "seed")
        # Add a comment-only line: line 2 in the new file is a comment,
        # not instrumented.
        _write(
            repo,
            "backend/mod.py",
            "def f():\n    # explanatory comment\n    return 1\n",
        )
        _commit(repo, "comment-only change")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        cov = _make_python_coverage(repo, {"backend/mod.py": {1, 3}})
        ok = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--backend-json", str(cov),
        )
        assert ok.returncode == 0, ok.stdout + ok.stderr

    # ----- (6) Frontend sufficient LCOV -> PASS ----------------------------

    def test_frontend_sufficient_lcov_passes(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "src/app.ts", "export const x = 1;\n")
        _commit(repo, "seed")
        _write(repo, "src/app.ts", "export const x = 1;\nexport const y = 2;\n")
        _commit(repo, "add line")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        cov = _make_lcov(repo, {"src/app.ts": {1, 2}})
        ok = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--frontend-lcov", str(cov),
        )
        assert ok.returncode == 0, ok.stdout + ok.stderr

    # ----- (7) Frontend file absent from LCOV -> FAIL ----------------------

    def test_frontend_file_absent_from_lcov_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed-empty")
        _write(repo, "src/app.ts", "export const x = 1;\n")
        _commit(repo, "add frontend")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        cov = _make_lcov(repo, {})
        bad = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--frontend-lcov", str(cov),
        )
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "absent" in bad.stdout.lower()

    # ----- (8) Malformed LCOV DA / record -> FAIL --------------------------

    def test_malformed_lcov_da_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "src/app.ts", "export const x = 1;\n")
        _commit(repo, "seed")
        _write(repo, "src/app.ts", "export const x = 1;\nexport const y = 2;\n")
        _commit(repo, "add line")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = repo / "_bad.lcov"
        bad.write_text(
            "TN:\nSF:" + str(repo / "src/app.ts") + "\nDA:abc,1\nend_of_record\n",
            encoding="utf-8",
        )
        proc = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--frontend-lcov", str(bad),
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "malformed" in proc.stdout.lower() or "da" in proc.stdout.lower()

    def test_malformed_lcov_unterminated_record_fails(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "src/app.ts", "export const x = 1;\n")
        _commit(repo, "seed")
        _write(repo, "src/app.ts", "export const x = 1;\nexport const y = 2;\n")
        _commit(repo, "add line")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        bad = repo / "_bad.lcov"
        # SF present but NO end_of_record -> structurally broken.
        bad.write_text(
            "TN:\nSF:" + str(repo / "src/app.ts") + "\nDA:1,1\n",
            encoding="utf-8",
        )
        proc = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--frontend-lcov", str(bad),
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "unterminated" in proc.stdout.lower()

    # ----- (9) comments / non-instrumented-only change in valid file -> PASS

    def test_frontend_comments_only_change_passes(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "src/app.ts", "export const x = 1;\n")
        _commit(repo, "seed")
        # Add a comment line; no new instrumented line.
        _write(
            repo,
            "src/app.ts",
            "// explanatory\nexport const x = 1;\n",
        )
        _commit(repo, "comment-only")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        cov = _make_lcov(repo, {"src/app.ts": {2}})
        ok = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--frontend-lcov", str(cov),
        )
        assert ok.returncode == 0, ok.stdout + ok.stderr

    # ----- (10) .d.ts change is not treated as executable source -----------

    def test_dts_change_is_not_treated_as_executable(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "src/types.d.ts", "export const x: number;\n")
        _commit(repo, "seed")
        _write(
            repo,
            "src/types.d.ts",
            "export const x: number;\nexport const y: number;\n",
        )
        _commit(repo, "add .d.ts")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        # No coverage supplied for the .d.ts file; the gate should treat
        # it as ineligible and PASS cleanly.
        cov = _make_lcov(repo, {})
        ok = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--frontend-lcov", str(cov),
        )
        assert ok.returncode == 0, ok.stdout + ok.stderr

    # ----- (11) Backend change with only frontend-lcov -> not a failure ---

    def test_backend_change_with_only_frontend_lcov_isolates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed-empty")
        _write(repo, "backend/mod.py", "def f():\n    return 1\n")
        _commit(repo, "add backend")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        # Frontend coverage exists but backend file is changed.
        cov = _make_lcov(repo, {})
        ok = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--frontend-lcov", str(cov),
        )
        assert ok.returncode == 0, ok.stdout + ok.stderr

    # ----- (12) Frontend change with only backend-json -> not a failure ---

    def test_frontend_change_with_only_backend_json_isolates(self, tmp_path):
        repo = _new_repo(tmp_path)
        _commit(repo, "seed-empty")
        _write(repo, "src/app.ts", "export const x = 1;\n")
        _commit(repo, "add frontend")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        cov = _make_python_coverage(repo, {})
        ok = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--backend-json", str(cov),
        )
        assert ok.returncode == 0, ok.stdout + ok.stderr

    # ----- (13) Neither backend-json nor frontend-lcov -> FAIL clearly ----

    def test_neither_coverage_input_fails_clearly(self, tmp_path):
        repo = _new_repo(tmp_path)
        _write(repo, "backend/mod.py", "def f():\n    return 1\n")
        _commit(repo, "seed")
        bad = _run_gate(COV_SCRIPT, repo, "--base", "HEAD")
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "must supply" in bad.stdout.lower() or "backend-json" in bad.stdout.lower()

    # ----- (14) Pure R100 backend rename: destination must not disappear -

    def test_pure_r100_backend_rename_destination_evaluated(self, tmp_path):
        repo = _new_repo(tmp_path)
        _git(repo, "config", "diff.renames", "true")
        _git(repo, "config", "status.renames", "true")
        _write(repo, "backend/old_mod.py", "def f():\n    return 1\n")
        _commit(repo, "seed")
        (repo / "backend/old_mod.py").rename(repo / "backend/new_mod.py")
        _commit(repo, "rename")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        # Destination absent from coverage -> MUST fail closed.
        cov = _make_python_coverage(repo, {})
        bad = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--backend-json", str(cov),
        )
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "new_mod.py" in bad.stdout

    # ----- (15) Pure R100 frontend rename: destination must not disappear -

    def test_pure_r100_frontend_rename_destination_evaluated(self, tmp_path):
        repo = _new_repo(tmp_path)
        _git(repo, "config", "diff.renames", "true")
        _git(repo, "config", "status.renames", "true")
        _write(repo, "src/old_app.ts", "export const x = 1;\n")
        _commit(repo, "seed")
        (repo / "src/old_app.ts").rename(repo / "src/new_app.ts")
        _commit(repo, "rename")
        base = _git(repo, "rev-parse", "HEAD~1").strip()
        cov = _make_lcov(repo, {})
        bad = _run_gate(
            COV_SCRIPT, repo, "--base", base, "--frontend-lcov", str(cov),
        )
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert "new_app.ts" in bad.stdout
