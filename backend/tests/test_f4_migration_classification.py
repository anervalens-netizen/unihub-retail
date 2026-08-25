from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from db.migration_runner import (
    ALLOWED_EXECUTION_CLASSES,
    MAINTENANCE_WINDOW_AUTHORIZATION_ENV,
    MAINTENANCE_WINDOW_EXECUTION_CLASS,
    ONLINE_EXECUTION_MODE,
    TRANSACTIONAL_EXECUTION_MODE,
    MigrationError,
    MigrationManifest,
    load_migration_manifest,
)


def _payload(
    *,
    execution_modes: dict[str, str] | None = None,
    execution_classes: dict[str, str] | None = None,
) -> dict[str, object]:
    migrations = {
        "001_first.sql": "b" * 64,
        "002_second.sql": "c" * 64,
    }
    payload: dict[str, object] = {
        "version": 1,
        "baseline": {
            "file": "schema_v2.sql",
            "sha256": "a" * 64,
            "incorporated_through": "001_first.sql",
        },
        "migrations": migrations,
    }
    if execution_modes is not None:
        payload["execution_modes"] = execution_modes
    if execution_classes is not None:
        payload["execution_classes"] = execution_classes
    return payload


def _write_manifest(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_legacy_manifest_infers_class_from_existing_execution_mode(
    tmp_path: Path,
) -> None:
    path = _write_manifest(
        tmp_path,
        _payload(execution_modes={"002_second.sql": ONLINE_EXECUTION_MODE}),
    )

    manifest = load_migration_manifest(path)

    assert manifest.execution_classes == {}
    assert (
        manifest.execution_classes.get(
            "001_first.sql", manifest.execution_mode("001_first.sql")
        )
        == TRANSACTIONAL_EXECUTION_MODE
    )
    assert (
        manifest.execution_classes.get(
            "002_second.sql", manifest.execution_mode("002_second.sql")
        )
        == ONLINE_EXECUTION_MODE
    )


@pytest.mark.parametrize(
    "execution_classes",
    [
        {"001_first.sql": TRANSACTIONAL_EXECUTION_MODE},
        {
            "001_first.sql": TRANSACTIONAL_EXECUTION_MODE,
            "002_second.sql": "sometimes",
        },
        {
            "001_first.sql": TRANSACTIONAL_EXECUTION_MODE,
            "999_unknown.sql": TRANSACTIONAL_EXECUTION_MODE,
        },
    ],
)
def test_explicit_execution_classification_is_exhaustive_and_closed(
    tmp_path: Path,
    execution_classes: dict[str, str],
) -> None:
    path = _write_manifest(
        tmp_path,
        _payload(execution_classes=execution_classes),
    )

    with pytest.raises(MigrationError, match="manifest is invalid"):
        load_migration_manifest(path)


def test_online_classification_must_match_online_execution_mode(
    tmp_path: Path,
) -> None:
    mismatched = _write_manifest(
        tmp_path,
        _payload(
            execution_classes={
                "001_first.sql": TRANSACTIONAL_EXECUTION_MODE,
                "002_second.sql": ONLINE_EXECUTION_MODE,
            }
        ),
    )
    with pytest.raises(MigrationError, match="manifest is invalid"):
        load_migration_manifest(mismatched)

    matched = _write_manifest(
        tmp_path,
        _payload(
            execution_modes={"002_second.sql": ONLINE_EXECUTION_MODE},
            execution_classes={
                "001_first.sql": TRANSACTIONAL_EXECUTION_MODE,
                "002_second.sql": ONLINE_EXECUTION_MODE,
            },
        ),
    )
    manifest = load_migration_manifest(matched)
    assert manifest.execution_classes["002_second.sql"] == ONLINE_EXECUTION_MODE


def test_current_manifest_classifies_every_migration_explicitly() -> None:
    manifest = load_migration_manifest()

    assert set(manifest.execution_classes) == set(manifest.checksums)
    assert set(manifest.execution_classes.values()) <= ALLOWED_EXECUTION_CLASSES


@pytest.mark.asyncio
async def test_maintenance_window_migration_requires_exact_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    migration = tmp_path / "070_maintenance.sql"
    migration.write_text("SELECT 1;", encoding="utf-8")
    checksum = runner._sha256(migration)
    manifest = MigrationManifest(
        "a" * 64,
        migration.name,
        {migration.name: checksum},
        execution_classes={migration.name: MAINTENANCE_WINDOW_EXECUTION_CLASS},
    )
    calls: list[dict[str, Any]] = []

    async def fake_apply(_connection: object, **kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(runner, "get_migrations_dir", lambda: tmp_path)
    monkeypatch.setattr(runner, "_apply_transactional_migration", fake_apply)

    for unauthorized in (None, "0", "true"):
        if unauthorized is None:
            monkeypatch.delenv(MAINTENANCE_WINDOW_AUTHORIZATION_ENV, raising=False)
        else:
            monkeypatch.setenv(MAINTENANCE_WINDOW_AUTHORIZATION_ENV, unauthorized)
        with pytest.raises(MigrationError, match=MAINTENANCE_WINDOW_AUTHORIZATION_ENV):
            await runner._apply_pending_migrations(  # type: ignore[arg-type]
                object(),
                manifest,
                {},
                cutover_bootstrap=False,
            )

    assert calls == []


@pytest.mark.asyncio
async def test_authorized_maintenance_window_uses_transactional_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    migration = tmp_path / "070_maintenance.sql"
    migration.write_text("SELECT 1;", encoding="utf-8")
    checksum = runner._sha256(migration)
    manifest = MigrationManifest(
        "a" * 64,
        migration.name,
        {migration.name: checksum},
        execution_classes={migration.name: MAINTENANCE_WINDOW_EXECUTION_CLASS},
    )
    calls: list[dict[str, Any]] = []

    async def fake_apply(_connection: object, **kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setenv(MAINTENANCE_WINDOW_AUTHORIZATION_ENV, "1")
    monkeypatch.setattr(runner, "get_migrations_dir", lambda: tmp_path)
    monkeypatch.setattr(runner, "_apply_transactional_migration", fake_apply)

    applied = await runner._apply_pending_migrations(  # type: ignore[arg-type]
        object(),
        manifest,
        {},
        cutover_bootstrap=False,
    )

    assert applied == [migration.name]
    assert calls == [
        {
            "filename": migration.name,
            "checksum": checksum,
            "sql": "SELECT 1;",
        }
    ]
