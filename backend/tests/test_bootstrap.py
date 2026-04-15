from __future__ import annotations

import os

import pytest

from bootstrap import (
    assert_no_default_passwords_in_production,
    get_core_user_bootstrap_status,
    get_default_core_credentials,
    is_production_env,
    reset_default_core_users,
    should_reset_default_users_on_boot,
)
from services.auth_service import hash_password


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


def test_is_production_env_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNIHUB_ENV", raising=False)
    assert is_production_env() is False


def test_is_production_env_detects_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "production")
    assert is_production_env() is True


class _PasswordCheckConn:
    """Minimal conn stub for password check: fetchrow returns hash per username."""

    def __init__(self, hashes: dict[str, str]) -> None:
        self._hashes = hashes

    async def fetchrow(self, query: str, username: str) -> dict[str, str] | None:
        if username in self._hashes:
            return {"password_hash": self._hashes[username]}
        return None


@pytest.mark.anyio
async def test_password_check_noop_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "development")
    conn = _PasswordCheckConn({"admin": hash_password("9999"), "management": hash_password("9999")})
    # Ar trebui să nu ridice nimic
    await assert_no_default_passwords_in_production(conn)


@pytest.mark.anyio
async def test_password_check_raises_in_production_when_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.delenv("UNIHUB_ALLOW_DEFAULT_PASSWORDS", raising=False)
    conn = _PasswordCheckConn({"admin": hash_password("9999"), "management": hash_password("9999")})

    with pytest.raises(RuntimeError, match="parola default"):
        await assert_no_default_passwords_in_production(conn)


@pytest.mark.anyio
async def test_password_check_passes_when_password_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "production")
    conn = _PasswordCheckConn({
        "admin": hash_password("custom_strong_password_42"),
        "management": hash_password("another_custom_pw_7"),
    })
    await assert_no_default_passwords_in_production(conn)


@pytest.mark.anyio
async def test_password_check_escape_hatch_allows_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("UNIHUB_ALLOW_DEFAULT_PASSWORDS", "1")
    conn = _PasswordCheckConn({"admin": hash_password("9999"), "management": hash_password("9999")})
    # Nu trebuie să ridice — doar să logheze warning
    await assert_no_default_passwords_in_production(conn)
