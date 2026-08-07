from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os


PROMETHEUS_DOCKER_GATEWAY_ENV = "PROMETHEUS_DOCKER_GATEWAY"
PROMETHEUS_DOCKER_SUBNET_ENV = "PROMETHEUS_DOCKER_SUBNET"


@dataclass(frozen=True, slots=True)
class MetricsNetwork:
    gateway: ipaddress.IPv4Address
    subnet: ipaddress.IPv4Network


def _parse_metrics_network(*, required: bool) -> MetricsNetwork | None:
    raw_gateway = os.getenv(PROMETHEUS_DOCKER_GATEWAY_ENV, "").strip()
    raw_subnet = os.getenv(PROMETHEUS_DOCKER_SUBNET_ENV, "").strip()
    if not raw_gateway and not raw_subnet and not required:
        return None
    if not raw_gateway or not raw_subnet:
        raise ValueError("Prometheus Docker gateway and subnet must be configured together")
    try:
        gateway = ipaddress.ip_address(raw_gateway)
        subnet = ipaddress.ip_network(raw_subnet, strict=True)
    except ValueError as exc:
        raise ValueError("Prometheus Docker gateway/subnet is invalid") from exc
    if not isinstance(gateway, ipaddress.IPv4Address) or not isinstance(
        subnet, ipaddress.IPv4Network
    ):
        raise ValueError("Prometheus Docker gateway/subnet must use IPv4")
    if (
        gateway.is_unspecified
        or gateway.is_loopback
        or gateway.is_multicast
        or not gateway.is_private
        or gateway not in subnet
    ):
        raise ValueError("Prometheus Docker gateway must be a private address inside its subnet")
    return MetricsNetwork(gateway=gateway, subnet=subnet)


def metrics_network_config_errors(*, required: bool) -> list[str]:
    try:
        _parse_metrics_network(required=required)
    except ValueError as exc:
        return [str(exc)]
    return []


def required_metrics_network() -> MetricsNetwork:
    network = _parse_metrics_network(required=True)
    if network is None:  # pragma: no cover - required=True cannot return None
        raise ValueError("Prometheus Docker network is required")
    return network


def metrics_peer_allowed(peer: str | None) -> bool:
    try:
        network = _parse_metrics_network(required=False)
        address = ipaddress.ip_address(peer or "")
    except ValueError:
        return False
    return (
        network is not None
        and isinstance(address, ipaddress.IPv4Address)
        and address in network.subnet
    )
