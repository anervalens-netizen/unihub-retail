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
    replication: bool = False
    direct_memberships: tuple[tuple[str, bool, bool], ...] = (
        ("unihub_business_write", True, False),
        ("unihub_web_read", True, False),
    )
    effective_memberships: frozenset[str] = frozenset(
        {"unihub_web_read", "unihub_business_write"}
    )
    direct_authority: bool = False

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
            "rolreplication": self.replication,
        }

    async def fetch(self, sql: str) -> list[dict[str, object]]:
        if "pg_auth_members" in sql:
            return [
                {
                    "rolname": role_name,
                    "inherit_option": inherit_option,
                    "set_option": set_option,
                }
                for role_name, inherit_option, set_option in self.direct_memberships
            ]
        return [{"rolname": role_name} for role_name in self.effective_memberships]

    async def fetchval(self, _sql: str, _principal: str) -> bool:
        return self.direct_authority


@pytest.mark.asyncio
async def test_web_authority_requires_exact_login_and_only_its_groups() -> None:
    await connection_module.verify_database_connection_authority(
        _AuthorityConnection(), "web"  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_authority_rejects_cross_authority_membership() -> None:
    connection = _AuthorityConnection(
        direct_memberships=(
            ("unihub_business_write", True, False),
            ("unihub_sales_import", True, False),
            ("unihub_web_read", True, False),
        ),
        effective_memberships=frozenset(
            {"unihub_web_read", "unihub_business_write", "unihub_sales_import"}
        ),
    )

    with pytest.raises(RuntimeError, match="direct memberships"):
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
    with pytest.raises(RuntimeError, match="flags do not match"):
        await connection_module.verify_database_connection_authority(
            _AuthorityConnection(inherits=False), "web"  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_authority_rejects_arbitrary_transitive_membership() -> None:
    with pytest.raises(RuntimeError, match="unexpected direct or transitive"):
        await connection_module.verify_database_connection_authority(
            _AuthorityConnection(
                effective_memberships=frozenset(
                    {"unihub_web_read", "unihub_business_write", "pg_read_all_data"}
                )
            ),
            "web",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_authority_rejects_direct_acl_or_object_ownership() -> None:
    with pytest.raises(RuntimeError, match="direct grants, default privileges, or ownership"):
        await connection_module.verify_database_connection_authority(
            _AuthorityConnection(direct_authority=True),
            "web",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_authority_rejects_membership_option_drift() -> None:
    with pytest.raises(RuntimeError, match="memberships or options"):
        await connection_module.verify_database_connection_authority(
            _AuthorityConnection(
                direct_memberships=(
                    ("unihub_business_write", True, False),
                    ("unihub_web_read", True, True),
                )
            ),
            "web",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_migration_authority_requires_noinherit_and_schema_owner_membership() -> None:
    await connection_module.verify_database_connection_authority(
        _AuthorityConnection(
            current_user="unihub_migration_runner",
            session_user="unihub_migration_runner",
            inherits=False,
            direct_memberships=(
                ("unihub_migrate", False, False),
                ("unihub_schema_owner", False, True),
            ),
            effective_memberships=frozenset(
                {"unihub_migrate", "unihub_schema_owner"}
            ),
        ),
        "migrate",  # type: ignore[arg-type]
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
        "postgresql://unihub_test:test@127.0.0.1:55432/unihub_test",  # pragma: allowlist secret
    )
    monkeypatch.setenv("UNIHUB_TEST_DATABASE", "1")
    monkeypatch.setenv(DB_PROCESS_AUTHORITY_ENV, "web")

    assert await connection_module.init_db_pool() is created_pool
    verify.assert_awaited_once_with(created_pool)


@pytest.mark.asyncio
async def test_one_shot_connection_uses_bounded_server_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(connection_module.asyncpg, "connect", connect)
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "9000")
    monkeypatch.setenv("DB_LOCK_TIMEOUT_MS", "800")
    monkeypatch.setenv("DB_IDLE_TRANSACTION_TIMEOUT_MS", "7000")

    assert await connection_module.connect_database_url(
        "postgresql://test", application_name="p1a-test"
    ) is connection
    connect.assert_awaited_once_with(
        "postgresql://test",
        command_timeout=9.0,
        server_settings={
            "application_name": "p1a-test",
            "statement_timeout": "9000",
            "lock_timeout": "800",
            "idle_in_transaction_session_timeout": "7000",
        },
    )


def test_explicit_process_authority_must_match_runtime_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DB_PROCESS_AUTHORITY_ENV, "sales_import")

    with pytest.raises(ConfigError, match="nu corespunde procesului web"):
        load_runtime_config("web")


def test_production_runtime_requires_explicit_database_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.delenv(DB_PROCESS_AUTHORITY_ENV, raising=False)

    with pytest.raises(ConfigError, match="obligatoriu în producție"):
        load_runtime_config("web")


@pytest.mark.asyncio
async def test_production_connection_check_is_not_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.delenv(DB_PROCESS_AUTHORITY_ENV, raising=False)

    with pytest.raises(RuntimeError, match="explicit process authority"):
        await connection_module.verify_database_connection_authority(  # type: ignore[arg-type]
            _AuthorityConnection()
        )


def test_versioned_units_declare_exclusive_process_authorities() -> None:
    root = Path(__file__).resolve().parents[2]
    expected = {
        root / "ops/systemd/unihub-backend.service": "web",
        root / "unihub-worker.service": "operations",
        root / "ops/systemd/unihub-import-worker.service": "sales_import",
        root / "ops/systemd/unihub-grile-worker.service": "operations",
        root / "ops/systemd/unihub-export-worker.service": "operations",
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

    shadow_script = (root / "backend/scripts/shadow_store_pnl.py").read_text(
        encoding="utf-8"
    )
    assert 'load_dotenv(REPO_DIR / ".env.worker")' in shadow_script
    assert shadow_script.index('load_dotenv(REPO_DIR / ".env.worker")') < shadow_script.index(
        "from db.connection import"
    )
    assert "connect_database_url(" in shadow_script
    assert 'verify_database_connection_authority(connection, "operations")' in shadow_script
