from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "complexity_ratchet",
    ROOT / "scripts/check_complexity_ratchet.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
evaluate = MODULE.evaluate


def _config(
    *,
    file_limit: int = 3,
    function_limit: int = 4,
    files: dict[str, int] | None = None,
    functions: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "version": 2,
        "default_max_lines": {"py": file_limit, "ts": file_limit, "tsx": file_limit},
        "legacy_max_lines": files or {},
        "default_max_python_function_lines": function_limit,
        "legacy_max_python_function_lines": functions or {},
    }


def _root(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "src").mkdir()


def test_complexity_ratchet_rejects_new_oversized_module(tmp_path: Path) -> None:
    _root(tmp_path)
    (tmp_path / "backend/large.py").write_text("# 1\n# 2\n# 3\n# 4\n", encoding="utf-8")
    assert evaluate(tmp_path, _config()) == [
        "backend/large.py: 4 lines > allowed 3"
    ]


def test_file_allowance_is_exact_and_removed_after_refactor(tmp_path: Path) -> None:
    _root(tmp_path)
    target = tmp_path / "backend/large.py"
    target.write_text("# 1\n# 2\n# 3\n# 4\n", encoding="utf-8")
    config = _config(files={"backend/large.py": 4})
    assert evaluate(tmp_path, config) == []

    target.write_text("# 1\n# 2\n# 3\n", encoding="utf-8")
    assert evaluate(tmp_path, config) == [
        "backend/large.py: legacy file allowance 4 is stale; remove it"
    ]

    target.unlink()
    assert evaluate(tmp_path, config) == [
        "backend/large.py: stale legacy file allowance"
    ]


def test_python_function_ratchet_rejects_new_growth(tmp_path: Path) -> None:
    _root(tmp_path)
    (tmp_path / "backend/functions.py").write_text(
        "def oversized():\n"
        "    first = 1\n"
        "    second = 2\n"
        "    third = 3\n"
        "    return first + second + third\n",
        encoding="utf-8",
    )
    assert evaluate(tmp_path, _config(file_limit=20, function_limit=4)) == [
        "backend/functions.py::oversized: 5 lines > allowed 4"
    ]


def test_python_function_allowance_is_exact_stale_and_deleted(tmp_path: Path) -> None:
    _root(tmp_path)
    target = tmp_path / "backend/functions.py"
    target.write_text(
        "class Service:\n"
        "    def large(self):\n"
        "        first = 1\n"
        "        second = 2\n"
        "        return first + second\n",
        encoding="utf-8",
    )
    key = "backend/functions.py::Service.large"
    config = _config(file_limit=20, function_limit=3, functions={key: 4})
    assert evaluate(tmp_path, config) == []

    target.write_text(
        "class Service:\n"
        "    def large(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    assert evaluate(tmp_path, config) == [
        f"{key}: legacy function allowance 4 is stale; remove it"
    ]

    target.unlink()
    assert evaluate(tmp_path, config) == [
        f"{key}: stale legacy Python function allowance"
    ]


def test_complexity_ratchet_ignores_dependency_and_build_trees(tmp_path: Path) -> None:
    _root(tmp_path)
    dependency = tmp_path / "backend/venv/site-packages/vendor.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("\n".join("x = 1" for _ in range(1000)), encoding="utf-8")
    assert evaluate(tmp_path, _config()) == []
