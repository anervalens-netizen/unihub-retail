from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from types import ModuleType
from typing import Any
import base64

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = ROOT / "scripts/check_release_a_candidate.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_candidate_checker", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_release_a_schema_gate_isolated(
    checker: str,
    schema_gate: str,
    structural_gate: str,
    scale_gate: str,
) -> None:
    assert 'git("status", "--porcelain")' in checker
    assert "--untracked-files=no" not in checker
    assert 'os.environ.pop(_startup_variable, None)' in checker
    assert "status --porcelain" in schema_gate
    assert "PYTHONNOUSERSITE=1" in schema_gate
    assert "PYTHONSAFEPATH=1" in schema_gate
    assert "PYTHONDONTWRITEBYTECODE=1" in schema_gate
    assert '"$PYTHON_BASE" -B -I -S "$ROOT_DIR/scripts/check_release_a_candidate.py"' in schema_gate
    assert "unset MYPYPATH MYPY_CONFIG_FILE" in schema_gate
    for source in (schema_gate, structural_gate, scale_gate):
        assert "postgres@sha256:" in source
        assert "--pull=never" in source
        assert 'PYTHON_BASE="/usr/bin/python3.12"' in source
        assert "PYTHON_BASE_SHA256=" in source
    assert "valkey/valkey@sha256:" in schema_gate
    assert "UNIHUB_SCALE_PYTHON" not in scale_gate
    assert "UNIHUB_BACKEND_VENV" not in structural_gate


def _assert_local_python_gate_isolated(local_gate: str) -> None:
    assert "EXPECTED_NODE_SHA256" in local_gate
    assert "EXPECTED_NPM_CLI_SHA256" in local_gate
    assert 'PYTHON_BASE="/usr/bin/python3.12"' in local_gate
    assert "EXPECTED_PYTHON_SHA256" in local_gate
    assert "'$PYTHON' -B -I -m mypy" in local_gate
    assert "python-cache-preflight" in local_gate
    assert "python-dependencies-final" in local_gate
    assert 'export PYTHONDONTWRITEBYTECODE=1' in local_gate
    assert 'PATH="$(dirname "$NODE"):' in local_gate
    assert "    export PATH" in local_gate


def _assert_outbox_gate_isolated(outbox_gate: str) -> None:
    assert "UNIHUB_BACKEND_VENV" not in outbox_gate
    assert 'PYTHON_BASE = Path("/usr/bin/python3.12")' in outbox_gate
    assert 'not sys.flags.isolated' in outbox_gate
    assert 'os.environ.pop(_startup_variable, None)' in outbox_gate
    assert '[str(PYTHON), "-B", "-I", str(DRIVER)' in outbox_gate


def _assert_e2e_and_deploy_python_isolated(real_e2e: str, deployed: str) -> None:
    assert 'PYTHON_BASE="/usr/bin/python3.12"' in real_e2e
    assert "export PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1" in real_e2e
    assert '"${PYTHON}" -I -c' in real_e2e
    assert "BACKEND_PYTHON=(" in real_e2e
    assert 'node_modules/.bin/playwright' not in real_e2e
    assert '"${NODE}" "${PLAYWRIGHT_CLI}"' in real_e2e
    assert "NODE_OPTIONS NODE_PATH" in real_e2e
    assert 'PYTHON_BASE="/usr/bin/python3.12"' in deployed
    assert "PYTHON_BASE_SHA256" in deployed
    assert "export PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1" in deployed


def test_release_a_tooling_requires_clean_untracked_scope() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    schema_gate = (ROOT / "scripts/run_release_a_schema_gate.sh").read_text(
        encoding="utf-8"
    )
    structural_gate = (ROOT / "scripts/run_structural_characterization.sh").read_text(
        encoding="utf-8"
    )
    scale_gate = (ROOT / "scripts/run_retail_scale_gate.sh").read_text(
        encoding="utf-8"
    )
    local_gate = (ROOT / "scripts/run_local_quality_gate.sh").read_text(
        encoding="utf-8"
    )
    outbox_gate = (ROOT / "scripts/run_outbox_slo_gate.py").read_text(
        encoding="utf-8"
    )
    real_e2e = (ROOT / "scripts/run_real_e2e.sh").read_text(encoding="utf-8")
    deployed = (ROOT / "scripts/verify_deployed_release.sh").read_text(
        encoding="utf-8"
    )
    _assert_release_a_schema_gate_isolated(
        checker, schema_gate, structural_gate, scale_gate
    )
    _assert_local_python_gate_isolated(local_gate)
    _assert_outbox_gate_isolated(outbox_gate)
    _assert_e2e_and_deploy_python_isolated(real_e2e, deployed)


def test_outbox_authority_rejects_forged_samples_and_monitors_claimers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = ROOT / "scripts/run_outbox_slo_gate.py"
    spec = importlib.util.spec_from_file_location("outbox_slo_gate", path)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )
    gate.self_test()
    driver = (ROOT / "backend/scripts/run_outbox_slo_workload.py").read_text(
        encoding="utf-8"
    )
    engine = (ROOT / "backend/scripts/outbox_slo_workload_engine.py").read_text(
        encoding="utf-8"
    )
    assert "from scripts.outbox_slo_workload_engine import OutboxWorkload" in driver
    assert "class OutboxWorkload:" in engine
    assert "def ensure_claimers_healthy(self)" in engine
    assert engine.count("self.ensure_claimers_healthy()") >= 4
    assert gate.ENGINE == ROOT / "backend/scripts/outbox_slo_workload_engine.py"
    assert "                    ENGINE," in path.read_text(encoding="utf-8")


def test_outbox_workload_split_is_bounded_and_gate_binds_engine() -> None:
    gate_source = (ROOT / "scripts/run_outbox_slo_gate.py").read_text(
        encoding="utf-8"
    )
    driver_path = ROOT / "backend/scripts/run_outbox_slo_workload.py"
    engine_path = ROOT / "backend/scripts/outbox_slo_workload_engine.py"
    for path in (driver_path, engine_path):
        source = path.read_text(encoding="utf-8")
        tree = compile(source, str(path), "exec", ast.PyCF_ONLY_AST)
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert len(source.splitlines()) <= 600
        assert max((node.end_lineno or node.lineno) - node.lineno + 1 for node in functions) <= 120
    assert 'ENGINE = ROOT / "backend/scripts/outbox_slo_workload_engine.py"' in gate_source


def _scan_protected_outbox_vocabulary(
    reserved_emitters: set[str], protected_event_types: set[str]
) -> tuple[dict[str, set[str]], set[str], set[str]]:
    found: dict[str, set[str]] = {name: set() for name in reserved_emitters}
    event_type_paths: set[str] = set()
    generic_insert_paths: set[str] = set()
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\0")
    for relative in tracked:
        if not relative or relative.startswith("docs/"):
            continue
        try:
            source = (ROOT / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name in reserved_emitters:
            if name in source:
                found[name].add(relative)
        if any(event_type in source for event_type in protected_event_types):
            event_type_paths.add(relative)
        if (
            relative.startswith("backend/")
            and not relative.startswith(("backend/scripts/", "backend/tests/"))
            and "INSERT INTO retail_outbox_events" in source
        ):
            generic_insert_paths.add(relative)
    return found, event_type_paths, generic_insert_paths


def test_protected_outbox_vocabulary_has_no_release_b_application_producer() -> None:
    reserved_emitters = {
        "emit_retail_pnl_generation_promoted",
        "emit_retail_salary_import_completed",
        "emit_retail_planning_forecast_promoted",
        "emit_retail_grile_manifest_approved",
    }
    allowed = {
        "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
        "backend/scripts/run_outbox_slo_workload.py",
        "backend/tests/test_release_a_schema_069.py",
        "backend/tests/test_release_contract_tooling_security.py",
        "scripts/run_outbox_slo_gate.py",
    }
    protected_event_types = {
        "retail.pnl_generation_promoted.v1",
        "retail.salary_import_completed.v1",
        "retail.planning_forecast_promoted.v1",
        "retail.grile_manifest_approved.v1",
    }
    found, event_type_paths, generic_insert_paths = _scan_protected_outbox_vocabulary(
        reserved_emitters, protected_event_types
    )
    assert found == {name: allowed for name in reserved_emitters}
    allowed_event_type_paths = {
        "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
        "backend/scripts/run_outbox_slo_workload.py",
        "backend/tests/test_release_contract_tooling_security.py",
        "scripts/run_outbox_slo_gate.py",
        "scripts/verify_deployed_release.sh",
    }
    if (ROOT / "backend/services/outbox_worker.py").is_file():
        allowed_event_type_paths.add("backend/services/outbox_worker.py")
    assert event_type_paths == allowed_event_type_paths
    assert generic_insert_paths == set()
    gate_source = (ROOT / "scripts/run_outbox_slo_gate.py").read_text(
        encoding="utf-8"
    )
    assert '"protected_sql_fixture_emitters"' in gate_source
    assert '"non_sales_producers"' not in gate_source


def test_release_a_checker_never_runs_mypy_after_scope_failure() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    assert "if scope_ready:\n        _command, mypy = run_direct_mypy()" in checker
    assert '"reason": "scope_precondition_failed"' in checker
    assert '"/usr/bin/python3.12",\n        "-B",\n        "-I",\n        "-S"' in checker
    assert "runpy.run_module('mypy',run_name='__main__')" in checker
    assert '"venv/bin/mypy"' not in checker


def test_artifact_policy_can_reconstruct_mypy_command_without_an_ignored_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    monkeypatch.setattr(
        checker,
        "verified_backend_python",
        lambda: (_ for _ in ()).throw(AssertionError("ignored venv must not be read")),
    )
    command = checker.expected_direct_mypy_command()
    assert command[3] == "/usr/bin/python3.12"
    assert command[4:7] == ["-B", "-I", "-S"]
    assert "venv/lib/python3.12/site-packages" in command[8]
    assert str(checker.ROOT) not in command[8]
    source = (ROOT / "scripts/check_release_a_candidate.py").read_text(
        encoding="utf-8"
    )
    assert '"PYTHONDONTWRITEBYTECODE": "1"' in source
    assert 'evidence["python_environment_post_mypy"]' in source
    assert "direct mypy changed the verified Python environment" in source
    assert "python_environment_post_mypy == python_environment" in source


def test_direct_mypy_subprocess_cannot_write_bytecode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    observed: dict[str, Any] = {}

    monkeypatch.setattr(
        checker,
        "verified_backend_python",
        lambda: Path("/usr/bin/python3.12"),
    )

    def run_stub(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["args"] = args
        observed["environment"] = kwargs["env"]
        return subprocess.CompletedProcess(args, 0, "Success: no issues found", "")

    monkeypatch.setattr(checker.subprocess, "run", run_stub)
    command, result = checker.run_direct_mypy()
    assert result.returncode == 0
    assert command[1:4] == ["-B", "-I", "-S"]
    assert observed["args"][1:4] == ["-B", "-I", "-S"]
    assert observed["environment"]["PYTHONDONTWRITEBYTECODE"] == "1"


def _assert_python_record_canonicalization(
    checker: ModuleType, environment: dict[str, Any]
) -> None:
    assert environment["site_packages_sha256"] == checker.PYTHON_SITE_PACKAGES_SHA256
    compiled_record = (
        b"package/module.py,sha256=source,1\n"
        b"package/__pycache__/module.cpython-312.pyc,,\n"
        b"../../../bin/__pycache__/runxlrd.cpython-312.pyc,,\n"
        b"../../../bin/package,sha256=path-bound,99\n"
    )
    assert checker.canonical_python_record_bytes(compiled_record) == (
        b"package/module.py,sha256=source,1\n"
        b"../../../bin/package,<venv-script>,<size>\n"
    )
    malicious_record = b"../../outside.pyc,,\n"
    assert checker.canonical_python_record_bytes(malicious_record) == malicious_record
    nested_record = b"package/__pycache__/nested/module.cpython-312.pyc,,\n"
    assert checker.canonical_python_record_bytes(nested_record) == nested_record
    assert (
        environment["system_sitecustomize_sha256"]
        == checker.PYTHON_SYSTEM_SITECUSTOMIZE_SHA256
    )
    assert "backend/scripts/run_tests_isolated.sh" in checker.EXPECTED_RELEASE_A_AUTHORITIES


def _assert_python_runtime_supply_contract(
    validator: str, workflow: str, verifier: str
) -> None:
    property_name = "unihub:python-runtime:site-packages-tree-sha256:v1"
    assert property_name in validator
    assert 'metadata.setdefault("properties", [])' in validator
    assert property_name in verifier
    assert '--runtime-venv "$runtime_venv"' in workflow
    assert "--clean-runtime-pyc" in workflow
    assert "--no-compile" in workflow
    assert "--verify-python-environment" in workflow


def _assert_secret_scan_contract(secret_step: str) -> None:
    exact_scan = secret_step[secret_step.index("detect_secrets scan") :]
    for digest_authority in (
        "backend/scripts/run_tests_isolated.sh",
        "ops/deploy-retail-artifact.sh",
    ):
        assert f"':(exclude){digest_authority}'" in secret_step
        assert secret_step.count(digest_authority) == 2
        assert digest_authority in exact_scan
    assert "--disable-plugin HexHighEntropyString" in secret_step
    assert "--disable-plugin Base64HighEntropyString" in secret_step
    assert secret_step.count("--disable-plugin") == 2


def _assert_local_python_cache_contract(local_gate: str) -> None:
    assert "is_canonical_generated_pyc" in local_gate
    assert 'path.parts[:5] == ("..", "..", "..", "bin", "__pycache__")' in local_gate
    assert 'for path in venv_root.rglob("*.pyc")' in local_gate
    assert '"$ROOT/backend/venv" "$output"' in local_gate


def _assert_python_install_order(workflow: str) -> None:
    pip_install = workflow.index("--no-compile --require-hashes -r requirements-dev.lock")
    cache_clean = workflow.index("--internal-python-cache-clean", pip_install)
    environment_check = workflow.index("--verify-python-environment", cache_clean)
    assert pip_install < cache_clean < environment_check
    backend_tests = workflow.index("- name: Backend tests", environment_check)
    backend_cache_clean = workflow.index("--internal-python-cache-clean", backend_tests)
    backend_test_runner = workflow.index("scripts/run_tests_isolated.sh", backend_cache_clean)
    assert environment_check < backend_tests < backend_cache_clean < backend_test_runner
    assert workflow.count("import sys; sys.path.insert(0, '.')") >= 2


def _assert_migration_manifest_loads() -> None:
    completed = subprocess.run(
        [
            str(ROOT / "backend/venv/bin/python"),
            "-B",
            "-I",
            "-c",
            (
                "import sys; sys.path.insert(0, '.'); "
                "from db.migration_runner import load_migration_manifest, "
                "verify_migration_files; "
                "verify_migration_files(load_migration_manifest())"
            ),
        ],
        cwd=ROOT / "backend",
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_release_a_python_environment_and_runtime_tree_are_cryptographically_bound() -> None:
    checker = _load_checker()
    environment = checker.verify_backend_python_environment()
    _assert_python_record_canonicalization(checker, environment)
    validator = (ROOT / "scripts/validate_release_sbom.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow_secret_step = workflow[
        workflow.index("- name: Tracked secret regression scan") : workflow.index(
            "- name: Bandit waiver governance"
        )
    ]
    verifier = (ROOT / "scripts/verify_deployed_release.sh").read_text(encoding="utf-8")
    _assert_python_runtime_supply_contract(validator, workflow, verifier)
    local_gate = (ROOT / "scripts/run_local_quality_gate.sh").read_text(
        encoding="utf-8"
    )
    local_secret_step = local_gate[
        local_gate.index("internal_secret_scan()") : local_gate.index(
            "internal_python_lock()"
        )
    ]
    for secret_step in (workflow_secret_step, local_secret_step):
        _assert_secret_scan_contract(secret_step)
    _assert_local_python_cache_contract(local_gate)
    _assert_python_install_order(workflow)
    _assert_migration_manifest_loads()


def test_import_overlap_worker_uses_isolated_explicit_backend_bootstrap() -> None:
    path = ROOT / "backend/scripts/run_import_overlap_gate.py"
    spec = importlib.util.spec_from_file_location("import_overlap_gate", path)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    command = gate.worker_command()
    assert command[0] == sys.executable
    assert command[1:3] == ("-I", "-c")
    assert "sys.path.insert(0,backend)" in command[3]
    assert Path(command[4]).resolve() == (ROOT / "backend").resolve()
    assert Path(command[5]).resolve() == (ROOT / "backend/worker.py").resolve()


def test_release_a_source_transform_binds_exact_grile_whitespace_normalization() -> None:
    checker = _load_checker()
    transform = checker.verify_source_transform()
    assert transform["whitespace_normalization"] == {
        "path": "backend/services/grile_pilot_v2_sync.py",
        "baseline_git_mode": "100644",
        "baseline_git_blob": "27c05c7388cd134aebeae9b98efeb86f4831c77f",
        "baseline_sha256": "ac31c6551e61c1cc8e59731488dfe44b2468f37b00bc5a88933f6fd88aaa1f60",
        "preview_git_mode": "100644",
        "result_git_mode": "100644",
        "result_git_blob": "00a8f3ab186f2e600d5d810640c85a796a65a359",
        "result_sha256": "0e2aad80ca331ca5b713f9ab3adb42b72b7c08ed3aab971d94b7033b11319c46",
        "deleted_blank_lines": 5,
        "runtime_effect": "none",
    }


def test_production_deploy_binds_signature_and_root_entrypoint_to_exact_artifact() -> None:
    checker = _load_checker()
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    assert ".github/workflows/deploy.yml" in checker.EXPECTED_CHANGED_PATHS
    assert ".github/workflows/deploy.yml" in checker.EXPECTED_RELEASE_A_AUTHORITIES
    assert 'BASH_ENV: ""' in workflow and 'ENV: ""' in workflow
    assert 'GH_BIN=/usr/bin/gh' in workflow
    assert checker.GH_DELL_SHA256 not in workflow
    assert "141507c337e8b202ad398550c3b73d72f5af92e86f71665214538a81efd4c409" in workflow
    assert 'COSIGN_BIN="$RUNNER_TEMP/cosign/cosign"' in workflow
    assert checker.COSIGN_LINUX_AMD64_SHA256 in workflow
    for claim in (
        "--certificate-github-workflow-sha",
        "--certificate-github-workflow-repository",
        "--certificate-github-workflow-ref",
        "--certificate-github-workflow-trigger",
        "--certificate-github-workflow-name",
    ):
        assert claim in workflow
    assert "tar -xOzf \"$artifact\" ./ops/deploy-retail-artifact.sh" in workflow
    assert "stat -c '%u:%g:%a' \"$entrypoint\"" in workflow


def test_python_runtime_tree_property_round_trips_in_cyclonedx_metadata(
    tmp_path: Path,
) -> None:
    validator = _load_module(ROOT / "scripts/validate_release_sbom.py", "sbom_validator")
    runtime_venv = tmp_path / "venv"
    site = runtime_venv / "lib/python3.12/site-packages"
    dist_info = site / "demo-1.0.dist-info"
    dist_info.mkdir(parents=True)
    files = {
        site / "demo.py": b"VALUE = 1\n",
        dist_info / "METADATA": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
        dist_info / "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    for path, payload in files.items():
        path.write_bytes(payload)
    record_rows = []
    for path, payload in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
        record_rows.append(f"{path.relative_to(site)},{'sha256=' + digest},{len(payload)}")
    record_rows.append("demo-1.0.dist-info/RECORD,,")
    (dist_info / "RECORD").write_text("\n".join(record_rows) + "\n", encoding="utf-8")
    sbom_path = tmp_path / "python.cdx.json"
    sbom_path.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "metadata": {},
                "components": [
                    {
                        "type": "library",
                        "bom-ref": "pkg:pypi/demo@1.0",
                        "name": "demo",
                        "version": "1.0",
                        "purl": "pkg:pypi/demo@1.0",
                    }
                ],
                "dependencies": [{"ref": "pkg:pypi/demo@1.0", "dependsOn": []}],
            }
        ),
        encoding="utf-8",
    )
    digest = validator.bind_python_runtime_tree(sbom_path, runtime_venv)
    payload = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["properties"] == [
        {"name": validator.PYTHON_RUNTIME_TREE_PROPERTY, "value": digest}
    ]
    assert "properties" not in payload
    checker = _load_checker()
    assert checker.python_runtime_tree_digest_from_sbom(payload) == digest
    with pytest.raises(ValueError, match="runtime tree identity"):
        checker.python_runtime_tree_digest_from_sbom(
            {**payload, "metadata": {"properties": []}}
        )


def test_signed_python_runtime_supply_is_exact_and_content_bound(tmp_path: Path) -> None:
    checker = _load_checker()
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    requirements = ROOT / "backend/requirements.lock"
    requirements_target = artifact / checker.PYTHON_RUNTIME_REQUIREMENTS_NAME
    requirements_target.write_bytes(requirements.read_bytes())
    sbom_target = artifact / "SBOM.python.cdx.json"
    runtime_tree_sha256 = "1" * 64
    sbom_target.write_text(
        json.dumps(
            {
                "metadata": {
                    "properties": [
                        {
                            "name": checker.PYTHON_RUNTIME_TREE_PROPERTY,
                            "value": runtime_tree_sha256,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    wheel_name = "demo-1.0-py3-none-any.whl"
    wheel_payload = b"bounded synthetic wheel bytes"
    wheel_archive = artifact / checker.PYTHON_RUNTIME_WHEELS_NAME
    with tarfile.open(wheel_archive, mode="w:gz") as archive:
        member = tarfile.TarInfo(wheel_name)
        member.size = len(wheel_payload)
        archive.addfile(member, io.BytesIO(wheel_payload))
    sha256 = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    checksums = {
        checker.PYTHON_RUNTIME_REQUIREMENTS_NAME: sha256(requirements_target),
        checker.PYTHON_RUNTIME_WHEELS_NAME: sha256(wheel_archive),
        "SBOM.python.cdx.json": sha256(sbom_target),
    }
    supply: dict[str, Any] = {
        "schemaVersion": 1,
        "python": {
            "path": str(checker.PYTHON_BASE_PATH),
            "sha256": checker.PYTHON_BASE_SHA256,
            "version": "3.12.3",
        },
        "requirements": {
            "name": checker.PYTHON_RUNTIME_REQUIREMENTS_NAME,
            "sha256": checksums[checker.PYTHON_RUNTIME_REQUIREMENTS_NAME],
        },
        "sitePackages": {
            "property": checker.PYTHON_RUNTIME_TREE_PROPERTY,
            "sha256": runtime_tree_sha256,
        },
        "sbom": {
            "name": "SBOM.python.cdx.json",
            "sha256": checksums["SBOM.python.cdx.json"],
        },
        "bootstrapDistributions": {"pip": "24.0"},
        "wheelArchive": {
            "name": checker.PYTHON_RUNTIME_WHEELS_NAME,
            "sha256": checksums[checker.PYTHON_RUNTIME_WHEELS_NAME],
            "fileCount": 1,
            "totalBytes": len(wheel_payload),
        },
        "wheels": [
            {
                "name": wheel_name,
                "sha256": hashlib.sha256(wheel_payload).hexdigest(),
                "size": len(wheel_payload),
            }
        ],
    }
    supply_path = artifact / checker.PYTHON_RUNTIME_SUPPLY_NAME
    supply_path.write_text(
        json.dumps(supply, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    result = checker.verify_python_runtime_supply(
        artifact,
        checksums,
        subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        runtime_tree_sha256,
    )
    assert result["wheel_file_count"] == 1
    supply["sitePackages"]["sha256"] = "0" * 64
    supply_path.write_text(json.dumps(supply), encoding="utf-8")
    with pytest.raises(ValueError, match="tree identity"):
        checker.verify_python_runtime_supply(
            artifact,
            checksums,
            subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
            ).strip(),
            runtime_tree_sha256,
        )


def test_release_a_evidence_commands_are_relocatable() -> None:
    checker = _load_checker()
    release_a_sha = "a" * 40
    expected = f"test-results/closure/{release_a_sha}/release-a/schema-gate.json"
    assert checker.release_a_evidence_logical_path(release_a_sha) == expected
    schema_gate = (ROOT / "scripts/run_release_a_schema_gate.sh").read_text(
        encoding="utf-8"
    )
    assert 'EVIDENCE_RELATIVE_PATH="test-results/closure/$CURRENT_SHA/release-a/schema-gate.json"' in schema_gate
    assert 'os.environ["EVIDENCE_RELATIVE_PATH"]' in schema_gate
    assert 'os.environ["EVIDENCE_PATH"],' not in schema_gate


def test_release_a_gate_requires_fresh_canonical_evidence_and_authority_seed() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    schema_gate = (ROOT / "scripts/run_release_a_schema_gate.sh").read_text(
        encoding="utf-8"
    )
    assert "verify_release_a_authority_seed()" in checker
    assert "EXPECTED_RELEASE_A_AUTHORITIES" in checker
    assert 'EXPECTED_EVIDENCE_PATH="$ROOT_DIR/test-results/closure/$CURRENT_SHA/release-a/schema-gate.json"' in schema_gate
    assert "Release-A evidence path must be new" in schema_gate
    assert "realpath -m" in schema_gate


def test_promtool_cache_never_trusts_a_system_binary(tmp_path: Path) -> None:
    script = ROOT / "scripts/verify_promtool_cache.sh"
    source = script.read_text(encoding="utf-8")
    assert "command -v promtool" not in source
    assert 'source="system"' not in source
    assert 'PYTHON="/usr/bin/python3.12"' in source
    mode = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-s", "--", str(script.relative_to(ROOT))],
        text=True,
    ).split()[0]
    assert mode == "100755"
    evidence = tmp_path / "promtool.json"
    subprocess.run(
        [str(script), "self-test", "--evidence", str(evidence)],
        cwd=ROOT,
        check=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["result"] == "PASS"
    assert payload["cold_download_count"] == 1
    assert payload["warm_download_count"] == 0
    assert len(payload["archive_sha256"]) == 64
    assert len(payload["promtool_sha256"]) == 64


def test_release_b_workflow_is_only_the_three_frozen_insertions() -> None:
    checker = _load_checker()
    baseline = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    candidate = checker.expected_release_b_workflow(baseline)
    inserted_names = (
        "Python complexity closure contract",
        "Frontend structure closure contract",
        "Frontend critical coverage closure contract",
    )
    for name in inserted_names:
        assert name not in baseline
        assert candidate.count(name) == 1
    assert candidate.count(checker.EXPECTED_TYPECHECK_STEP) == 1
    assert all(token in candidate for token in checker.RELEASE_B_REQUIRED_CI_TOKENS)
    assert "SOURCE_SHA" not in checker.RELEASE_B_REQUIRED_CI_TOKENS
    assert "SHA256SUMS" not in checker.RELEASE_B_REQUIRED_CI_TOKENS
    artifact_builder = (ROOT / "ops/build-retail-release-artifact.sh").read_text(
        encoding="utf-8"
    )
    artifact_checker = CHECKER_PATH.read_text(encoding="utf-8")
    for artifact_token in ("SOURCE_SHA", "SHA256SUMS"):
        assert artifact_token not in candidate
        assert artifact_token in artifact_builder
        assert artifact_token in artifact_checker
    assert candidate != checker.expected_release_b_workflow(candidate)


def test_release_b_authorities_reject_digest_or_mode_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checker = _load_checker()
    real_contract = json.loads(
        (ROOT / "scripts/release-b-authority-contract-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert real_contract["required_paths"] == sorted(checker.EXPECTED_AUTHORITY_PATHS)
    assert len(real_contract["authorities"]) == len(checker.EXPECTED_AUTHORITY_PATHS) == 111
    assert checker.EXPECTED_RELEASE_A_AUTHORITIES <= checker.EXPECTED_AUTHORITY_PATHS
    assert "ops/deploy-retail-artifact.sh" in checker.EXPECTED_AUTHORITY_PATHS
    monkeypatch.setattr(checker, "EXPECTED_RELEASE_A_AUTHORITIES", set())
    monkeypatch.setattr(checker, "EXPECTED_AUTHORITY_PATHS", {"authority.py"})
    monkeypatch.setattr(checker, "EXPECTED_AUTHORITY_SET_NAMES", set())
    monkeypatch.setattr(checker, "EXPECTED_SOURCE_SNAPSHOTS", {})
    authority = tmp_path / "authority.py"
    authority.write_text("print('real gate')\n", encoding="utf-8")
    digest = hashlib.sha256(authority.read_bytes()).hexdigest()
    contract = {
        "schema_version": 2,
        "baseline_source_sha": checker.EXPECTED_BASELINE,
        "acceptance_criteria": sorted(checker.EXPECTED_AUTHORITY_CRITERIA),
        "release_a_authorities": [],
        "required_paths": ["authority.py"],
        "authority_sets": [],
        "source_snapshots": {},
        "authorities": [
            {
                "path": "authority.py",
                "sha256": digest,
                "git_mode": "100644",
                "supports": sorted(checker.EXPECTED_AUTHORITY_CRITERIA),
            }
        ],
    }
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/release-b-authority-contract-v1.json").write_text(
        json.dumps(contract), encoding="utf-8"
    )
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(
        checker,
        "git",
        lambda *args, **_kwargs: (
            "100644 blob authority.py"
            if args[:3] == ("ls-tree", "HEAD", "--")
            else ""
        ),
    )
    assert checker.verify_release_b_authorities()["authority_count"] == 1
    authority.write_text("print('no-op')\n", encoding="utf-8")
    with pytest.raises(ValueError, match="authority drift"):
        checker.verify_release_b_authorities()


def _assert_release_a_artifact_evidence_contract(checker: str, builder: str) -> None:
    for name in (
        "schema-gate.json",
        "release-a-candidate.json",
        "release-a-schema-empty.xml",
        "release-a-schema-restored.xml",
    ):
        assert name in checker
        assert name in builder
    assert "RELEASE_A_EVIDENCE_RUN_ID" in builder
    assert 'manifest["releaseAEvidence"]' in builder
    assert 'external.get("releaseAEvidence")' in checker


def _assert_artifact_cosign_contract(checker: str) -> None:
    assert "COSIGN_BIN" not in checker
    assert "COSIGN_LINUX_AMD64_SHA256" in checker
    assert "shutil.which(\"cosign\")" in checker


def _assert_frontend_build_input_contract(
    checker: str, builder: str, workflow: str
) -> None:
    assert "Generate exact-main Release-A schema evidence" in workflow
    assert "retail-release-a-schema-${{ github.sha }}" in workflow
    assert 'manifest["frontendBuildInput"]' not in builder
    assert '"frontendBuildInput": {' in builder
    assert "FRONTEND_BUILD_INPUT_SHA256_FILE" in builder
    assert "expected_frontend_build_input_sha256" in checker
    assert "retail-frontend-build-input-${{ github.sha }}" in workflow
    assert "VITE_FRONTEND_GLITCHTIP_DSN: ${{ secrets.VITE_GLITCHTIP_DSN }}" in workflow


def _assert_artifact_workflow_toolchain_fences(workflow: str) -> None:
    assert 'PYTHONNOUSERSITE: "1"' in workflow
    assert 'PYTHONSAFEPATH: "1"' in workflow
    assert workflow.count('PYTHONSTARTUP: ""') == 4
    assert workflow.count('NODE_OPTIONS: ""') == 5
    assert workflow.count('BASH_ENV: ""') == 5
    assert 'actions/setup-node@' not in workflow
    assert "caddy@sha256:844f60b64e4724a5aa8245e019dace0d3f199f7433ce6c57676cb30a920dbad9" in workflow
    assert 'docker run --pull=never --rm --network none' in workflow
    assert "caddy:2.11.4" not in workflow
    assert workflow.count('RETAIL_NODE: /opt/codex-desktop/resources/node-runtime/bin/node') == 3
    assert '"$audit_python" -I -S scripts/check_release_a_candidate.py' in workflow


def test_artifact_contract_binds_main_evidence_and_pinned_cosign() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    builder = (ROOT / "ops/build-retail-release-artifact.sh").read_text(
        encoding="utf-8"
    )
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    _assert_release_a_artifact_evidence_contract(checker, builder)
    _assert_artifact_cosign_contract(checker)
    _assert_frontend_build_input_contract(checker, builder, workflow)
    _assert_artifact_workflow_toolchain_fences(workflow)


def _assert_exact_checkout_audit_contract(checker: str) -> None:
    assert "--verify-artifact-checkout" in checker
    assert "def build_exact_checkout_frontend(rum_dsn: str)" in checker
    assert '"npm_config_offline": "true"' in checker
    assert 'for key in ("NODE_OPTIONS", "NODE_PATH")' in checker
    assert '"ci",\n        "--offline",\n        "--ignore-scripts"' in checker
    assert 'r"v22\\.\\d+\\.\\d+"' in checker
    assert "signed archive tracked source differs from exact Git tree" in checker
    assert "signed archive dist differs from exact-checkout tested build" in checker
    assert "--verify-signed-artifact-audit" in checker
    assert "artifact-checkout.sigstore.json" in checker
    assert "frontend_build_input_sha256" in checker
    assert "--expected-workflow-run-id" in checker
    assert "artifact provenance does not match the audit workflow run" in checker


def _assert_exact_checkout_audit_workflow(workflow: str) -> None:
    assert "Rebuild exact main and audit signed artifact" in workflow
    assert "retail-artifact-audit-${{ github.sha }}" in workflow
    assert "--frontend-rum-dsn-from-environment" in workflow
    assert "ARTIFACT_AUDIT_RUN_ID: ${{ github.run_id }}" in workflow
    assert "ARTIFACT_AUDIT_RUN_ATTEMPT: ${{ github.run_attempt }}" in workflow
    assert "ARTIFACT_AUDIT_WORKFLOW_SHA: ${{ github.workflow_sha }}" in workflow


def _assert_exact_checkout_audit_plan(plan: str) -> None:
    assert "clean detached" in plan and "exact-SHA Git checkout" in plan
    assert "unpacked artifact `git rev-parse HEAD`" not in plan


def test_artifact_audit_runs_from_exact_checkout_and_compares_source_and_dist() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    plan = (ROOT / "docs/exec-plans/active/UR-CLOSE-20260812.md").read_text(
        encoding="utf-8"
    )
    _assert_exact_checkout_audit_contract(checker)
    _assert_exact_checkout_audit_workflow(workflow)
    _assert_exact_checkout_audit_plan(plan)


def test_release_b_authorities_bind_transitive_runners_and_durable_snapshots() -> None:
    checker = _load_checker()
    contract = json.loads(
        (ROOT / "scripts/release-b-authority-contract-v1.json").read_text(
            encoding="utf-8"
        )
    )
    authority_paths = {item["path"] for item in contract["authorities"]}
    assert "scripts/validate_release_sbom.py" in authority_paths
    assert "scripts/verify_frontend_rum_build.mjs" in authority_paths
    for path in (
        "package.json",
        "backend/scripts/run_tests_isolated.sh",
        "playwright.browser-smoke.config.ts",
        "playwright.pwa-workbox.config.ts",
        "playwright.real.config.ts",
        "scripts/run_pwa_release_lifecycle.sh",
        "scripts/run_real_e2e.sh",
        "vitest.config.ts",
    ):
        assert path in checker.EXPECTED_AUTHORITY_PATHS
        assert path in contract["required_paths"]
    snapshots = contract["source_snapshots"]
    assert snapshots == checker.EXPECTED_SOURCE_SNAPSHOTS
    assert all(
        value["ref"].startswith("refs/tags/ur-close-20260812-")
        for value in snapshots.values()
    )
    verified = checker.verify_source_snapshots(
        require_ancestors=False, verify_remote=True
    )
    assert all(value["remote_ref_verified"] for value in verified.values())


def test_dynamic_authority_sets_freeze_recursive_pytest_and_complete_e2e_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    inventory = "\n".join(
        (
            "backend/tests/test_top.py",
            "backend/tests/nested/test_nested.py",
            "backend/tests/nested/legacy_test.py",
            "backend/tests/nested/fixture.json",
            "e2e/flow.spec.ts",
            "e2e/nested/flow.spec.mjs",
            "e2e/nested/flow.spec.tsx",
            "e2e/nested/fixture.json",
            "src/feature/view.test.tsx",
        )
    )
    monkeypatch.setattr(
        checker,
        "git",
        lambda *args, **_kwargs: (
            inventory if args[:4] == ("ls-tree", "-r", "--name-only", "HEAD") else ""
        ),
    )
    assert checker.authority_set_selected_paths("backend_test_suite") == {
        "backend/tests/test_top.py",
        "backend/tests/nested/test_nested.py",
        "backend/tests/nested/legacy_test.py",
        "backend/tests/nested/fixture.json",
    }
    assert checker.authority_set_selected_paths("e2e_test_suite") == {
        "e2e/flow.spec.ts",
        "e2e/nested/flow.spec.mjs",
        "e2e/nested/flow.spec.tsx",
        "e2e/nested/fixture.json",
    }


def test_release_b_runtime_composition_rejects_frozen_drift_and_extra_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    frozen = {f"runtime/frozen_{index:03d}.py" for index in range(272)}
    immutable = {f"contract/immutable_{index:02d}.json" for index in range(25)}
    immutable_from_a = {
        ".agent/contract-lock.json",
        "backend/services/grile_pilot_v2.py",
    }
    mutable = {"runtime/mutable.py"}
    mutable_tests = {f"tests/mutable_{index:02d}.py" for index in range(7)}
    special = {".github/workflows/ci.yml"}
    preview_delta = (
        frozen | immutable | immutable_from_a | mutable | mutable_tests | special
    )
    assert len(preview_delta) == 308
    outbox_unique = {"backend/tests/test_outbox.py"}
    scale_unique = {"backend/scripts/run_scale.py"}
    monkeypatch.setattr(checker, "EXPECTED_BASELINE", "base")
    monkeypatch.setattr(
        checker,
        "EXPECTED_SOURCE_SNAPSHOTS",
        {
            "release_b_integrated_preview": {"commit": "preview"},
            "outbox_acceptance_contract": {"commit": "outbox"},
            "scale_authority": {"commit": "scale"},
        },
    )
    monkeypatch.setattr(checker, "RELEASE_B_MUTABLE_PATHS", mutable)
    monkeypatch.setattr(checker, "RELEASE_B_MUTABLE_TEST_PATHS", mutable_tests)
    monkeypatch.setattr(checker, "RELEASE_B_IMPLEMENTATION_PATHS", mutable)
    monkeypatch.setattr(checker, "RELEASE_B_SPECIAL_PATHS", special)
    monkeypatch.setattr(
        checker, "RELEASE_B_IMMUTABLE_FROM_A_PATHS", immutable_from_a
    )
    monkeypatch.setattr(checker, "RELEASE_B_OUTBOX_UNIQUE_PATHS", outbox_unique)
    monkeypatch.setattr(checker, "RELEASE_B_SCALE_UNIQUE_PATHS", scale_unique)
    actual_delta = preview_delta | outbox_unique | scale_unique

    def fake_diff(before: str, after: str) -> set[str]:
        if (before, after) == ("base", "preview"):
            return preview_delta
        if (before, after) == ("base", "outbox"):
            return preview_delta | outbox_unique
        if (before, after) == ("base", "scale"):
            return preview_delta | scale_unique
        if (before, after) == ("release-a", "HEAD"):
            return actual_delta
        raise AssertionError((before, after))

    identities = {
        ("preview", path): ("100644", f"preview-{path}") for path in preview_delta
    }
    identities.update(
        {("HEAD", path): value for (_commit, path), value in identities.items()}
    )
    executable_frozen = sorted(frozen)[0]
    identities[("preview", executable_frozen)] = (
        "100755",
        f"preview-{executable_frozen}",
    )
    identities[("HEAD", executable_frozen)] = identities[
        ("preview", executable_frozen)
    ]
    identities[("HEAD", "runtime/mutable.py")] = ("100644", "implemented")
    for path in mutable_tests:
        identities[("HEAD", path)] = ("100644", f"implemented-{path}")
    for path in immutable_from_a:
        identities[("release-a", path)] = ("100644", f"release-a-{path}")
        identities[("HEAD", path)] = identities[("release-a", path)]
    monkeypatch.setattr(checker, "git_diff_paths", fake_diff)
    monkeypatch.setattr(
        checker,
        "git_path_identity",
        lambda commit, path: identities.get((commit, path), ("", "")),
    )
    evidence = checker.verify_release_b_runtime_composition("release-a", immutable)
    assert evidence["preview_delta_count"] == 308
    assert evidence["frozen_preview_count"] == 272

    changed = sorted(frozen)[1]
    identities[("HEAD", changed)] = ("100644", "tampered")
    with pytest.raises(ValueError, match="frozen preview runtime drift"):
        checker.verify_release_b_runtime_composition("release-a", immutable)
    identities[("HEAD", changed)] = identities[("preview", changed)]
    for path in immutable_from_a:
        identities[("HEAD", path)] = ("100644", "tampered")
        with pytest.raises(ValueError, match="changed immutable Release-A path"):
            checker.verify_release_b_runtime_composition("release-a", immutable)
        identities[("HEAD", path)] = identities[("release-a", path)]
        identities[("HEAD", path)] = (
            "100755",
            identities[("release-a", path)][1],
        )
        with pytest.raises(ValueError, match="changed immutable Release-A path"):
            checker.verify_release_b_runtime_composition("release-a", immutable)
        identities[("HEAD", path)] = identities[("release-a", path)]
    actual_delta.add("backend/services/backdoor.py")
    with pytest.raises(ValueError, match="unexpected path mutation"):
        checker.verify_release_b_runtime_composition("release-a", immutable)


def test_release_b_real_preview_topology_classifies_release_a_preserved_paths() -> None:
    checker = _load_checker()
    assert len(checker.EXPECTED_CHANGED_PATHS) == 42
    assert len(checker.RELEASE_B_MUTABLE_PATHS) == 23
    assert len(checker.RELEASE_B_IMPLEMENTATION_PATHS) == 18
    assert len(checker.RELEASE_B_MUTABLE_TEST_PATHS) == 10
    assert checker.RELEASE_B_IMPLEMENTATION_PATHS < checker.RELEASE_B_MUTABLE_PATHS
    assert checker.RELEASE_B_MUTABLE_TEST_PATHS.isdisjoint(
        checker.RELEASE_B_MUTABLE_PATHS
        | checker.RELEASE_B_IMMUTABLE_CURRENT_PATHS
        | checker.RELEASE_B_SPECIAL_PATHS
    )
    preview_sha = checker.EXPECTED_SOURCE_SNAPSHOTS[
        "release_b_integrated_preview"
    ]["commit"]
    preview_delta = checker.git_diff_paths(checker.EXPECTED_BASELINE, preview_sha)
    immutable_from_a = {
        ".agent/contract-lock.json",
        "backend/services/grile_pilot_v2.py",
    }
    assert checker.RELEASE_B_IMMUTABLE_FROM_A_PATHS == immutable_from_a
    classified_exclusions = (
        checker.RELEASE_B_IMMUTABLE_CURRENT_PATHS
        | checker.RELEASE_B_IMMUTABLE_FROM_A_PATHS
        | checker.RELEASE_B_SPECIAL_PATHS
        | checker.RELEASE_B_MUTABLE_PATHS
        | checker.RELEASE_B_MUTABLE_TEST_PATHS
    )
    frozen = preview_delta - classified_exclusions
    assert len(preview_delta) == 308
    assert len(frozen) == 272
    assert immutable_from_a <= preview_delta
    assert immutable_from_a.isdisjoint(frozen)
    assert len(preview_delta & checker.RELEASE_B_IMMUTABLE_CURRENT_PATHS) == 17
    assert len(preview_delta & checker.RELEASE_B_SPECIAL_PATHS) == 1
    assert len(preview_delta & checker.RELEASE_B_MUTABLE_PATHS) == 14
    assert len(preview_delta & checker.RELEASE_B_MUTABLE_TEST_PATHS) == 2
    frozen_executables = {
        path
        for path in frozen
        if checker.git_path_identity(preview_sha, path)[0] == "100755"
    }
    assert frozen_executables == {
        "backend/scripts/run_tests_isolated.sh",
        "scripts/run_pwa_release_lifecycle.sh",
    }
    assert all(
        checker.git_path_identity("HEAD", path)[0] == "100644"
        for path in immutable_from_a
    )


def test_release_a_merge_topology_binds_predecessor_and_final_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    final_head = "f" * 40
    final_merge = "e" * 40
    parents = {
        checker.RELEASE_A_PREDECESSOR_MERGE_SHA: (
            f"{checker.EXPECTED_BASELINE} {checker.RELEASE_A_PREDECESSOR_HEAD_SHA}"
        ),
        final_merge: f"{checker.RELEASE_A_PREDECESSOR_MERGE_SHA} {final_head}",
    }

    def fake_git(*args: str) -> str:
        assert args[:3] == ("show", "-s", "--format=%P")
        return parents[args[3]]

    monkeypatch.setattr(checker, "git", fake_git)
    evidence = checker.verify_release_a_merge_topology(final_head, final_merge)
    assert evidence["predecessor_pr"] == 151
    assert evidence["predecessor_branch"] == (
        "codex/retail-definitive-closure-20260812"
    )
    assert evidence["release_a_parents"] == [
        checker.RELEASE_A_PREDECESSOR_MERGE_SHA,
        final_head,
    ]
    parents[final_merge] = f"{checker.EXPECTED_BASELINE} {final_head}"
    with pytest.raises(ValueError, match="final Release-A merge topology mismatch"):
        checker.verify_release_a_merge_topology(final_head, final_merge)
    parents[final_merge] = (
        f"{checker.RELEASE_A_PREDECESSOR_MERGE_SHA} {final_head}"
    )
    parents[checker.RELEASE_A_PREDECESSOR_MERGE_SHA] = (
        f"{checker.RELEASE_A_PREDECESSOR_HEAD_SHA} {checker.EXPECTED_BASELINE}"
    )
    with pytest.raises(ValueError, match="predecessor merge topology mismatch"):
        checker.verify_release_a_merge_topology(final_head, final_merge)


def _assert_ac17_invocation_contract(verifier: str, plan: str) -> None:
    for token in (
        "--main-a-sha",
        "--main-b-sha",
        "--release-a-artifact-dir",
        "--release-b-artifact-dir",
        "--release-a-evidence",
        "--release-b-archive-sha256",
        "--backup-handle",
        "--probe-month",
        "--manager-cookie-file",
        "--forbidden-cookie-file",
        "--release-a-pr",
        "--release-b-pr",
    ):
        assert token in verifier
        assert token in plan
    assert 'RELEASE_A_PR_NUMBER="152"' in verifier
    assert "--release-a-pr 152" in plan


def _assert_ac17_ref_reconciliation(verifier: str) -> None:
    assert "refs-primary.json" in verifier
    assert "refs-dell.json" in verifier
    assert "refs-github.json" in verifier
    assert "codex/retail-definitive-closure-20260812" in verifier
    assert "codex/retail-definitive-closure-rev27" in verifier
    assert "codex/retail-definitive-closure-b-projected-rev27" in verifier
    assert "pr-a-predecessor.json" in verifier
    assert "headRefOid" in verifier
    assert '"refs/heads/$RELEASE_A_PREDECESSOR_BRANCH"' in verifier
    assert "predecessor_parents != [pbase,phead]" in verifier
    assert "release_a_parents != [pmerge,av[\"headRefOid\"]]" in verifier
    assert verifier.count("codex/retail-close-preview-v3") == 2
    assert "ls-remote origin refs/heads/main" in verifier
    assert 'remote_lines != [f"{b}\\trefs/heads/main"]' in verifier
    assert 'export GH_HOST=github.com' in verifier
    assert (
        'GITHUB_ORIGIN_URL="https://github.com/anervalens-netizen/unihub-retail.git"'
        in verifier
    )
    assert 'origin=git("remote","get-url","origin")' in verifier
    assert verifier.count("origin!=canonical_origin") == 2
    assert verifier.count("GH_HOST=github.com GH_PAGER=cat") == 3
    assert '[[ "$mode" == "400" || "$mode" == "600" ]]' in verifier
    assert '[[ "$owner_uid" == "0" || "$owner_uid" == "$OPERATOR_UID" ]]' in verifier


def _assert_ac17_browser_control_is_private(verifier: str) -> None:
    assert "probe_authenticated_browser" in verifier
    assert '"browser.json"' in verifier
    assert "BROWSER_CHROME_SHA256" in verifier
    assert '"--remote-debugging-pipe"' in verifier
    assert "--remote-debugging-port" not in verifier
    assert "--no-sandbox" not in verifier
    assert "from websockets" not in verifier
    assert "os.setgroups([])" in verifier
    assert "os.setgid(operator_gid)" in verifier
    assert "os.setuid(operator_uid)" in verifier
    assert "os.killpg(process.pid, signal.SIGTERM)" in verifier
    assert "pass_fds=(3, 4)" in verifier
    assert "DEPLOY_HANDLE_EPOCH <= started_epoch && started_epoch <= DEPLOYED_EPOCH" in verifier
    assert 'readlink -f "/proc/$pid/cwd"' in verifier
    assert 'readlink -f "/proc/$pid/exe"' in verifier


def _assert_ac17_browser_journeys(verifier: str) -> None:
    assert "services-runtime-before.json" in verifier
    assert "services-runtime-after.json" in verifier
    assert "def drain_network_events(seconds: float = 2.0)" in verifier
    assert "exercise_journey(mobile=True)\n    drain_network_events()" in verifier
    assert '"control_transport": "private_cdp_pipe"' in verifier
    assert '"sandbox_bypass": False' in verifier
    for marker in (
        "Sales Hub",
        "Grile V2 · pilot",
        "Calculator Target",
        "Statistici Salarii",
        "Import fișier vânzări",
        "Builder export Excel",
        "mobile-dashboard",
        "mobile-grile-v2",
        "mobile-target",
        "mobile-salary-read",
        "mobile-imports",
        "mobile-exports-read",
    ):
        assert marker in verifier
    assert "exercise_journey(mobile=False)" in verifier
    assert "exercise_journey(mobile=True)" in verifier


def _assert_ac17_python_runtime_contract(verifier: str) -> None:
    assert "export PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 PYTHONDONTWRITEBYTECODE=1" in verifier
    assert 'verify_python_runtime "$WORK/fragments/python-runtime-before.json"' in verifier
    assert 'verify_python_runtime "$WORK/fragments/python-runtime-after.json"' in verifier
    assert '"$PYTHON" -B -I -' in verifier
    assert (
        '"command": "/usr/bin/python3.12 -m venv '
        '/opt/Mobiup/unihub-retail/backend/venv"'
        in verifier
    )
    assert 'importlib.metadata.distributions(path=[str(site_packages)])' in verifier
    assert 'if sbom_versions != expected or sbom_hashes != expected_hashes:' in verifier
    assert '"site_packages_tree_sha256": tree_sha256' in verifier
    assert '"pyc_file_count": 0' in verifier
    assert '"unowned_file_count": 0' in verifier
    assert '"interpreter_symlink_count": len(expected_interpreter_links)' in verifier
    assert '"unsafe_symlink_count": 0' in verifier


def _assert_ac17_rollback_artifacts(verifier: str) -> None:
    assert '"python-runtime-before.json","python-runtime-after.json"' in verifier
    assert '"deploy-entrypoint-bootstrap.json"' in verifier
    assert '"rollback-python-runtime.json"' in verifier
    assert '"rollback-python-supply.json"' in verifier
    assert '"$BACKUP_HANDLE/venv.pre-switch"' in verifier
    assert '"$BACKUP_HANDLE/python-runtime-supply.old"' in verifier


def _assert_ac17_cookie_contract(verifier: str) -> None:
    assert 'allowed_domains = {"retail.unihub.ro", ".retail.unihub.ro"}' in verifier
    assert "non-Retail cookie record rejected" in verifier
    assert '"domain": domain' in verifier
    assert "cookie path does not match Retail root" in verifier
    assert "Retail HTTPS cookie is not Secure" in verifier
    assert "cookie is expired" in verifier
    assert '"values_recorded": False' in verifier


def _assert_ac17_outbox_metrics_contract(verifier: str) -> None:
    assert 'query={__name__=~"^(?:retail_outbox_oldest_pending_seconds|' in verifier
    assert 'expected_scalar={"retail_outbox_oldest_pending_seconds","retail_outbox_head_blocked","retail_outbox_completed_total","retail_outbox_failed_total"}' in verifier
    assert 'histogram="retail_outbox_delivery_duration_seconds"' in verifier
    assert "names != expected_exposition" in verifier
    assert 'query=count({__name__=~".*outbox.*"})' not in verifier
    assert 'set(types) - {"retail.sales_generation_promoted.v1"}' in verifier
    assert "protected outbox event type was activated in production" in verifier


def _assert_ac17_direct_python_contract(verifier: str) -> None:
    direct_python = [
        line.strip()
        for line in verifier.splitlines()
        if line.strip().startswith('"$PYTHON_BASE" ')
    ]
    assert direct_python
    assert all(line.startswith('"$PYTHON_BASE" -I -S ') for line in direct_python)
    assert 'COSIGN_BIN="$COSIGN_BIN" "$PYTHON_BASE" -I -S ' in verifier


def _assert_ac17_self_test() -> None:
    completed = subprocess.run(
        [str(ROOT / "scripts/verify_deployed_release.sh"), "--self-test"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "AC-17 verifier self-test PASS" in completed.stdout


def test_ac17_freezes_complete_invocation_and_three_way_ref_reconciliation() -> None:
    verifier = (ROOT / "scripts/verify_deployed_release.sh").read_text(
        encoding="utf-8"
    )
    plan = (ROOT / "docs/exec-plans/active/UR-CLOSE-20260812.md").read_text(
        encoding="utf-8"
    )
    _assert_ac17_invocation_contract(verifier, plan)
    _assert_ac17_ref_reconciliation(verifier)
    _assert_ac17_browser_control_is_private(verifier)
    _assert_ac17_browser_journeys(verifier)
    _assert_ac17_python_runtime_contract(verifier)
    _assert_ac17_rollback_artifacts(verifier)
    _assert_ac17_cookie_contract(verifier)
    _assert_ac17_outbox_metrics_contract(verifier)
    _assert_ac17_direct_python_contract(verifier)
    _assert_ac17_self_test()


def test_ac16_has_executable_github_run_and_signed_audit_authorities() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    plan = (ROOT / "docs/exec-plans/active/UR-CLOSE-20260812.md").read_text(
        encoding="utf-8"
    )
    assert "--verify-github-release-runs" in checker
    assert 'GH_PATH = Path("/usr/bin/gh")' in checker
    assert "GH_DELL_SHA256" in checker
    assert 'TASK_A_BRANCH = "codex/retail-definitive-closure-rev27"' in checker
    assert "RELEASE_A_PR_NUMBER = 152" in checker
    assert "RELEASE_A_PREDECESSOR_PR_NUMBER = 151" in checker
    assert "RELEASE_A_PREDECESSOR_MERGE_SHA" in checker
    assert "verify_release_a_merge_topology" in checker
    assert "live GitHub refs/heads/main differs from MAIN_B_SHA" in checker
    assert "--verify-github-release-runs" in plan
    assert "--verify-signed-artifact-audit" in plan
    ac16 = plan.rsplit("| AC-16 |", 1)[1].split("\n", 1)[0]
    assert "..." not in ac16
    assert "--release-a-pr 152" in ac16
