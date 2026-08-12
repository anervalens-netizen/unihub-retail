from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from main import app
from observability.metrics_network import metrics_peer_allowed
from observability.prometheus import UNMATCHED_HANDLER, canonical_handler
from observability.worker_metrics import start_worker_metrics


class Route:
    path = "/api/items/{item_id}"


def test_metrics_handler_is_bounded_for_unmatched_routes() -> None:
    assert canonical_handler({"route": Route()}) == "/api/items/{item_id}"
    assert canonical_handler({"path": "/random-user-controlled-path"}) == UNMATCHED_HANDLER


def test_metrics_acl_accepts_only_configured_prometheus_subnet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROMETHEUS_DOCKER_GATEWAY", "172.23.0.1")
    monkeypatch.setenv("PROMETHEUS_DOCKER_SUBNET", "172.23.0.0/16")
    assert metrics_peer_allowed("172.23.0.2") is True
    assert metrics_peer_allowed("127.0.0.1") is False
    assert metrics_peer_allowed("100.64.0.1") is False
    assert metrics_peer_allowed(None) is False


@pytest.mark.anyio
async def test_metrics_route_is_hidden_outside_prometheus_subnet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROMETHEUS_DOCKER_GATEWAY", "172.23.0.1")
    monkeypatch.setenv("PROMETHEUS_DOCKER_SUBNET", "172.23.0.0/16")
    transport = httpx.ASGITransport(app=app, client=("100.64.0.4", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/metrics", headers={"X-Forwarded-For": "172.23.0.2"}
        )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_metrics_route_allows_direct_prometheus_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROMETHEUS_DOCKER_GATEWAY", "172.23.0.1")
    monkeypatch.setenv("PROMETHEUS_DOCKER_SUBNET", "172.23.0.0/16")
    transport = httpx.ASGITransport(app=app, client=("172.23.0.2", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_worker_metrics_rejects_wildcard_loopback_and_wrong_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROMETHEUS_DOCKER_GATEWAY", "172.23.0.1")
    monkeypatch.setenv("PROMETHEUS_DOCKER_SUBNET", "172.23.0.0/16")
    monkeypatch.setenv("WORKER_METRICS_PORT", "9901")
    for host in ("0.0.0.0", "127.0.0.1", "172.23.0.2"):
        monkeypatch.setenv("WORKER_METRICS_HOST", host)
        with pytest.raises(RuntimeError, match="detected Prometheus Docker gateway"):
            start_worker_metrics("operations")


def _read_retail_units(root: Path) -> dict[str, str]:
    paths = {
        "web": "ops/systemd/unihub-backend.service",
        "operations": "unihub-worker.service",
        "imports": "ops/systemd/unihub-import-worker.service",
        "grile": "ops/systemd/unihub-grile-worker.service",
        "exports": "ops/systemd/unihub-export-worker.service",
        "salary_exports": "ops/systemd/unihub-salary-export-worker.service",
        "migrations": "ops/systemd/unihub-retail-migrate.service",
    }
    return {
        name: (root / path).read_text(encoding="utf-8")
        for name, path in paths.items()
    }


def _assert_metrics_topology(units: dict[str, str]) -> None:
    web, operations, imports = units["web"], units["operations"], units["imports"]
    assert "--host 0.0.0.0" in web
    assert "PROMETHEUS_MULTIPROC_DIR=/run/unihub-retail-prometheus" in web
    for unit in (web, operations, imports, units["grile"], units["exports"], units["salary_exports"]):
        assert "EnvironmentFile=/opt/Mobiup/ops/prometheus/unihub-retail-network.env" in unit
    for unit in (operations, imports, units["grile"], units["exports"], units["salary_exports"]):
        assert "WORKER_METRICS_HOST=127.0.0.1" not in unit
        assert "WORKER_METRICS_HOST=0.0.0.0" not in unit
    assert "WORKER_METRICS_PORT=9901" in operations
    assert "WORKER_METRICS_PORT=9902" in imports
    assert "WORKER_METRICS_PORT=9903" in units["grile"]
    assert "WORKER_METRICS_PORT=9904" in units["exports"]
    assert "WORKER_METRICS_PORT=9905" in units["salary_exports"]


def _assert_exact_write_paths(units: dict[str, str]) -> None:
    web = units["web"]
    operations, imports = units["operations"], units["imports"]
    grile, exports = units["grile"], units["exports"]
    salary_exports, migrations = units["salary_exports"], units["migrations"]
    assert "ReadWritePaths=/opt/Mobiup/unihub-retail/data/import_spool" in web
    assert "ReadWritePaths=" not in operations
    assert "ReadWritePaths=" not in migrations
    assert "ReadWritePaths=/opt/Mobiup/unihub-retail/data/import_spool" in imports
    assert "ReadWritePaths=/opt/Mobiup/unihub-retail/data/promo_generations" in imports
    assert "ReadWritePaths=/opt/Mobiup/unihub-retail/backend/outputs/grile" in grile
    assert "ReadWritePaths=/opt/Mobiup/unihub-retail/data/export_artifacts" in exports
    assert (
        "ReadWritePaths=/opt/Mobiup/unihub-retail/data/export_artifacts/salary"
        in salary_exports
    )
    salary_namespace_mask = (
        "InaccessiblePaths=-/opt/Mobiup/unihub-retail/data/export_artifacts/salary"
    )
    assert all(
        salary_namespace_mask in unit
        for unit in (operations, imports, grile, exports, migrations)
    )
    assert salary_namespace_mask not in web
    assert salary_namespace_mask not in salary_exports


def _assert_no_broad_write_paths(units: dict[str, str]) -> None:
    approved_write_paths = {
        "/opt/Mobiup/unihub-retail/data/import_spool",
        "/opt/Mobiup/unihub-retail/data/promo_generations",
        "/opt/Mobiup/unihub-retail/backend/outputs/grile",
        "/opt/Mobiup/unihub-retail/data/export_artifacts",
        "/opt/Mobiup/unihub-retail/data/export_artifacts/salary",
    }
    for unit in units.values():
        write_paths = {
            line.removeprefix("ReadWritePaths=")
            for line in unit.splitlines()
            if line.startswith("ReadWritePaths=")
        }
        assert write_paths <= approved_write_paths
        assert not any(
            path.endswith(("/backend", "/src", "/ops", "/config"))
            or path == "/opt/Mobiup/unihub-retail"
            for path in write_paths
        )


def _assert_systemd_write_boundaries(units: dict[str, str]) -> None:
    all_units = tuple(units.values())
    assert all("ReadWritePaths=/opt/Mobiup\n" not in unit for unit in all_units)
    assert all("ProtectSystem=strict" in unit for unit in all_units)
    assert all("RestrictSUIDSGID=true" in unit for unit in all_units)
    assert all("PYTHONDONTWRITEBYTECODE=1" in unit for unit in all_units)
    _assert_exact_write_paths(units)
    _assert_no_broad_write_paths(units)


def _assert_runtime_os_identities(units: dict[str, str]) -> None:
    expected = {
        "web": (
            "unihub-web",
            "unihub-web",
            "unihub-import-spool unihub-promo-artifacts unihub-grile-artifacts unihub-export-artifacts",
            "0007",
        ),
        "operations": ("unihub-operations", "unihub-operations", None, "0077"),
        "imports": (
            "unihub-import",
            "unihub-import",
            "unihub-import-spool unihub-promo-artifacts",
            "0007",
        ),
        "grile": (
            "unihub-grile",
            "unihub-grile",
            "unihub-operations unihub-grile-artifacts",
            "0007",
        ),
        "exports": (
            "unihub-export",
            "unihub-export",
            "unihub-operations unihub-export-artifacts",
            "0007",
        ),
        "salary_exports": (
            "unihub-salary-export",
            "unihub-salary-export",
            "unihub-export-artifacts",
            "0007",
        ),
        "migrations": ("unihub-migrate", "unihub-migrate", None, "0077"),
    }
    for name, (user, group, supplementary, umask) in expected.items():
        lines = units[name].splitlines()
        assert [line for line in lines if line.startswith("User=")] == [f"User={user}"]
        assert [line for line in lines if line.startswith("Group=")] == [f"Group={group}"]
        expected_supplementary = (
            [] if supplementary is None else [f"SupplementaryGroups={supplementary}"]
        )
        assert [line for line in lines if line.startswith("SupplementaryGroups=")] == (
            expected_supplementary
        )
        assert [line for line in lines if line.startswith("UMask=")] == [f"UMask={umask}"]


def test_systemd_uses_multiprocess_web_metrics_and_detected_gateway_env() -> None:
    units = _read_retail_units(Path(__file__).resolve().parents[2])
    _assert_metrics_topology(units)
    _assert_systemd_write_boundaries(units)
    _assert_runtime_os_identities(units)


def test_runtime_identity_provisioners_are_fail_closed_and_secret_safe() -> None:
    root = Path(__file__).resolve().parents[2]
    os_provisioner = (root / "ops/provision-retail-service-identities.sh").read_text(
        encoding="utf-8"
    )
    db_provisioner = (
        root / "ops/provision-retail-salary-export-database.sh"
    ).read_text(encoding="utf-8")

    for user in (
        "unihub-web",
        "unihub-operations",
        "unihub-import",
        "unihub-grile",
        "unihub-export",
        "unihub-salary-export",
        "unihub-migrate",
    ):
        assert user in os_provisioner
    assert "useradd --system --no-create-home --home-dir /nonexistent" in os_provisioner
    assert 'usermod --lock "$user"' in os_provisioner
    assert "root:$group:640" in os_provisioner

    assert "openssl rand -hex 32" in db_provisioner
    assert "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in db_provisioner
    assert "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT" in db_provisioner
    assert "WITH INHERIT TRUE, SET FALSE" in db_provisioner
    assert "direct grant, default ACL, or owned object" in db_provisioner
    assert "root:$SALARY_ENV_GROUP:640" in db_provisioner
    assert "runtime_password" not in db_provisioner.split("printf 'retail_salary_export", 1)[1]


def test_runtime_relies_on_deploy_setgid_and_never_sets_special_bits() -> None:
    root = Path(__file__).resolve().parents[2]
    runtime_modules = (
        "backend/services/export_operations.py",
        "backend/services/grile_monthly_integrity.py",
        "backend/services/imports.py",
        "backend/services/sales_artifacts.py",
    )
    for module in runtime_modules:
        assert "0o2770" not in (root / module).read_text(encoding="utf-8")

    deployer = (root / "ops/deploy-retail-artifact.sh").read_text(encoding="utf-8")
    assert "SHARED_DIRECTORY_MODE=2770" in deployer
    assert "SHARED_DIRECTORY_MODE=770" in deployer


def test_runtime_verifier_sets_backend_pythonpath_itself() -> None:
    root = Path(__file__).resolve().parents[2]
    verifier = (root / "ops/verify-forensic-remediation-runtime.sh").read_text(
        encoding="utf-8"
    )

    assert 'PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"' in verifier
