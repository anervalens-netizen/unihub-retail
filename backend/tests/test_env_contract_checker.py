"""Regression tests for ``scripts/check_env_contract.py``.

The contract checker used to recognize ``os.getenv("NAME")`` and
``os.environ.get("NAME")`` only when the first argument was a string
literal. Constant-backed lookups such as ``SOME_ENV = "NAME"`` followed by
``os.getenv(SOME_ENV)`` were silently missed, hiding latent runtime
variables from the contract.

These tests pin the hardened detection behaviour:
* direct literal arguments still resolve;
* same-module static string constants resolve for both ``os.getenv`` and
  ``os.environ.get``;
* dynamic expressions, function-local bindings, and unrelated function
  calls do not falsely resolve.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_env_contract.py"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location("check_env_contract", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "module_under_test.py"
    path.write_text(source, encoding="utf-8")
    return path


def test_direct_literal_os_getenv_is_detected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import os\n"
        "X = os.getenv('LITERAL_NAME')\n",
    )
    assert MODULE._python_env_names(path) == {"LITERAL_NAME"}


def test_direct_literal_os_environ_get_is_detected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import os\n"
        "X = os.environ.get('LITERAL_NAME')\n",
    )
    assert MODULE._python_env_names(path) == {"LITERAL_NAME"}


def test_constant_backed_os_getenv_is_detected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import os\n"
        "SOME_ENV = 'SOME_VARIABLE'\n"
        "value = os.getenv(SOME_ENV)\n",
    )
    assert MODULE._python_env_names(path) == {"SOME_VARIABLE"}


def test_constant_backed_os_environ_get_is_detected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import os\n"
        "SOME_ENV = 'SOME_VARIABLE'\n"
        "value = os.environ.get(SOME_ENV)\n",
    )
    assert MODULE._python_env_names(path) == {"SOME_VARIABLE"}


def test_constant_resolution_does_not_cross_modules(tmp_path: Path) -> None:
    """A constant defined in another module must not resolve."""

    other = tmp_path / "constants.py"
    other.write_text(
        "OTHER_ENV = 'OTHER_VARIABLE'\n",
        encoding="utf-8",
    )
    module_path = _write(
        tmp_path,
        "import os\n"
        "from constants import OTHER_ENV\n"
        "value = os.getenv(OTHER_ENV)\n",
    )
    assert MODULE._python_env_names(module_path) == set()


def test_function_local_constant_is_not_resolved(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import os\n"
        "def get_value():\n"
        "    INNER_ENV = 'INNER_VARIABLE'\n"
        "    return os.getenv(INNER_ENV)\n",
    )
    assert MODULE._python_env_names(path) == set()


def test_dynamic_expression_is_not_resolved(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import os\n"
        "BASE = 'BASE_VARIABLE'\n"
        "value = os.getenv(BASE + '_SUFFIX')\n",
    )
    assert MODULE._python_env_names(path) == set()


def test_unrelated_call_is_ignored(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "SOME_ENV = 'SOME_VARIABLE'\n"
        "result = print(SOME_ENV)\n",
    )
    assert MODULE._python_env_names(path) == set()


def test_non_string_constant_is_not_resolved(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import os\n"
        "NUMBER_ENV = 42\n"
        "value = os.getenv(NUMBER_ENV)\n",
    )
    assert MODULE._python_env_names(path) == set()


def test_known_latent_constant_sites_are_now_visible(tmp_path: Path) -> None:
    """All five known latent constant-backed env vars resolve to themselves."""

    sources = {
        "fiscal_rules.py": (
            "import os\n"
            "EFFECTIVE_DATED_VAT_ENV = 'EFFECTIVE_DATED_VAT_ENABLED'\n"
            "os.getenv(EFFECTIVE_DATED_VAT_ENV)\n"
        ),
        "metrics_network.py": (
            "import os\n"
            "PROMETHEUS_DOCKER_GATEWAY_ENV = 'PROMETHEUS_DOCKER_GATEWAY'\n"
            "PROMETHEUS_DOCKER_SUBNET_ENV = 'PROMETHEUS_DOCKER_SUBNET'\n"
            "os.getenv(PROMETHEUS_DOCKER_GATEWAY_ENV)\n"
            "os.getenv(PROMETHEUS_DOCKER_SUBNET_ENV)\n"
        ),
        "salary_import_approval.py": (
            "import os\n"
            "TRUSTED_REVIEWER_KEYS_ENV = 'SALARY_APPROVAL_REVIEWER_PUBLIC_KEYS_JSON'\n"
            "os.environ.get(TRUSTED_REVIEWER_KEYS_ENV)\n"
        ),
        "migration_runner.py": (
            "import os\n"
            "AUTHORITY_CUTOVER_BOOTSTRAP_ENV = 'UNIHUB_DB_AUTHORITY_CUTOVER_BOOTSTRAP'\n"
            "os.getenv(AUTHORITY_CUTOVER_BOOTSTRAP_ENV)\n"
        ),
    }
    expected = {
        "EFFECTIVE_DATED_VAT_ENABLED",
        "PROMETHEUS_DOCKER_GATEWAY",
        "PROMETHEUS_DOCKER_SUBNET",
        "SALARY_APPROVAL_REVIEWER_PUBLIC_KEYS_JSON",
        "UNIHUB_DB_AUTHORITY_CUTOVER_BOOTSTRAP",
    }
    found: set[str] = set()
    for filename, source in sources.items():
        path = tmp_path / filename
        path.write_text(source, encoding="utf-8")
        found.update(MODULE._python_env_names(path))
    assert found == expected
