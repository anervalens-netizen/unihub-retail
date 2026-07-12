"""Trusted client address resolution rooted in the direct socket peer."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from starlette.requests import Request

from rate_limit_settings import RateLimitSettings


@dataclass(frozen=True, slots=True)
class ClientIPResolution:
    address: str
    mode: str
    outcome: str


def _address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _trusted(address: ipaddress.IPv4Address | ipaddress.IPv6Address, settings: RateLimitSettings) -> bool:
    return any(address.version == network.version and address in network for network in settings.trusted_proxy_networks)


def resolve_client_ip(request: Request, settings: RateLimitSettings, max_xff_hops: int = 16) -> ClientIPResolution:
    peer_raw = request.client.host if request.client else ""
    peer = _address(peer_raw)
    if peer is None:
        return ClientIPResolution("unknown", "peer", "invalid")
    peer_text = str(peer)
    mode = settings.client_ip_header_mode
    if mode == "none" or not _trusted(peer, settings):
        return ClientIPResolution(peer_text, "peer", "fallback" if mode != "none" else "accepted")

    if mode == "cloudflare":
        raw = request.headers.get("cf-connecting-ip", "")
        if not raw or raw != raw.strip() or "," in raw or any(char.isspace() for char in raw):
            return ClientIPResolution(peer_text, "cloudflare", "invalid")
        value = _address(raw)
        return ClientIPResolution(str(value), "cloudflare", "accepted") if value else ClientIPResolution(peer_text, "cloudflare", "invalid")

    raw = request.headers.get("x-forwarded-for", "")
    parts = raw.split(",") if raw else []
    if not parts or len(parts) > max_xff_hops:
        return ClientIPResolution(peer_text, "xff", "invalid")
    chain: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for part in parts:
        if not part or part != part.strip():
            return ClientIPResolution(peer_text, "xff", "invalid")
        value = _address(part)
        if value is None:
            return ClientIPResolution(peer_text, "xff", "invalid")
        chain.append(value)
    for value in reversed(chain):
        if not _trusted(value, settings):
            return ClientIPResolution(str(value), "xff", "accepted")
    return ClientIPResolution(peer_text, "xff", "fallback")
