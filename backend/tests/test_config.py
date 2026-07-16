"""Tests for config validation (fail-fast la startup)."""
from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import dotenv_values

from config import (
    ConfigError,
    _is_production,
    get_visits_db_path,
    get_visits_images_dir,
    get_visits_read_source,
    validate_required_env_vars,
    visits_shadow_compare_enabled,
)
from session_auth import load_session_settings


@pytest.fixture(autouse=True)
def _clear_oidc_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE", "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET", "SESSION_ENCRYPTION_KEY", "SESSION_PUBLIC_ORIGIN",
        "SESSION_VALKEY_URL", "SESSION_TTL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def _set_privileged_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_CALCULATOR_FINALIZER_GROUPS", "target-role")
    monkeypatch.setenv("GRILE_FINALIZER_GROUPS", "grile-role")
    monkeypatch.setenv("GRILE_TARGET_SYNC_GROUPS", "grile-sync-role")
    monkeypatch.setenv("STORE_PNL_ACCESS_GROUPS", "pnl-role")
    monkeypatch.delenv("TARGET_CALCULATOR_FINALIZER_EMAILS", raising=False)
    monkeypatch.delenv("GRILE_FINALIZER_EMAILS", raising=False)
    monkeypatch.delenv("PNL_OWNER_EMAILS", raising=False)
    monkeypatch.delenv("VITE_PNL_OWNER_EMAILS", raising=False)


def _set_oidc_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.invalid/oidc")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example.invalid/oidc/jwks")
    monkeypatch.setenv("OIDC_AUDIENCE", "test-audience")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    monkeypatch.setenv("RATE_LIMIT_CLIENT_IP_HEADER", "none")
    monkeypatch.setenv("RATE_LIMIT_KEY_HMAC_SECRET", "r" * 43)
    monkeypatch.setenv("RATE_LIMIT_FAILURE_MODE", "closed")
    monkeypatch.setenv("RATE_LIMIT_VALKEY_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("OIDC_CLIENT_ID", "test-audience")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "synthetic-client-secret")
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    monkeypatch.setenv("SESSION_PUBLIC_ORIGIN", "https://retail.example.invalid")
    monkeypatch.setenv("SESSION_VALKEY_URL", "redis://localhost:6379/14")


def test_is_production_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "production")
    assert _is_production() is True

    monkeypatch.setenv("UNIHUB_ENV", " PRODUCTION ")
    assert _is_production() is True

    monkeypatch.setenv("UNIHUB_ENV", "development")
    assert _is_production() is False

    monkeypatch.delenv("UNIHUB_ENV", raising=False)
    assert _is_production() is False


def test_config_passes_with_valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("UNIHUB_ENV", "development")
    validate_required_env_vars()  # nu ridică


def test_env_example_keeps_optional_browser_session_disabled_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = dotenv_values(Path(__file__).resolve().parents[2] / ".env.example")
    for name, value in values.items():
        monkeypatch.setenv(name, value or "")

    validate_required_env_vars()
    assert load_session_settings() is None


def test_salary_person_id_key_required_in_production(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("VISITS_DB_PATH", str(tmp_path / "visits.db"))
    (tmp_path / "visits.db").touch()
    _set_privileged_groups(monkeypatch)
    _set_oidc_settings(monkeypatch)
    monkeypatch.delenv("SALARY_PERSON_ID_HMAC_KEY", raising=False)
    with pytest.raises(ConfigError, match="SALARY_PERSON_ID_HMAC_KEY"):
        validate_required_env_vars()
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", "")
    with pytest.raises(ConfigError, match="SALARY_PERSON_ID_HMAC_KEY"):
        validate_required_env_vars()


def test_salary_person_id_key_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("VISITS_DB_PATH", str(tmp_path / "visits.db"))
    (tmp_path / "visits.db").touch()
    _set_privileged_groups(monkeypatch)
    _set_oidc_settings(monkeypatch)
    for value in ("short", " " + "x" * 48, "x" * 48 + "\n"):
        monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", value)
        with pytest.raises(ConfigError, match="SALARY_PERSON_ID_HMAC_KEY"):
            validate_required_env_vars()
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", "x" * 48)
    validate_required_env_vars()


@pytest.mark.parametrize("value", [None, ""])
def test_development_allows_absent_or_empty_salary_person_id_key(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("UNIHUB_ENV", "development")
    if value is None:
        monkeypatch.delenv("SALARY_PERSON_ID_HMAC_KEY", raising=False)
    else:
        monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", value)
    validate_required_env_vars()


def test_development_rejects_nonempty_invalid_salary_person_id_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", "   ")
    with pytest.raises(ConfigError, match="SALARY_PERSON_ID_HMAC_KEY"):
        validate_required_env_vars()


def test_development_allows_valid_salary_person_id_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", "x" * 48)
    validate_required_env_vars()


def test_env_example_empty_salary_key_loads_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", "")
    validate_required_env_vars()


def test_config_rejects_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        validate_required_env_vars()


def test_config_rejects_bad_database_url_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@host/db")
    with pytest.raises(ConfigError, match="schemă invalidă"):
        validate_required_env_vars()


def test_config_ignores_visits_db_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.setenv("VISITS_DB_PATH", "/nonexistent/path.db")
    validate_required_env_vars()  # în dev, visits path nu e validat


def test_visits_paths_use_env_with_repo_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VISITS_DB_PATH", raising=False)
    monkeypatch.delenv("VISITS_IMAGES_DIR", raising=False)
    assert get_visits_db_path().name == "visits.db"
    assert get_visits_images_dir().name == "images"

    db_path = tmp_path / "visits-custom.db"
    images_path = tmp_path / "images-custom"
    monkeypatch.setenv("VISITS_DB_PATH", str(db_path))
    monkeypatch.setenv("VISITS_IMAGES_DIR", str(images_path))
    assert get_visits_db_path() == db_path
    assert get_visits_images_dir() == images_path


def test_config_rejects_sqlite_visits_source_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("RETAIL_VISITS_READ_SOURCE", "sqlite")
    _set_privileged_groups(monkeypatch)
    with pytest.raises(ConfigError, match="trebuie sa fie postgres dupa cutover"):
        validate_required_env_vars()


def test_visit_source_flags_are_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETAIL_VISITS_READ_SOURCE", " POSTGRES ")
    monkeypatch.setenv("RETAIL_VISITS_SHADOW_COMPARE_ENABLED", "YeS")
    assert get_visits_read_source() == "postgres"
    assert visits_shadow_compare_enabled() is True


def test_visit_source_defaults_to_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RETAIL_VISITS_READ_SOURCE", raising=False)
    assert get_visits_read_source() == "postgres"


def test_config_rejects_unknown_visit_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.setenv("RETAIL_VISITS_READ_SOURCE", "mysql")
    with pytest.raises(ConfigError, match="RETAIL_VISITS_READ_SOURCE"):
        validate_required_env_vars()


def test_postgres_primary_without_shadow_does_not_require_sqlite_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("RETAIL_VISITS_READ_SOURCE", "postgres")
    monkeypatch.setenv("RETAIL_VISITS_SHADOW_COMPARE_ENABLED", "false")
    monkeypatch.delenv("VISITS_DB_PATH", raising=False)
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", "x" * 48)
    monkeypatch.setenv("HUB_INTERNAL_SECRET", "h" * 32)
    _set_privileged_groups(monkeypatch)
    _set_oidc_settings(monkeypatch)
    validate_required_env_vars()


def test_production_rejects_visits_shadow_compare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("RETAIL_VISITS_READ_SOURCE", "postgres")
    monkeypatch.setenv("RETAIL_VISITS_SHADOW_COMPARE_ENABLED", "true")
    _set_privileged_groups(monkeypatch)
    with pytest.raises(ConfigError, match="trebuie sa fie false dupa cutover"):
        validate_required_env_vars()


def test_config_accumulates_all_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        validate_required_env_vars()
    assert "DATABASE_URL" in str(exc_info.value)
