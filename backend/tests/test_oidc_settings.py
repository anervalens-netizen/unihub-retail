from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from oidc_settings import (
    _number,
    _url,
    hub_internal_secret_errors,
    load_oidc_verifier_settings,
    normalized_origin,
    oidc_config_errors,
)


def _valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.invalid/oidc/")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example.invalid/oidc/jwks/")
    monkeypatch.setenv("OIDC_AUDIENCE", "test-audience")


@pytest.mark.parametrize("name", ["OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE"])
@pytest.mark.parametrize("value", [None, ""])
def test_production_requires_every_missing_and_empty_setting(monkeypatch: pytest.MonkeyPatch, name: str, value: str | None) -> None:
    _valid(monkeypatch)
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    errors = oidc_config_errors(True)
    assert any(name in error for error in errors)


def test_development_all_empty_is_allowed_but_partial_and_invalid_numeric_are_not(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE"):
        monkeypatch.setenv(name, "")
    assert load_oidc_verifier_settings() is None
    monkeypatch.setenv("OIDC_AUDIENCE", "partial")
    assert oidc_config_errors(False)
    monkeypatch.setenv("JWKS_CACHE_TTL", "NaN")
    assert oidc_config_errors(False)


@pytest.mark.parametrize(
    "raw,production,accepted",
    [
        ("https://issuer.example.invalid/a/", True, True),
        ("http://localhost:8080/a/", False, True),
        ("http://127.0.0.1:8080/a/", False, True),
        ("http://[::1]:8080/a/", False, True),
        ("http://localhost/a", True, False),
        ("http://example.invalid/a", False, False),
        ("ftp://issuer.example.invalid/a", False, False),
        ("https://issuer.example.invalid/a?x=1", True, False),
        ("https://issuer.example.invalid/a#x", True, False),
        ("https://user:pass@issuer.example.invalid/a", True, False),
        (" https://issuer.example.invalid/a", True, False),
        ("https://issuer.example.invalid/a\t", True, False),
        ("https://issuer.example.invalid/a\r", True, False),
        ("https://issuer.example.invalid:0/a", True, False),
        ("https://issuer.example.invalid:65536/a", True, False),
        ("https://issuer.example.invalid:wat/a", True, False),
    ],
)
def test_url_validation_is_fail_closed_and_preserves_accepted_raw_value(raw: str, production: bool, accepted: bool) -> None:
    value, error = _url(raw, "OIDC_ISSUER", production)
    assert (value == raw and error is None) if accepted else (value is None and error == "OIDC_ISSUER is invalid" or error == "OIDC_ISSUER must use an allowed scheme")


@pytest.mark.parametrize(
    "issuer,jwks,valid",
    [
        ("https://ISSUER.example.invalid:443/a/", "https://issuer.example.invalid/b/", True),
        ("https://issuer.example.invalid/a", "https://issuer.example.invalid:444/b", False),
        ("https://issuer.example.invalid/a", "http://issuer.example.invalid/b", False),
    ],
)
def test_origin_comparison_and_trailing_slash(monkeypatch: pytest.MonkeyPatch, issuer: str, jwks: str, valid: bool) -> None:
    _valid(monkeypatch)
    monkeypatch.setenv("OIDC_ISSUER", issuer)
    monkeypatch.setenv("OIDC_JWKS_URL", jwks)
    settings = load_oidc_verifier_settings() if valid else None
    if valid:
        assert settings is not None and settings.issuer == issuer and settings.jwks_url == jwks
    else:
        assert oidc_config_errors(True)


def test_normalized_origin_rejects_invalid_port() -> None:
    assert normalized_origin(urlsplit("https://ISSUER.example.invalid/a")) == ("https", "issuer.example.invalid", 443)
    with pytest.raises(ValueError, match="invalid port"):
        normalized_origin(urlsplit("https://issuer.example.invalid:wat/a"))
    with pytest.raises(ValueError, match="invalid port"):
        normalized_origin(urlsplit("https://issuer.example.invalid:0/a"))


def test_urlsplit_error_audience_and_loader_error_are_generic(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _url("https://[::1", "OIDC_ISSUER", True) == (None, "OIDC_ISSUER is invalid")
    _valid(monkeypatch)
    monkeypatch.setenv("OIDC_AUDIENCE", "contains space")
    errors = oidc_config_errors(True)
    assert errors == ["OIDC_AUDIENCE is invalid"]
    monkeypatch.setenv("UNIHUB_ENV", "production")
    with pytest.raises(ValueError, match="OIDC verifier configuration is invalid"):
        load_oidc_verifier_settings()


def test_origin_parser_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    import oidc_settings
    _valid(monkeypatch)
    monkeypatch.setattr(oidc_settings, "normalized_origin", lambda _parsed: (_ for _ in ()).throw(ValueError("port")))
    assert oidc_config_errors(True) == ["OIDC_ISSUER or OIDC_JWKS_URL is invalid"]


@pytest.mark.parametrize(
    "name,value,integer,low,high,expected",
    [
        ("N", None, False, 1, 2, 1.5), ("N", "", False, 1, 2, 1.5),
        ("N", "1", False, 1, 2, 1.0), ("N", "2", False, 1, 2, 2.0),
        ("N", "1", True, 1, 2, 1.0), ("N", "2", True, 1, 2, 2.0),
    ],
)
def test_number_defaults_and_all_boundaries(monkeypatch: pytest.MonkeyPatch, name: str, value: str | None, integer: bool, low: float, high: float, expected: float) -> None:
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)
    assert _number(name, 1.5, low, high, integer) == (expected, None)


@pytest.mark.parametrize("value", ["0", "3", "wat", "NaN", "Infinity", "-Infinity", " 1", "1\t"])
def test_number_rejects_range_nonfinite_and_whitespace(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("N", value)
    parsed, error = _number("N", 1.5, 1, 2)
    assert parsed is None and error is not None and value not in error


@pytest.mark.parametrize(
    "name,value",
    [
        ("JWKS_CACHE_TTL", "59"), ("JWKS_CACHE_TTL", "86401"),
        ("JWKS_MAX_STALE_SECONDS", "59"), ("JWKS_MAX_STALE_SECONDS", "604801"),
        ("JWKS_FETCH_TIMEOUT_SECONDS", "0.4"), ("JWKS_FETCH_TIMEOUT_SECONDS", "30.1"),
        ("OIDC_CLOCK_SKEW_SECONDS", "-1"), ("OIDC_CLOCK_SKEW_SECONDS", "121"),
        ("JWKS_UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS", "0"), ("JWKS_UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS", "61"),
        ("JWKS_REFRESH_FAILURE_RETRY_SECONDS", "0"), ("JWKS_REFRESH_FAILURE_RETRY_SECONDS", "61"),
    ],
)
def test_every_numeric_setting_fails_closed_outside_limits(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    _valid(monkeypatch)
    monkeypatch.setenv(name, value)
    errors = oidc_config_errors(True)
    assert any(name in error for error in errors) and value not in " ".join(errors)


def test_numeric_relationship_and_all_supported_extremes(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid(monkeypatch)
    monkeypatch.setenv("JWKS_CACHE_TTL", "60")
    monkeypatch.setenv("JWKS_MAX_STALE_SECONDS", "60")
    monkeypatch.setenv("JWKS_FETCH_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("OIDC_CLOCK_SKEW_SECONDS", "0")
    monkeypatch.setenv("JWKS_UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS", "1")
    monkeypatch.setenv("JWKS_REFRESH_FAILURE_RETRY_SECONDS", "60")
    settings = load_oidc_verifier_settings()
    assert settings is not None and settings.clock_skew_seconds == 0 and settings.unknown_kid_refresh_cooldown_seconds == 1
    monkeypatch.setenv("JWKS_CACHE_TTL", "61")
    assert any("at least" in error for error in oidc_config_errors(True))


@pytest.mark.parametrize("secret,valid", [(None, True), ("", True), ("x" * 32, True), ("x" * 256, True), ("x" * 31, False), ("x" * 257, False), ("x" * 31 + " ", False), ("x" * 31 + "\t", False)])
def test_hub_internal_secret_contract(monkeypatch: pytest.MonkeyPatch, secret: str | None, valid: bool) -> None:
    if secret is None:
        monkeypatch.delenv("HUB_INTERNAL_SECRET", raising=False)
    else:
        monkeypatch.setenv("HUB_INTERNAL_SECRET", secret)
    errors = hub_internal_secret_errors()
    assert (errors == []) is valid
    if errors:
        assert secret is not None and secret not in " ".join(errors)
