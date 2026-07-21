from __future__ import annotations

import pytest

from valkey_url import apply_valkey_endpoint_overrides


def test_endpoint_override_preserves_encoded_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_VALKEY_PORT", "6380")
    monkeypatch.setenv("SESSION_VALKEY_DATABASE", "1")

    result = apply_valkey_endpoint_overrides(
        "redis://service:p%40ssword@127.0.0.1:6379/7",
        "SESSION_VALKEY",
    )

    assert result == "redis://service:p%40ssword@127.0.0.1:6380/1"


@pytest.mark.parametrize(
    ("port", "database"),
    [("0", "0"), ("65536", "0"), ("invalid", "0"), ("6380", "16")],
)
def test_endpoint_override_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
    database: str,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_VALKEY_PORT", port)
    monkeypatch.setenv("RATE_LIMIT_VALKEY_DATABASE", database)

    with pytest.raises(ValueError, match="override is invalid"):
        apply_valkey_endpoint_overrides("redis://127.0.0.1:6379/0", "RATE_LIMIT_VALKEY")
