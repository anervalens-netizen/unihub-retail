from __future__ import annotations

import ipaddress

from starlette.requests import Request

from client_ip import resolve_client_ip
from rate_limit_settings import PolicySettings, RateLimitSettings


def settings(mode: str, cidrs: tuple[str, ...] = ("172.20.0.10/32",)) -> RateLimitSettings:
    return RateLimitSettings(
        tuple(ipaddress.ip_network(value) for value in cidrs), mode,  # type: ignore[arg-type]
        "redis://localhost", "s" * 43, "closed", {"test": PolicySettings(1, 60)},
    )


def request(peer: str | None, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers or [], "scheme": "http", "server": ("test", 80)}
    if peer is not None:
        scope["client"] = (peer, 1234)
    return Request(scope)


def test_untrusted_peer_ignores_spoofed_headers() -> None:
    result = resolve_client_ip(request("198.51.100.7", [(b"cf-connecting-ip", b"203.0.113.8"), (b"x-forwarded-for", b"203.0.113.9")]), settings("cloudflare"))
    assert result.address == "198.51.100.7" and result.mode == "peer" and result.outcome == "fallback"


def test_none_mode_always_uses_canonical_peer() -> None:
    assert resolve_client_ip(request("2001:0db8::1"), settings("none")).address == "2001:db8::1"


def test_missing_and_invalid_peer_are_unknown() -> None:
    assert resolve_client_ip(request(None), settings("none")).address == "unknown"
    assert resolve_client_ip(request("bad"), settings("none")).outcome == "invalid"


def test_cloudflare_valid_ipv4_and_ipv6() -> None:
    for raw, expected in ((b"203.0.113.8", "203.0.113.8"), (b"2001:0db8::1", "2001:db8::1")):
        result = resolve_client_ip(request("172.20.0.10", [(b"cf-connecting-ip", raw)]), settings("cloudflare"))
        assert result.address == expected and result.outcome == "accepted"


def test_cloudflare_invalid_or_multiple_falls_back() -> None:
    for raw in (b"", b"bad", b"203.0.113.8, 203.0.113.9", b" 203.0.113.8", b"203.0.113.8 203.0.113.9"):
        result = resolve_client_ip(request("172.20.0.10", [(b"cf-connecting-ip", raw)]), settings("cloudflare"))
        assert result.address == "172.20.0.10" and result.outcome == "invalid"


def test_xff_walks_right_to_left_over_trusted_hops() -> None:
    cfg = settings("x-forwarded-for", ("172.20.0.0/24", "10.0.0.0/8"))
    result = resolve_client_ip(request("172.20.0.10", [(b"x-forwarded-for", b"203.0.113.8,10.1.2.3")]), cfg)
    assert result.address == "203.0.113.8" and result.outcome == "accepted"


def test_xff_malformed_all_trusted_and_hop_bound() -> None:
    cfg = settings("x-forwarded-for", ("172.20.0.0/24", "10.0.0.0/8"))
    for raw in (b"bad", b"203.0.113.8, bad", b"203.0.113.8, 10.1.2.3", b""):
        result = resolve_client_ip(request("172.20.0.10", [(b"x-forwarded-for", raw)]), cfg)
        assert result.address == "172.20.0.10" and result.outcome == "invalid"
    all_trusted = resolve_client_ip(request("172.20.0.10", [(b"x-forwarded-for", b"10.1.2.3")]), cfg)
    assert all_trusted.address == "172.20.0.10" and all_trusted.outcome == "fallback"
    too_many = b",".join([b"203.0.113.8"] * 17)
    assert resolve_client_ip(request("172.20.0.10", [(b"x-forwarded-for", too_many)]), cfg).outcome == "invalid"
