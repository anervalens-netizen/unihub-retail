from __future__ import annotations

import pytest

from rate_limit_settings import load_rate_limit_settings, rate_limit_config_errors


REQUIRED = {
    "TRUSTED_PROXY_CIDRS": "172.20.0.10/32",
    "RATE_LIMIT_CLIENT_IP_HEADER": "cloudflare",
    "RATE_LIMIT_KEY_HMAC_SECRET": "s" * 43,
    "RATE_LIMIT_FAILURE_MODE": "closed",
    "RATE_LIMIT_VALKEY_URL": "redis://localhost:6379/15",
}


def _valid(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)


def test_development_allows_distributed_limiter_to_be_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("VALKEY_URL", raising=False)
    assert load_rate_limit_settings() is None


@pytest.mark.parametrize("name", list(REQUIRED))
@pytest.mark.parametrize("value", [None, ""])
def test_production_requires_each_distributed_setting(monkeypatch: pytest.MonkeyPatch, name: str, value: str | None) -> None:
    _valid(monkeypatch)
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    if name == "RATE_LIMIT_VALKEY_URL":
        monkeypatch.delenv("VALKEY_URL", raising=False)
    errors = rate_limit_config_errors(True)
    expected = "RATE_LIMIT_VALKEY_URL" if name == "RATE_LIMIT_VALKEY_URL" else name
    assert any(expected in error for error in errors)


@pytest.mark.parametrize("cidrs", ["bad", "172.20.0.1/32, bad", "172.20.0.1/32,", " 172.20.0.1/32"])
def test_cidrs_fail_closed_without_echoing_values(monkeypatch: pytest.MonkeyPatch, cidrs: str) -> None:
    _valid(monkeypatch); monkeypatch.setenv("TRUSTED_PROXY_CIDRS", cidrs)
    errors = rate_limit_config_errors(True)
    assert errors and cidrs not in " ".join(errors)


def test_cidrs_support_ipv4_ipv6_and_deduplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid(monkeypatch)
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "172.20.0.10/32,172.20.0.10/32,2001:db8::1/128")
    settings = load_rate_limit_settings()
    assert settings is not None
    assert [network.with_prefixlen for network in settings.trusted_proxy_networks] == ["172.20.0.10/32", "2001:db8::1/128"]


@pytest.mark.parametrize("mode", ["cloudflare", "x-forwarded-for"])
def test_forwarded_modes_require_trusted_network(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    _valid(monkeypatch); monkeypatch.setenv("RATE_LIMIT_CLIENT_IP_HEADER", mode); monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "")
    assert any("forwarded client IP" in error for error in rate_limit_config_errors(True))


def test_none_mode_is_valid_with_explicit_proxy_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid(monkeypatch); monkeypatch.setenv("RATE_LIMIT_CLIENT_IP_HEADER", "none")
    assert load_rate_limit_settings() is not None


@pytest.mark.parametrize("url", ["", "http://localhost", "redis://", "redis://user@localhost", "redis://localhost:0", "redis://localhost:99999", " redis://localhost", "redis://localhost?x=1"])
def test_valkey_url_is_strict_and_safe(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    _valid(monkeypatch); monkeypatch.setenv("RATE_LIMIT_VALKEY_URL", url); monkeypatch.delenv("VALKEY_URL", raising=False)
    errors = rate_limit_config_errors(True)
    assert errors and (not url or url not in " ".join(errors))


@pytest.mark.parametrize("secret", ["x" * 42, "x" * 257, "x" * 42 + " ", "x" * 42 + "\t"])
def test_secret_is_bounded_and_never_echoed(monkeypatch: pytest.MonkeyPatch, secret: str) -> None:
    _valid(monkeypatch); monkeypatch.setenv("RATE_LIMIT_KEY_HMAC_SECRET", secret)
    errors = rate_limit_config_errors(True)
    assert errors and secret not in " ".join(errors)


def test_authenticated_valkey_url_and_invalid_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid(monkeypatch)
    monkeypatch.setenv("RATE_LIMIT_VALKEY_URL", "redis://service:synthetic-password@localhost:6379/15")
    assert load_rate_limit_settings() is not None
    monkeypatch.setenv("RATE_LIMIT_CLIENT_IP_HEADER", "forwarded")
    assert any("RATE_LIMIT_CLIENT_IP_HEADER" in error for error in rate_limit_config_errors(True))
    monkeypatch.setenv("RATE_LIMIT_CLIENT_IP_HEADER", "none")
    monkeypatch.setenv("RATE_LIMIT_FAILURE_MODE", "open")
    assert any("RATE_LIMIT_FAILURE_MODE" in error for error in rate_limit_config_errors(True))


def test_loader_raises_only_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid(monkeypatch); value = "unsafe mode value"; monkeypatch.setenv("RATE_LIMIT_CLIENT_IP_HEADER", value)
    with pytest.raises(ValueError) as exc:
        load_rate_limit_settings()
    assert str(exc.value) == "Distributed rate limit configuration is invalid" and value not in str(exc.value)


@pytest.mark.parametrize("name", [
    "RATE_LIMIT_AUTH_PROXY", "RATE_LIMIT_SALES_IMPORT_UPLOAD", "RATE_LIMIT_REPORT_EXPORT",
    "RATE_LIMIT_BUSINESS_WRITE", "RATE_LIMIT_GRILE_JOB", "RATE_LIMIT_TARGET_MUTATION",
])
@pytest.mark.parametrize("value", ["0", "100001", "NaN", " 1", "1.0", "-1"])
def test_every_policy_limit_is_typed_and_bounded(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    _valid(monkeypatch); monkeypatch.setenv(name, value)
    assert any(name in error for error in rate_limit_config_errors(True))


@pytest.mark.parametrize("base", [
    "RATE_LIMIT_AUTH_PROXY", "RATE_LIMIT_SALES_IMPORT_UPLOAD", "RATE_LIMIT_REPORT_EXPORT",
    "RATE_LIMIT_BUSINESS_WRITE", "RATE_LIMIT_GRILE_JOB", "RATE_LIMIT_TARGET_MUTATION",
])
@pytest.mark.parametrize("value", ["0", "86401", "Infinity", "1.0"])
def test_every_policy_window_is_typed_and_bounded(monkeypatch: pytest.MonkeyPatch, base: str, value: str) -> None:
    _valid(monkeypatch); name = f"{base}_WINDOW_SECONDS"; monkeypatch.setenv(name, value)
    assert any(name in error for error in rate_limit_config_errors(True))


def test_policy_minimum_maximum_and_lazy_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid(monkeypatch); monkeypatch.setenv("RATE_LIMIT_AUTH_PROXY", "1"); monkeypatch.setenv("RATE_LIMIT_AUTH_PROXY_WINDOW_SECONDS", "86400")
    first = load_rate_limit_settings(); assert first and first.policies["auth_proxy"].limit == 1
    monkeypatch.setenv("RATE_LIMIT_AUTH_PROXY", "100000")
    second = load_rate_limit_settings(); assert second and second.policies["auth_proxy"].limit == 100000
