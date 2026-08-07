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


def test_systemd_uses_multiprocess_web_metrics_and_detected_gateway_env() -> None:
    root = Path(__file__).resolve().parents[2]
    web = (root / "ops/systemd/unihub-backend.service").read_text(encoding="utf-8")
    operations = (root / "unihub-worker.service").read_text(encoding="utf-8")
    imports = (root / "ops/systemd/unihub-import-worker.service").read_text(encoding="utf-8")

    assert "--host 0.0.0.0" in web
    assert "PROMETHEUS_MULTIPROC_DIR=/run/unihub-retail-prometheus" in web
    assert "EnvironmentFile=/opt/Mobiup/ops/prometheus/unihub-retail-network.env" in web
    assert "EnvironmentFile=/opt/Mobiup/ops/prometheus/unihub-retail-network.env" in operations
    assert "WORKER_METRICS_HOST=127.0.0.1" not in operations
    assert "WORKER_METRICS_HOST=0.0.0.0" not in operations
    assert "WORKER_METRICS_PORT=9901" in operations
    assert "EnvironmentFile=/opt/Mobiup/ops/prometheus/unihub-retail-network.env" in imports
    assert "WORKER_METRICS_HOST=127.0.0.1" not in imports
    assert "WORKER_METRICS_HOST=0.0.0.0" not in imports
    assert "WORKER_METRICS_PORT=9902" in imports
