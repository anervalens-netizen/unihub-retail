from __future__ import annotations

from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from auth import AuthClaims
from config import ConfigError, validate_required_env_vars
from privileged_access import (
    DEPRECATED_GRILE_EMAILS_ENV,
    DEPRECATED_PNL_OWNER_EMAILS_ENV,
    DEPRECATED_TARGET_EMAILS_ENV,
    DEPRECATED_VITE_PNL_OWNER_EMAILS_ENV,
    GRILE_FINALIZER_GROUPS_ENV,
    GRILE_TARGET_SYNC_GROUPS_ENV,
    STORE_PNL_ACCESS_GROUPS_ENV,
    TARGET_FINALIZER_GROUPS_ENV,
    configured_groups,
    has_configured_group,
    parse_group_list,
)
from routers.grile import (
    can_grile_admin,
    can_grile_target_sync,
    require_grile_admin,
    require_grile_target_sync,
)
from routers.store_pnl import can_access_store_pnl
from routers.target_calculator import can_finalize_targets, require_target_owner


def _claims(groups: list[str], email: str = "owner@example.invalid") -> AuthClaims:
    return AuthClaims("subject-1", email, "owner", groups, "test", "test", 0, 1, {})


def _request(path: str) -> Request:
    request = Request({"type": "http", "method": "POST", "path": path, "headers": []})
    request.scope["route"] = SimpleNamespace(path=path)
    return request


@pytest.mark.parametrize("raw, expected", [
    ("target", frozenset({"target"})),
    (" target,GRILE ,target ", frozenset({"target", "grile"})),
    (None, frozenset()),
    ("", frozenset()),
])
def test_parse_group_list_valid_and_missing(raw: str | None, expected: frozenset[str]) -> None:
    assert parse_group_list(raw, TARGET_FINALIZER_GROUPS_ENV) == expected


@pytest.mark.parametrize("raw", ["a,,b", "mail@example.invalid", "a\tb", "a\nb", "a" * 129])
def test_parse_group_list_rejects_invalid_complete_policy(raw: str) -> None:
    with pytest.raises(ValueError, match=TARGET_FINALIZER_GROUPS_ENV):
        parse_group_list(raw, TARGET_FINALIZER_GROUPS_ENV)


def test_invalid_policy_is_not_partially_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TARGET_FINALIZER_GROUPS_ENV, "allowed,,bad")
    assert configured_groups(TARGET_FINALIZER_GROUPS_ENV) == frozenset()
    assert has_configured_group(["allowed"], TARGET_FINALIZER_GROUPS_ENV) is False


def test_dedicated_groups_are_isolated_and_broad_groups_do_not_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TARGET_FINALIZER_GROUPS_ENV, "unihub-target-finalizer")
    monkeypatch.setenv(GRILE_FINALIZER_GROUPS_ENV, "unihub-grile-admin")
    monkeypatch.setenv(GRILE_TARGET_SYNC_GROUPS_ENV, "unihub-grile-target-sync")
    monkeypatch.setenv(STORE_PNL_ACCESS_GROUPS_ENV, "unihub-pnl-owner")
    assert can_finalize_targets(_claims(["UNIHUB-TARGET-FINALIZER"])) is True
    assert can_grile_admin(_claims(["UNIHUB-GRILE-ADMIN"])) is True
    assert can_grile_target_sync(_claims(["UNIHUB-GRILE-TARGET-SYNC"])) is True
    assert can_grile_target_sync(_claims(["unihub-grile-admin"])) is False
    assert can_grile_admin(_claims(["unihub-target-finalizer"])) is False
    assert can_finalize_targets(_claims(["unihub-grile-admin"])) is False
    for group in ("unihub-admin", "authentik Admins", "unihub-manager", "hub-service"):
        assert can_finalize_targets(_claims([group])) is False
        assert can_grile_admin(_claims([group])) is False
        assert can_grile_target_sync(_claims([group])) is False
    assert can_finalize_targets(_claims([], "historical@example.invalid")) is False
    assert can_access_store_pnl(_claims(["unihub-pnl-owner"])) is False
    assert can_finalize_targets(_claims(["unihub-pnl-owner"])) is False
    assert can_grile_admin(_claims(["unihub-pnl-owner"])) is False


def test_privileged_dependencies_audit_allowed_and_denied_without_email_or_groups(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv(TARGET_FINALIZER_GROUPS_ENV, "target-role")
    monkeypatch.setenv(GRILE_FINALIZER_GROUPS_ENV, "grile-role")
    monkeypatch.setenv(GRILE_TARGET_SYNC_GROUPS_ENV, "grile-sync-role")
    with caplog.at_level("INFO", logger="permissions"):
        assert require_target_owner(_request("/api/target-calculator/scenarios/calculate"), _claims(["target-role"])) .sub == "subject-1"
        assert require_grile_admin(_request("/api/grile/monthly/run"), _claims(["grile-role"])) .sub == "subject-1"
        assert require_grile_target_sync(_request("/api/grile/agent-targets/sync"), _claims(["grile-sync-role"])).sub == "subject-1"
        with pytest.raises(HTTPException) as exc_info:
            require_target_owner(_request("/api/target-calculator/scenarios/finalize"), _claims(["unihub-admin"]))
    assert exc_info.value.status_code == 403
    assert "decision=allowed resource=target_calculator_finalization subject=subject-1 route=/api/target-calculator/scenarios/calculate" in caplog.text
    assert "decision=denied resource=target_calculator_finalization" in caplog.text
    assert "owner@example.invalid" not in caplog.text
    assert "target-role" not in caplog.text


def _set_production_base(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    visits = tmp_path / "visits.db"
    visits.touch()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.setenv("VISITS_DB_PATH", str(visits))
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", "synthetic-hmac-key-for-production-tests-abcdefghijklmnopqrstuvwxyz")
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.invalid/oidc")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example.invalid/oidc/jwks")
    monkeypatch.setenv("OIDC_AUDIENCE", "test-audience")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    monkeypatch.setenv("RATE_LIMIT_CLIENT_IP_HEADER", "none")
    monkeypatch.setenv("RATE_LIMIT_KEY_HMAC_SECRET", "r" * 43)
    monkeypatch.setenv("RATE_LIMIT_FAILURE_MODE", "closed")
    monkeypatch.setenv("RATE_LIMIT_VALKEY_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("OIDC_CLIENT_ID", "test-audience")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "synthetic-client-secret")
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    monkeypatch.setenv("SESSION_PUBLIC_ORIGIN", "https://retail.example.invalid")
    monkeypatch.setenv("SESSION_VALKEY_URL", "redis://localhost:6379/14")
    monkeypatch.delenv(DEPRECATED_TARGET_EMAILS_ENV, raising=False)
    monkeypatch.delenv(DEPRECATED_GRILE_EMAILS_ENV, raising=False)
    monkeypatch.delenv(DEPRECATED_PNL_OWNER_EMAILS_ENV, raising=False)
    monkeypatch.delenv(DEPRECATED_VITE_PNL_OWNER_EMAILS_ENV, raising=False)


def test_production_requires_valid_groups_and_rejects_deprecated_emails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_production_base(monkeypatch, tmp_path)
    monkeypatch.setenv(TARGET_FINALIZER_GROUPS_ENV, "target-role")
    monkeypatch.setenv(GRILE_FINALIZER_GROUPS_ENV, "grile-role")
    monkeypatch.setenv(GRILE_TARGET_SYNC_GROUPS_ENV, "grile-sync-role")
    monkeypatch.setenv(STORE_PNL_ACCESS_GROUPS_ENV, "pnl-role")
    validate_required_env_vars()
    monkeypatch.delenv(TARGET_FINALIZER_GROUPS_ENV)
    with pytest.raises(ConfigError, match=TARGET_FINALIZER_GROUPS_ENV):
        validate_required_env_vars()
    monkeypatch.setenv(TARGET_FINALIZER_GROUPS_ENV, "target-role")
    monkeypatch.delenv(GRILE_FINALIZER_GROUPS_ENV)
    with pytest.raises(ConfigError, match=GRILE_FINALIZER_GROUPS_ENV):
        validate_required_env_vars()
    monkeypatch.setenv(GRILE_FINALIZER_GROUPS_ENV, "grile-role")
    monkeypatch.delenv(GRILE_TARGET_SYNC_GROUPS_ENV)
    with pytest.raises(ConfigError, match=GRILE_TARGET_SYNC_GROUPS_ENV):
        validate_required_env_vars()
    monkeypatch.setenv(GRILE_TARGET_SYNC_GROUPS_ENV, "grile-sync-role")
    monkeypatch.delenv(STORE_PNL_ACCESS_GROUPS_ENV)
    with pytest.raises(ConfigError, match=STORE_PNL_ACCESS_GROUPS_ENV):
        validate_required_env_vars()
    monkeypatch.setenv(STORE_PNL_ACCESS_GROUPS_ENV, "pnl-role")
    monkeypatch.setenv(TARGET_FINALIZER_GROUPS_ENV, "email@example.invalid")
    with pytest.raises(ConfigError, match=TARGET_FINALIZER_GROUPS_ENV):
        validate_required_env_vars()
    monkeypatch.setenv(TARGET_FINALIZER_GROUPS_ENV, "target-role")
    monkeypatch.setenv(DEPRECATED_TARGET_EMAILS_ENV, "legacy@example.invalid")
    with pytest.raises(ConfigError, match=DEPRECATED_TARGET_EMAILS_ENV):
        validate_required_env_vars()
    monkeypatch.delenv(DEPRECATED_TARGET_EMAILS_ENV)
    monkeypatch.setenv(DEPRECATED_GRILE_EMAILS_ENV, "legacy@example.invalid")
    with pytest.raises(ConfigError, match=DEPRECATED_GRILE_EMAILS_ENV):
        validate_required_env_vars()
    monkeypatch.delenv(DEPRECATED_GRILE_EMAILS_ENV)
    monkeypatch.setenv(DEPRECATED_PNL_OWNER_EMAILS_ENV, "legacy@example.invalid")
    with pytest.raises(ConfigError, match=DEPRECATED_PNL_OWNER_EMAILS_ENV):
        validate_required_env_vars()
    monkeypatch.delenv(DEPRECATED_PNL_OWNER_EMAILS_ENV)
    monkeypatch.setenv(DEPRECATED_VITE_PNL_OWNER_EMAILS_ENV, "legacy@example.invalid")
    with pytest.raises(ConfigError, match=DEPRECATED_VITE_PNL_OWNER_EMAILS_ENV):
        validate_required_env_vars()


def test_development_missing_groups_starts_but_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    for name in (
        "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "SESSION_ENCRYPTION_KEY",
        "SESSION_PUBLIC_ORIGIN", "SESSION_VALKEY_URL", "SESSION_TTL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(TARGET_FINALIZER_GROUPS_ENV, raising=False)
    monkeypatch.delenv(GRILE_FINALIZER_GROUPS_ENV, raising=False)
    monkeypatch.delenv(GRILE_TARGET_SYNC_GROUPS_ENV, raising=False)
    monkeypatch.delenv(STORE_PNL_ACCESS_GROUPS_ENV, raising=False)
    validate_required_env_vars()
    assert can_finalize_targets(_claims([])) is False
    assert can_grile_admin(_claims([])) is False
    assert can_grile_target_sync(_claims([])) is False
    assert can_access_store_pnl(_claims(["unihub-manager"])) is False


def test_static_gate_removes_email_authorization_from_routers_and_example() -> None:
    root = Path(__file__).resolve().parents[2]
    files = [
        root / "backend/routers/target_calculator.py",
        root / "backend/routers/grile.py",
        root / "backend/routers/store_pnl.py",
        root / "src/App.tsx",
        root / "src/api/storePnl.ts",
        root / "src/auth/permissions.ts",
        root / "src/auth/permissions.test.ts",
        root / "src/auth/pnlAccess.ts",
        root / "src/auth/usePnlCapability.ts",
        root / "src/components/Management.tsx",
        root / "src/components/DesktopSidebar.tsx",
        root / "src/components/MainLayout.tsx",
        root / ".env.example",
    ]
    forbidden = ("DEFAULT_FINALIZER_EMAILS", "DEFAULT_GRILE_ADMINS", "TARGET_CALCULATOR_FINALIZER_EMAILS", "GRILE_FINALIZER_EMAILS", "PNL_OWNER_EMAILS", "VITE_PNL_OWNER_EMAILS", "@gmail.com")
    for path in files:
        content = path.read_text()
        assert not any(value in content for value in forbidden), path
        assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", content), path
