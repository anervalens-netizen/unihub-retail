"""Tests for WebSocket subprotocol auth extraction in routers/ai.py."""
from __future__ import annotations

from types import SimpleNamespace

from routers.ai import _extract_bearer_subprotocol


def _make_ws(protocol_header: str | None) -> SimpleNamespace:
    """Minimal stub mimicking starlette WebSocket.headers (case-insensitive dict-like)."""
    headers = {}
    if protocol_header is not None:
        headers["sec-websocket-protocol"] = protocol_header
    return SimpleNamespace(headers=headers)


def test_extract_bearer_returns_token_and_protocol() -> None:
    ws = _make_ws("bearer, eyJhbGciOi.token.sig")
    token, protocol = _extract_bearer_subprotocol(ws)
    assert token == "eyJhbGciOi.token.sig"
    assert protocol == "bearer"


def test_extract_bearer_handles_no_whitespace() -> None:
    ws = _make_ws("bearer,abc.def.ghi")
    token, protocol = _extract_bearer_subprotocol(ws)
    assert token == "abc.def.ghi"
    assert protocol == "bearer"


def test_extract_bearer_no_header_returns_nones() -> None:
    ws = _make_ws(None)
    token, protocol = _extract_bearer_subprotocol(ws)
    assert token is None
    assert protocol is None


def test_extract_bearer_wrong_scheme_returns_nones() -> None:
    ws = _make_ws("basic, some_token")
    token, protocol = _extract_bearer_subprotocol(ws)
    assert token is None
    assert protocol is None


def test_extract_bearer_single_proto_returns_nones() -> None:
    """Protocol singur (doar 'bearer' fără token) = refuz."""
    ws = _make_ws("bearer")
    token, protocol = _extract_bearer_subprotocol(ws)
    assert token is None
    assert protocol is None
