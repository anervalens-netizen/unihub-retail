"""Tests for config validation (fail-fast la startup)."""
from __future__ import annotations

import pytest

from config import ConfigError, validate_required_env_vars


def test_config_passes_with_valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("UNIHUB_ENV", "development")
    validate_required_env_vars()  # nu ridică


def test_config_rejects_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        validate_required_env_vars()


def test_config_rejects_bad_database_url_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@host/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    with pytest.raises(ConfigError, match="schemă invalidă"):
        validate_required_env_vars()


def test_config_rejects_missing_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ConfigError, match="JWT_SECRET"):
        validate_required_env_vars()


def test_config_rejects_short_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(ConfigError, match="prea scurt"):
        validate_required_env_vars()


def test_config_ignores_visits_db_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.setenv("VISITS_DB_PATH", "/nonexistent/path.db")
    validate_required_env_vars()  # în dev, visits path nu e validat


def test_config_requires_visits_db_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("VISITS_DB_PATH", "/nonexistent/path.db")
    with pytest.raises(ConfigError, match="VISITS_DB_PATH"):
        validate_required_env_vars()


def test_config_accumulates_all_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        validate_required_env_vars()
    # ambele erori trebuie raportate într-un singur ridicat
    assert "DATABASE_URL" in str(exc_info.value)
    assert "JWT_SECRET" in str(exc_info.value)
