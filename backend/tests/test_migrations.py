"""Tests for numbered SQL migrations runner."""
from __future__ import annotations

from pathlib import Path
import json

import pytest

from db.connection import list_migration_files
from db.migration_runner import (
    MigrationError,
    MigrationManifest,
    _validate_applied,
    load_migration_manifest,
    verify_migration_files,
)


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


def test_checked_in_manifest_matches_frozen_baseline_and_all_migrations() -> None:
    manifest = load_migration_manifest()
    verify_migration_files(manifest)
    assert manifest.incorporated_through == "022_store_pnl_site_links.sql"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"version": 2, "baseline": {}, "migrations": {}},
        {
            "version": 1,
            "baseline": {
                "file": "wrong.sql",
                "sha256": "a" * 64,
                "incorporated_through": "001_one.sql",
            },
            "migrations": {"001_one.sql": "b" * 64},
        },
    ],
)
def test_invalid_manifest_is_rejected(tmp_path: Path, payload: dict[str, object]) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MigrationError, match="manifest is invalid"):
        load_migration_manifest(path)


def test_manifest_parse_errors_are_generic(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(MigrationError, match="manifest is invalid"):
        load_migration_manifest(path)


def test_applied_checksum_validation_is_fail_closed() -> None:
    manifest = MigrationManifest("a" * 64, "001_one.sql", {"001_one.sql": "b" * 64})
    _validate_applied({"001_one.sql": None}, manifest, allow_missing_checksums=True)
    with pytest.raises(MigrationError, match="checksum mismatch"):
        _validate_applied({"001_one.sql": None}, manifest, allow_missing_checksums=False)
    with pytest.raises(MigrationError, match="checksum mismatch"):
        _validate_applied({"001_one.sql": "c" * 64}, manifest, allow_missing_checksums=False)
    with pytest.raises(MigrationError, match="absent from the manifest"):
        _validate_applied({"999_unknown.sql": "d" * 64}, manifest, allow_missing_checksums=False)


def test_file_or_baseline_tampering_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import db.migration_runner as runner

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    migration = migrations / "001_one.sql"
    migration.write_text("SELECT 1;", encoding="utf-8")
    baseline = tmp_path / "schema_v2.sql"
    baseline.write_text("SELECT 2;", encoding="utf-8")
    manifest = MigrationManifest(
        "0" * 64,
        migration.name,
        {migration.name: "1" * 64},
    )
    monkeypatch.setattr(runner, "get_migrations_dir", lambda: migrations)
    monkeypatch.setattr(runner, "get_schema_path", lambda: baseline)
    with pytest.raises(MigrationError, match="immutable manifest"):
        verify_migration_files(manifest)

    manifest = MigrationManifest(
        runner._sha256(baseline),
        migration.name,
        {migration.name: runner._sha256(migration)},
    )
    verify_migration_files(manifest)
    baseline.write_text("SELECT 3;", encoding="utf-8")
    with pytest.raises(MigrationError, match="Frozen schema baseline"):
        verify_migration_files(manifest)
