from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import db.connection as connection_module
from config import ConfigError, DB_PROCESS_AUTHORITY_ENV, load_runtime_config


@dataclass
class _AuthorityConnection:
    current_user: str = "unihub_web"
    session_user: str = "unihub_web"
    can_login: bool = True
    superuser: bool = False
    inherits: bool = True
    can_create_db: bool = False
    can_create_role: bool = False
    bypass_rls: bool = False
    memberships: frozenset[str] = frozenset(
        {"unihub_web_read", "unihub_business_write"}
    )

    async def fetchrow(self, _sql: str) -> dict[str, object]:
        return {
            "current_user": self.current_user,
            "session_user": self.session_user,
            "rolcanlogin": self.can_login,
            "rolsuper": self.superuser,
            "rolinherit": self.inherits,
            "rolcreatedb": self.can_create_db,
            "rolcreaterole": self.can_create_role,
            "rolbypassrls": self.bypass_rls,
        }

    async def fetchval(self, _sql: str, role_name: str) -> bool:
        return role_name in self.memberships


@pytest.mark.asyncio
async def test_web_authority_requires_exact_login_and_only_its_groups() -> None:
    await connection_module.verify_database_connection_authority(
        _AuthorityConnection(), "web"  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_authority_rejects_cross_authority_membership() -> None:
    connection = _AuthorityConnection(
        memberships=frozenset(
            {
                "unihub_web_read",
                "unihub_business_write",
                "unihub_sales_import",
            }
        )
    )

    with pytest.raises(RuntimeError, match="forbidden cross-authority"):
        await connection_module.verify_database_connection_authority(
            connection, "web"  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_authority_rejects_set_role_instead_of_authenticated_principal() -> None:
    connection = _AuthorityConnection(session_user="unihub_runtime")

    with pytest.raises(RuntimeError, match="principal does not match"):
        await connection_module.verify_database_connection_authority(
            connection, "web"  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_authority_rejects_noinherit_login() -> None:
    with pytest.raises(RuntimeError, match="inheriting LOGIN role"):
        await connection_module.verify_database_connection_authority(
            _AuthorityConnection(inherits=False), "web"  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_pool_startup_checks_an_explicit_process_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_pool = MagicMock()
    create_pool = AsyncMock(return_value=created_pool)
    verify = AsyncMock()
    monkeypatch.setattr(connection_module.asyncpg, "create_pool", create_pool)
    monkeypatch.setattr(connection_module, "verify_database_pool_authority", verify)
    monkeypatch.setattr(connection_module, "pool", None)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://unihub_test:test@127.0.0.1:55432/unihub_test",
    )
    monkeypatch.setenv("UNIHUB_TEST_DATABASE", "1")
    monkeypatch.setenv(DB_PROCESS_AUTHORITY_ENV, "web")

    assert await connection_module.init_db_pool() is created_pool
    verify.assert_awaited_once_with(created_pool)


def test_explicit_process_authority_must_match_runtime_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DB_PROCESS_AUTHORITY_ENV, "sales_import")

    with pytest.raises(ConfigError, match="nu corespunde procesului web"):
        load_runtime_config("web")


def test_versioned_units_declare_exclusive_process_authorities() -> None:
    root = Path(__file__).resolve().parents[2]
    expected = {
        root / "ops/systemd/unihub-backend.service": "web",
        root / "unihub-worker.service": "operations",
        root / "ops/systemd/unihub-import-worker.service": "sales_import",
        root / "ops/systemd/unihub-retail-migrate.service": "migrate",
    }
    for path, authority in expected.items():
        source = path.read_text(encoding="utf-8")
        assert f'Environment="{DB_PROCESS_AUTHORITY_ENV}={authority}"' in source

    import_unit = (root / "ops/systemd/unihub-import-worker.service").read_text(
        encoding="utf-8"
    )
    assert "EnvironmentFile=/opt/Mobiup/unihub-retail/.env.import-worker" in import_unit
    assert ".env.worker" not in import_unit
