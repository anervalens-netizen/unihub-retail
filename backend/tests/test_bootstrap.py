from __future__ import annotations

import os

import pytest

from bootstrap import (
    get_core_user_bootstrap_status,
    get_default_core_credentials,
    reset_default_core_users,
    should_reset_default_users_on_boot,
)


class DummyConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_rows = [
            {"username": "admin", "role": "admin", "is_active": True},
            {"username": "management", "role": "management", "is_active": False},
        ]

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.executed.append((query, args))
        return self.fetch_rows


def test_should_reset_default_users_on_boot_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESET_DEFAULT_USERS_ON_BOOT", raising=False)
    assert should_reset_default_users_on_boot() is False


def test_should_reset_default_users_on_boot_accepts_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESET_DEFAULT_USERS_ON_BOOT", "true")
    assert should_reset_default_users_on_boot() is True


@pytest.mark.anyio
async def test_reset_default_core_users_updates_admin_and_management() -> None:
    conn = DummyConn()

    reset_users = await reset_default_core_users(conn)

    assert len(reset_users) == 2
    assert reset_users[0]["role"] == "admin"
    assert reset_users[1]["role"] == "management"
    assert len(conn.executed) == 2


@pytest.mark.anyio
async def test_get_core_user_bootstrap_status_reports_existing_users() -> None:
    conn = DummyConn()

    status_rows = await get_core_user_bootstrap_status(conn)

    assert status_rows == [
        {"role": "admin", "username": "admin", "exists": True, "is_active": True},
        {
            "role": "management",
            "username": "management",
            "exists": True,
            "is_active": False,
        },
    ]


def test_get_default_core_credentials_honors_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "root-admin")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "1234")
    credentials = get_default_core_credentials()

    assert credentials["admin"][0] == "root-admin"
    assert credentials["admin"][1] == "1234"
