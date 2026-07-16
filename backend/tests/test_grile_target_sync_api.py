from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute, iter_route_contexts

from auth import AuthClaims
from privileged_access import GRILE_TARGET_SYNC_GROUPS_ENV
import routers.grile as grile_router


class FakeSessionRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, **_kwargs: object) -> bool:
        self.values[key] = value
        return True

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)


def claims(groups: list[str]) -> AuthClaims:
    return AuthClaims(
        sub="stable-synthetic-subject",
        email="mutable@example.invalid",
        preferred_username="synthetic-user",
        groups=groups,
        iss="https://issuer.invalid",
        aud="synthetic-audience",
        iat=1,
        exp=2,
        raw={},
    )


def request(path: str) -> Request:
    value = Request({"type": "http", "method": "POST", "path": path, "headers": []})
    value.scope["route"] = SimpleNamespace(path=path)
    return value


@pytest.mark.asyncio
async def test_regular_user_can_check_and_diff_uses_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = object()
    monkeypatch.setattr(grile_router, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(grile_router, "resolve_month", AsyncMock(return_value="2098-09"))
    enqueue_check = AsyncMock(
        return_value=SimpleNamespace(
            status="enqueued",
            run_id=3,
            job=SimpleNamespace(job_id="check-job"),
        )
    )
    enqueue_sync = AsyncMock(
        return_value=SimpleNamespace(
            status="enqueued",
            operation_id=4,
            job=SimpleNamespace(job_id="diff-job"),
            operation=None,
        )
    )
    monkeypatch.setattr(grile_router, "enqueue_grile_check", enqueue_check)
    monkeypatch.setattr(grile_router, "enqueue_grile_target_sync", enqueue_sync)
    regular = claims(["unihub-agent"])

    check_result = await grile_router.grile_run(
        month="2098-09",
        claims=regular,
        _rate_limit=None,
    )
    diff_result = await grile_router.grile_agent_targets_diff(
        body=grile_router.AgentTargetRunRequest(month="2098-09"),
        claims=regular,
        _rate_limit=None,
    )

    assert check_result["job_id"] == "check-job"
    enqueue_check.assert_awaited_once_with(
        month="2098-09",
        source="manual",
        source_snapshot_id=None,
        triggered_by_sub="stable-synthetic-subject",
    )
    assert diff_result["job_id"] == "diff-job"
    enqueue_sync.assert_awaited_once_with(
        month="2098-09",
        mode="dry_run",
        requested_by_sub="stable-synthetic-subject",
    )


@pytest.mark.asyncio
async def test_sync_requires_dedicated_group_and_persists_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GRILE_TARGET_SYNC_GROUPS_ENV, "synthetic-sync-role")
    with pytest.raises(HTTPException) as exc_info:
        grile_router.require_grile_target_sync(
            request("/api/grile/agent-targets/sync"),
            claims(["unihub-admin"]),
        )
    assert exc_info.value.status_code == 403

    authorized = claims(["synthetic-sync-role"])
    assert grile_router.require_grile_target_sync(
        request("/api/grile/agent-targets/sync"), authorized
    ) is authorized
    enqueue = AsyncMock(
        return_value=SimpleNamespace(
            status="enqueued",
            operation_id=7,
            job=SimpleNamespace(job_id="sync-job"),
            operation=None,
        )
    )
    monkeypatch.setattr(grile_router, "enqueue_grile_target_sync", enqueue)

    result = await grile_router.grile_agent_targets_sync(
        body=grile_router.AgentTargetRunRequest(month="2098-10"),
        claims=authorized,
        _rate_limit=None,
    )

    assert result["job_id"] == "sync-job"
    enqueue.assert_awaited_once_with(
        month="2098-10",
        mode="sync",
        requested_by_sub="stable-synthetic-subject",
    )


def test_sync_route_is_post_and_has_privileged_dependency() -> None:
    from main import app

    route = next(
        item.original_route
        for item in iter_route_contexts(app.routes)
        if isinstance(item.original_route, APIRoute)
        and item.path == "/api/grile/agent-targets/sync"
    )
    assert route.methods == {"POST"}
    assert route.dependant is not None
    dependencies = {item.call for item in route.dependant.dependencies}
    assert grile_router.require_grile_target_sync in dependencies


def test_public_operation_payload_never_exposes_authorization_identity() -> None:
    payload = grile_router._target_operation_payload(
        {
            "id": 1,
            "run_month": "2098-11",
            "status": "completed",
            "requested_by_sub": "must-not-be-exposed",
            "diff": {},
        }
    )
    assert "requested_by_sub" not in payload


@pytest.mark.anyio
async def test_sync_browser_session_requires_csrf_on_the_real_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rate_limits
    import session_auth
    from main import app
    from session_auth import SessionSettings

    key = Fernet.generate_key().decode("ascii")
    session_id = "s" * 43
    csrf = "synthetic-csrf"
    redis = FakeSessionRedis()
    cipher = Fernet(key.encode("ascii"))
    settings = SessionSettings(
        "redis://localhost:6379/14",
        key,
        "retail",
        "synthetic-client-secret",
        "https://retail.example.invalid",
        "https://auth.example.invalid/application/o/unihub-retail",
        3600,
        True,
    )
    record = {
        "sub": "stable-synthetic-subject",
        "email": "mutable@example.invalid",
        "preferred_username": "synthetic-user",
        "groups": ["synthetic-sync-role"],
        "iss": "https://issuer.invalid",
        "aud": "synthetic-audience",
        "iat": int(time.time()) - 1,
        "exp": int(time.time()) + 600,
        "refresh_token": "synthetic-refresh-token",
        "csrf": csrf,
    }
    redis.values[session_auth.SESSION_PREFIX + session_id] = session_auth._pack(
        cipher, record
    )
    monkeypatch.setattr(session_auth, "_settings", settings)
    monkeypatch.setattr(session_auth, "_redis", redis)
    monkeypatch.setattr(session_auth, "_cipher", cipher)
    monkeypatch.setattr(session_auth, "_http", object())
    monkeypatch.setattr(rate_limits, "enforce_rate_limit", AsyncMock())
    monkeypatch.setenv(GRILE_TARGET_SYNC_GROUPS_ENV, "synthetic-sync-role")
    enqueue = AsyncMock(
        return_value=SimpleNamespace(
            status="enqueued",
            operation_id=8,
            job=SimpleNamespace(job_id="sync-job"),
            operation=None,
        )
    )
    monkeypatch.setattr(grile_router, "enqueue_grile_target_sync", enqueue)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://retail.example.invalid",
        cookies={session_auth.COOKIE_NAME: session_id},
    ) as client:
        denied = await client.post(
            "/api/grile/agent-targets/sync",
            json={"month": "2098-10"},
        )
        allowed = await client.post(
            "/api/grile/agent-targets/sync",
            json={"month": "2098-10"},
            headers={"X-CSRF-Token": csrf},
        )

    assert denied.status_code == 403
    assert denied.json() == {"detail": "CSRF validation failed"}
    assert allowed.status_code == 200
    assert allowed.json()["job_id"] == "sync-job"
    enqueue.assert_awaited_once_with(
        month="2098-10",
        mode="sync",
        requested_by_sub="stable-synthetic-subject",
    )
