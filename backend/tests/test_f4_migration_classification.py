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

    # Missing authorization, the legacy boolean "1", and a stale/wrong
    # filename must all be refused: authorization must equal the exact
    # migration filename, nothing else.
    unauthorized_values = (None, "", "0", "1", "true", "070_other.sql")
    for unauthorized in unauthorized_values:
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

    # Authorization must equal the exact migration filename.
    monkeypatch.setenv(MAINTENANCE_WINDOW_AUTHORIZATION_ENV, migration.name)
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


@pytest.mark.asyncio
async def test_stale_maintenance_window_authorization_does_not_authorize_other_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authorization left over from a previous maintenance migration must
    never authorize a different maintenance-window migration that happens to
    run later. A stale ``UNIHUB_MIGRATION_MAINTENANCE_WINDOW=070_first.sql``
    in ``.env.migrations`` MUST NOT authorize ``071_second.sql``."""
    import db.migration_runner as runner

    first = tmp_path / "070_first.sql"
    first.write_text("SELECT 1;", encoding="utf-8")
    second = tmp_path / "071_second.sql"
    second.write_text("SELECT 2;", encoding="utf-8")
    manifest = MigrationManifest(
        "a" * 64,
        second.name,
        {
            first.name: runner._sha256(first),
            second.name: runner._sha256(second),
        },
        execution_classes={
            first.name: MAINTENANCE_WINDOW_EXECUTION_CLASS,
            second.name: MAINTENANCE_WINDOW_EXECUTION_CLASS,
        },
    )

    applied: list[str] = []

    async def record_apply(_connection: object, **kwargs: Any) -> None:
        applied.append(str(kwargs["filename"]))

    monkeypatch.setattr(runner, "get_migrations_dir", lambda: tmp_path)
    monkeypatch.setattr(runner, "_apply_transactional_migration", record_apply)

    # 070 has already been authorized and applied; the operator forgot to
    # clear the env var before starting the second run.
    monkeypatch.setenv(MAINTENANCE_WINDOW_AUTHORIZATION_ENV, first.name)
    applied.clear()

    # The remaining migration must NOT be authorized by the stale env var.
    with pytest.raises(MigrationError, match=MAINTENANCE_WINDOW_AUTHORIZATION_ENV):
        await runner._apply_pending_migrations(  # type: ignore[arg-type]
            object(),
            manifest,
            {first.name: runner._sha256(first)},
            cutover_bootstrap=False,
        )

    assert applied == []

    # Re-running with the matching authorization for the second migration
    # must now allow it through.
    monkeypatch.setenv(MAINTENANCE_WINDOW_AUTHORIZATION_ENV, second.name)
    scheduled = await runner._apply_pending_migrations(  # type: ignore[arg-type]
        object(),
        manifest,
        {first.name: runner._sha256(first)},
        cutover_bootstrap=False,
    )
    assert scheduled == [second.name]
    assert applied == [second.name]
