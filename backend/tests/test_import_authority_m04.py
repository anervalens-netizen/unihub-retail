from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/import_historical.py"
IMPORTER = ROOT / "services/importer.py"
MIGRATION = ROOT / "db/migrations/038_retire_replace_month_snapshot.sql"


def test_m04_has_no_productive_legacy_call_site() -> None:
    assert "replace_month_snapshot" not in SCRIPT.read_text(encoding="utf-8")
    assert "replace_month_snapshot" not in IMPORTER.read_text(encoding="utf-8")


def test_historical_script_is_offline_and_has_no_apply_surface() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "asyncpg" not in source
    assert "DATABASE_URL" not in source
    assert "reserve_snapshot" not in source
    assert "--apply" not in source
    assert "create_pool" not in source


def test_m04_migration_revokes_acl_and_drops_function_defensively() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "revoke execute on function public.replace_month_snapshot(text) from public" in sql
    assert "revoke execute on function public.replace_month_snapshot(text) from unihub_runtime" in sql
    assert "drop function if exists public.replace_month_snapshot(text)" in sql
