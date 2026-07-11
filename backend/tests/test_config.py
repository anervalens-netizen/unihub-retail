"""Tests for config validation (fail-fast la startup)."""
from __future__ import annotations

from pathlib import Path

import pytest

from config import ConfigError, get_visits_db_path, get_visits_images_dir, validate_required_env_vars, _is_production


def _set_privileged_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_CALCULATOR_FINALIZER_GROUPS", "target-role")
    monkeypatch.setenv("GRILE_FINALIZER_GROUPS", "grile-role")
    monkeypatch.setenv("STORE_PNL_ACCESS_GROUPS", "pnl-role")
    monkeypatch.delenv("TARGET_CALCULATOR_FINALIZER_EMAILS", raising=False)
    monkeypatch.delenv("GRILE_FINALIZER_EMAILS", raising=False)
    monkeypatch.delenv("PNL_OWNER_EMAILS", raising=False)
    monkeypatch.delenv("VITE_PNL_OWNER_EMAILS", raising=False)


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


def test_config_requires_visits_db_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("VISITS_DB_PATH", "/nonexistent/path.db")
    _set_privileged_groups(monkeypatch)
    with pytest.raises(ConfigError, match="VISITS_DB_PATH"):
        validate_required_env_vars()


def test_config_accumulates_all_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        validate_required_env_vars()
    assert "DATABASE_URL" in str(exc_info.value)


def test_config_rejects_empty_visits_db_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("VISITS_DB_PATH", "   ")
    _set_privileged_groups(monkeypatch)
    with pytest.raises(ConfigError, match="VISITS_DB_PATH"):
        validate_required_env_vars()


def test_config_rejects_directory_as_visits_db_in_production(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    dir_path = tmp_path / "a_directory"
    dir_path.mkdir()
    monkeypatch.setenv("VISITS_DB_PATH", str(dir_path))
    _set_privileged_groups(monkeypatch)
    with pytest.raises(ConfigError, match="VISITS_DB_PATH"):
        validate_required_env_vars()
