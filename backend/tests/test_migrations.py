"""Tests for numbered SQL migrations runner."""
from __future__ import annotations

from pathlib import Path

import pytest

from db.connection import list_migration_files


def test_list_migration_files_empty(tmp_path: Path) -> None:
    assert list_migration_files(tmp_path) == []


def test_list_migration_files_ignores_non_sql(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# docs")
    (tmp_path / "001_first.sql").write_text("SELECT 1;")
    files = list_migration_files(tmp_path)
    assert [p.name for p in files] == ["001_first.sql"]


def test_list_migration_files_orders_numerically(tmp_path: Path) -> None:
    # Dacă sortarea ar fi lexicografică fără prefix de 3 cifre, 10 ar veni
    # înaintea lui 2. Prefix-ul strict 3-digit garantează ordinea corectă.
    for name in ["010_ten.sql", "002_two.sql", "001_one.sql", "099_last.sql"]:
        (tmp_path / name).write_text("SELECT 1;")
    files = list_migration_files(tmp_path)
    assert [p.name for p in files] == [
        "001_one.sql",
        "002_two.sql",
        "010_ten.sql",
        "099_last.sql",
    ]


def test_list_migration_files_rejects_bad_format(tmp_path: Path) -> None:
    (tmp_path / "001_ok.sql").write_text("SELECT 1;")
    (tmp_path / "bad_migration.sql").write_text("SELECT 1;")  # fără prefix numeric
    with pytest.raises(RuntimeError, match="Migrations invalide"):
        list_migration_files(tmp_path)


def test_list_migration_files_rejects_two_digit_prefix(tmp_path: Path) -> None:
    (tmp_path / "01_short.sql").write_text("SELECT 1;")  # doar 2 cifre
    with pytest.raises(RuntimeError, match="Migrations invalide"):
        list_migration_files(tmp_path)


def test_list_migration_files_rejects_uppercase(tmp_path: Path) -> None:
    # Impunem lowercase ca să evităm inconsistențe cross-OS (macOS case-insensitive).
    (tmp_path / "001_BadName.sql").write_text("SELECT 1;")
    with pytest.raises(RuntimeError, match="Migrations invalide"):
        list_migration_files(tmp_path)


def test_list_migration_files_missing_dir_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert list_migration_files(missing) == []


def test_migrations_dir_default_exists() -> None:
    # Directorul real trebuie să existe în repo (chiar și gol).
    from db.connection import get_migrations_dir

    assert get_migrations_dir().is_dir()
