from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import composition
from auth import AuthClaims
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from routers.store_pnl import (
    can_access_store_pnl,
    get_service,
    pnl_permissions,
    require_store_pnl_owner,
    router,
    validate_company,
)
from repositories.store_pnl import StorePnlRepository


def claims(email: str, groups: list[str] | None = None) -> AuthClaims:
    return AuthClaims("subject-1", email, "owner", groups or [], "issuer", "audience", 0, 1, {})


def request(path: str) -> Request:
    value = Request({"type": "http", "method": "GET", "path": path, "headers": []})
    value.scope["route"] = SimpleNamespace(path=path)
    return value


def test_store_pnl_requires_management_and_dedicated_group(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORE_PNL_ACCESS_GROUPS", "pnl-owner")
    assert can_access_store_pnl(claims("owner@example.invalid", ["unihub-manager", "PNL-OWNER"]))
    assert not can_access_store_pnl(claims("owner@example.invalid", ["unihub-manager"]))
    assert not can_access_store_pnl(claims("owner@example.invalid", ["pnl-owner"]))
    for group in ("unihub-admin", "unihub-hr", "authentik Admins", "hub-service"):
        assert not can_access_store_pnl(claims("owner@example.invalid", [group]))


def test_store_pnl_dependency_audits_without_sensitive_claims(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("STORE_PNL_ACCESS_GROUPS", "pnl-owner")
    allowed = claims("owner@example.invalid", ["unihub-manager", "pnl-owner"])
    with caplog.at_level("INFO", logger="permissions"):
        assert require_store_pnl_owner(request("/api/store-pnl/months"), allowed) is allowed
        with pytest.raises(HTTPException) as exc_info:
            require_store_pnl_owner(request("/api/store-pnl/overview"), claims("other@example.invalid", ["unihub-manager"]))
    assert exc_info.value.status_code == 403
    assert "resource=store_pnl subject=subject-1 route=/api/store-pnl/months" in caplog.text
    assert "decision=denied resource=store_pnl" in caplog.text
    assert "owner@example.invalid" not in caplog.text
    assert "pnl-owner" not in caplog.text


@pytest.mark.asyncio
async def test_pnl_permissions_is_quiet_capability_endpoint(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("STORE_PNL_ACCESS_GROUPS", "pnl-owner")
    with caplog.at_level("INFO", logger="permissions"):
        assert await pnl_permissions(claims("owner@example.invalid", ["unihub-manager", "pnl-owner"])) == {"can_view": True}
        assert await pnl_permissions(claims("owner@example.invalid", ["unihub-manager"])) == {"can_view": False}
    assert "privileged_access" not in caplog.text


def test_store_pnl_data_routes_keep_owner_dependency() -> None:
    protected = {
        "/api/store-pnl/months",
        "/api/store-pnl/stores",
        "/api/store-pnl/annual",
        "/api/store-pnl/overview",
    }
    for route in router.routes:
        if isinstance(route, APIRoute) and route.path in protected:
            assert any(dependency.call is require_store_pnl_owner for dependency in route.dependant.dependencies)


def test_store_pnl_company_filter_is_closed_to_known_values() -> None:
    validate_company(None)
    validate_company("Mobicell")
    validate_company("Mobiup")
    with pytest.raises(HTTPException) as exc_info:
        validate_company("Other")
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_store_pnl_service_uses_the_canonical_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = object()
    monkeypatch.setattr(composition, "get_pool", AsyncMock(return_value=pool))

    service = await get_service()

    assert isinstance(service.repository, StorePnlRepository)
    assert service.repository.pool is pool
