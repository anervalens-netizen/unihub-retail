from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import scripts.retire_legacy_database_login as retirement


class _LegacyConnection:
    def __init__(self, *, can_login: bool = True, sessions: int = 0, members: int = 0):
        self.can_login = can_login
        self.sessions = sessions
        self.members = members
        self.closed = False

    async def execute(self, sql: str) -> str:
        if "ALTER ROLE unihub_runtime NOLOGIN" in sql:
            self.can_login = False
        elif "ALTER ROLE unihub_runtime LOGIN" in sql:
            self.can_login = True
        return "OK"

    async def fetchrow(self, _sql: str, _role: str) -> dict[str, bool]:
        return {
            "rolcanlogin": self.can_login,
            "rolsuper": False,
            "rolcreatedb": False,
            "rolcreaterole": False,
            "rolbypassrls": False,
            "rolreplication": False,
        }

    async def fetchval(self, sql: str, *args: object) -> int | bool:
        if "pg_stat_activity" in sql:
            return self.sessions
        if "pg_auth_members" in sql:
            return self.members
        if "rolcanlogin = $2" in sql:
            return self.can_login is bool(args[1])
        raise AssertionError(sql)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_retirement_fences_only_fixed_legacy_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _LegacyConnection()
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(retirement, "connect_database_url", connect)

    checks = await retirement.set_legacy_login_state("postgresql://owner", allow_login=False)

    assert checks == {
        "legacy_login_allowed": False,
        "no_active_sessions": True,
        "no_member_roles": True,
    }
    assert not connection.can_login and connection.closed
    connect.assert_awaited_once_with(
        "postgresql://owner",
        application_name="unihub-retail-legacy-login-cutover",
    )


@pytest.mark.asyncio
async def test_retirement_refuses_active_sessions_or_member_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for connection, message in (
        (_LegacyConnection(sessions=1), "active sessions"),
        (_LegacyConnection(members=1), "member roles"),
    ):
        monkeypatch.setattr(
            retirement, "connect_database_url", AsyncMock(return_value=connection)
        )
        with pytest.raises(RuntimeError, match=message):
            await retirement.set_legacy_login_state(
                "postgresql://owner", allow_login=False
            )
        assert connection.can_login and connection.closed


@pytest.mark.asyncio
async def test_retirement_rollback_requires_nologin_prestate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _LegacyConnection(can_login=False)
    monkeypatch.setattr(
        retirement, "connect_database_url", AsyncMock(return_value=connection)
    )

    result = await retirement.set_legacy_login_state(
        "postgresql://owner", allow_login=True
    )

    assert result["legacy_login_allowed"] is True
    assert connection.can_login
