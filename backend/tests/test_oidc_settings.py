from __future__ import annotations

import pytest

from oidc_settings import load_oidc_verifier_settings, oidc_config_errors


def _valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.invalid/oidc/")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example.invalid/oidc/jwks/")
    monkeypatch.setenv("OIDC_AUDIENCE", "test-audience")


@pytest.mark.parametrize("name", ["OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE"])
def test_production_requires_each_setting(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    _valid(monkeypatch)
    monkeypatch.delenv(name)
    errors = oidc_config_errors(True)
    assert any(name in error for error in errors)


def test_development_all_absent_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE"):
        monkeypatch.delenv(name, raising=False)
    assert load_oidc_verifier_settings() is None
    assert oidc_config_errors(False) == []


@pytest.mark.parametrize("issuer,jwks", [
    ("http://issuer.example.invalid", "http://issuer.example.invalid/jwks"),
    ("http://localhost:9999", "http://localhost:9999/jwks"),
    ("https://issuer.example.invalid?bad=1", "https://issuer.example.invalid/jwks"),
    ("https://issuer.example.invalid", "https://other.example.invalid/jwks"),
])
def test_invalid_or_unmatched_urls_are_rejected(monkeypatch: pytest.MonkeyPatch, issuer: str, jwks: str) -> None:
    monkeypatch.setenv("OIDC_ISSUER", issuer)
    monkeypatch.setenv("OIDC_JWKS_URL", jwks)
    monkeypatch.setenv("OIDC_AUDIENCE", "test-audience")
    assert oidc_config_errors(True)


def test_valid_settings_are_normalized_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid(monkeypatch)
    monkeypatch.setenv("UNIHUB_ENV", "production")
    settings = load_oidc_verifier_settings()
    assert settings is not None
    assert settings.issuer == "https://issuer.example.invalid/oidc/"
    assert settings.jwks_url == "https://issuer.example.invalid/oidc/jwks/"
    assert settings.cache_ttl_seconds == 3600
    monkeypatch.setenv("JWKS_MAX_STALE_SECONDS", "59")
    assert any("JWKS_MAX_STALE_SECONDS" in error for error in oidc_config_errors(True))
