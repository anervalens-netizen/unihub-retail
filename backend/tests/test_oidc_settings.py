from __future__ import annotations

import pytest

from oidc_settings import load_oidc_verifier_settings, oidc_config_errors


def _valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.invalid/oidc/")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example.invalid/oidc/jwks/")
    monkeypatch.setenv("OIDC_AUDIENCE", "test-audience")


@pytest.mark.parametrize("name", ["OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE"])
@pytest.mark.parametrize("value", [None, ""])
def test_production_requires_missing_and_empty_settings(monkeypatch: pytest.MonkeyPatch, name: str, value: str | None) -> None:
    _valid(monkeypatch)
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    errors = oidc_config_errors(True)
    assert any(name in error for error in errors)


def test_development_all_absent_or_empty_is_allowed_but_partial_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE"):
        monkeypatch.setenv(name, "")
    assert load_oidc_verifier_settings() is None
    monkeypatch.setenv("OIDC_AUDIENCE", "partial")
    assert oidc_config_errors(False)


@pytest.mark.parametrize("issuer,jwks", [
    ("https://issuer.example.invalid\t/x", "https://issuer.example.invalid/jwks"),
    ("https://issuer.example.invalid\r", "https://issuer.example.invalid/jwks"),
    ("https://issuer.example.invalid:0", "https://issuer.example.invalid/jwks"),
    ("https://issuer.example.invalid:65536", "https://issuer.example.invalid/jwks"),
    ("https://issuer.example.invalid:wat", "https://issuer.example.invalid/jwks"),
    ("https://user@issuer.example.invalid", "https://issuer.example.invalid/jwks"),
    ("https://issuer.example.invalid?x=1", "https://issuer.example.invalid/jwks"),
    ("https://issuer.example.invalid#x", "https://issuer.example.invalid/jwks"),
    ("https://issuer.example.invalid", "https://other.example.invalid/jwks"),
])
def test_urls_fail_closed_without_echoing_values(monkeypatch: pytest.MonkeyPatch, issuer: str, jwks: str) -> None:
    monkeypatch.setenv("OIDC_ISSUER", issuer)
    monkeypatch.setenv("OIDC_JWKS_URL", jwks)
    monkeypatch.setenv("OIDC_AUDIENCE", "test-audience")
    errors = oidc_config_errors(True)
    assert errors and issuer not in " ".join(errors) and jwks not in " ".join(errors)


def test_urls_preserve_trailing_slash_and_compare_effective_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid(monkeypatch)
    monkeypatch.setenv("OIDC_ISSUER", "https://ISSUER.example.invalid:443/a/")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example.invalid/b/")
    settings = load_oidc_verifier_settings()
    assert settings and settings.issuer.endswith("/a/")


@pytest.mark.parametrize("name,value", [
    ("JWKS_CACHE_TTL", "59"), ("JWKS_CACHE_TTL", "NaN"), ("JWKS_MAX_STALE_SECONDS", "Infinity"),
    ("JWKS_FETCH_TIMEOUT_SECONDS", "0.4"), ("OIDC_CLOCK_SKEW_SECONDS", "-1"),
    ("JWKS_UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS", "0"), ("JWKS_REFRESH_FAILURE_RETRY_SECONDS", "61"),
])
def test_numeric_ranges_are_typed_and_fail_closed(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    _valid(monkeypatch); monkeypatch.setenv(name, value)
    assert any(name in error for error in oidc_config_errors(True))


def test_numeric_boundaries_and_hub_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid(monkeypatch)
    monkeypatch.setenv("OIDC_CLOCK_SKEW_SECONDS", "0")
    monkeypatch.setenv("JWKS_UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS", "1")
    monkeypatch.setenv("JWKS_REFRESH_FAILURE_RETRY_SECONDS", "60")
    settings = load_oidc_verifier_settings()
    assert settings and settings.clock_skew_seconds == 0 and settings.refresh_failure_retry_seconds == 60
