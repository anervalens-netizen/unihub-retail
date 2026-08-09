from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import ValidationError

from auth import AuthClaims
from privileged_access import GRILE_FINALIZER_GROUPS_ENV
import routers.grile as grile_router
from services.grile_queries import GrileQueryService


def claims(groups: list[str]) -> AuthClaims:
    return AuthClaims(
        sub="stable-monthly-subject",
        email="mutable-address@example.invalid",
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


def test_live_reset_request_requires_approved_manifest() -> None:
    with pytest.raises(ValidationError, match="approved_manifest_id"):
        grile_router.MonthlyRunRequest(
            op="reset",
            month="2098-09",
            dry_run=False,
        )
    with pytest.raises(ValidationError, match="permis numai pentru reset"):
        grile_router.MonthlyRunRequest(
            op="archive",
            month="2098-09",
            approved_manifest_id=3,
        )
    request_body = grile_router.MonthlyRunRequest(
        op="reset",
        month="2098-09",
        dry_run=False,
        approved_manifest_id=3,
    )
    assert request_body.approved_manifest_id == 3


@pytest.mark.asyncio
async def test_monthly_enqueue_uses_oidc_subject_not_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueue = AsyncMock(
        return_value=SimpleNamespace(
            status="enqueued",
            operation_id=7,
            job_id="monthly-job",
            operation=None,
        )
    )
    monkeypatch.setattr(grile_router, "enqueue_grile_monthly", enqueue)

    result = await grile_router.grile_monthly_run(
        body=grile_router.MonthlyRunRequest(op="finalize", month="2098-09"),
        claims=claims(["synthetic-finalizer"]),
        _rate_limit=None,
    )

    assert result["operation_id"] == 7
    enqueue.assert_awaited_once_with(
        op="finalize",
        month="2098-09",
        dry_run=True,
        requested_by_sub="stable-monthly-subject",
        approved_manifest_id=None,
    )
    assert "mutable-address" not in repr(enqueue.await_args)


@pytest.mark.asyncio
async def test_duplicate_monthly_request_returns_persisted_operation_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueue = AsyncMock(
        return_value=SimpleNamespace(
            status="already_running",
            operation_id=8,
            job_id="grile-monthly:8",
            operation={
                "op": "finalize",
                "closing_month": "2098-08",
                "dry_run": False,
            },
        )
    )
    monkeypatch.setattr(grile_router, "enqueue_grile_monthly", enqueue)

    result = await grile_router.grile_monthly_run(
        body=grile_router.MonthlyRunRequest(op="archive", month="2098-09", dry_run=False),
        claims=claims(["synthetic-finalizer"]),
        _rate_limit=None,
    )

    assert result["op"] == "finalize"
    assert result["month"] == "2098-08"
    assert "next_month_label" not in result


@pytest.mark.asyncio
async def test_manifest_approval_persists_approver_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AsyncMock(spec=GrileQueryService)
    service.approve_monthly_manifest.return_value = {"id": 9, "status": "approved"}

    result = await grile_router.grile_monthly_manifest_approve(
        manifest_id=9,
        claims=claims(["synthetic-finalizer"]),
        _rate_limit=None,
        svc=service,
    )

    assert result == {"manifest": {"id": 9, "status": "approved"}}
    service.approve_monthly_manifest.assert_awaited_once_with(
        manifest_id=9,
        approved_by_sub="stable-monthly-subject",
    )


def test_monthly_routes_keep_privileged_group_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GRILE_FINALIZER_GROUPS_ENV, "synthetic-finalizer")
    with pytest.raises(HTTPException) as exc_info:
        grile_router.require_grile_admin(
            request("/api/grile/monthly/run"),
            claims(["unihub-admin"]),
        )
    assert exc_info.value.status_code == 403

    authorized = claims(["synthetic-finalizer"])
    assert grile_router.require_grile_admin(
        request("/api/grile/monthly/run"),
        authorized,
    ) is authorized

    routes = {
        route.path: route
        for route in grile_router.router.routes
        if isinstance(route, APIRoute)
    }
    for path in (
        "/api/grile/monthly/run",
        "/api/grile/monthly/manifests/{manifest_id}/approve",
    ):
        route = routes[path]
        assert route.methods == {"POST"}
        dependencies = {dependency.call for dependency in route.dependant.dependencies}
        assert grile_router.require_grile_admin in dependencies
