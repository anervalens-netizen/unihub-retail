"""Bounded HTTP contract for personal Saved Views.

The router is mounted on a minimal FastAPI application so the tests exercise
only the Saved Views surface. Ownership is proven through the real
`require_auth` dependency override: the `owner_subject` handed to the service
is always the caller's `AuthClaims.sub`, never a client field.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

from auth import AuthClaims, require_auth
from routers.saved_views import get_saved_views_service, router
from services.saved_views import (
    SavedViewDuplicateName,
    SavedViewLimitReached,
    SavedViewNotFound,
)

TEST_OWNER_LIMIT = 3

STATE: dict[str, Any] = {
    "tab": "hub",
    "period": "2026-09",
    "filters": {
        "firma": "Toate firmele",
        "rm": "Toți",
        "magazin": ["M001"],
        "agent": [],
    },
    "section": "current",
    "subtab": None,
}

EXPECTED_METHODS = {
    "/api/saved-views": {"GET", "POST"},
    "/api/saved-views/{view_id}": {"PATCH", "DELETE"},
}


def _claims(subject: str) -> AuthClaims:
    return AuthClaims(
        sub=subject,
        email="saved-views@example.invalid",
        preferred_username="saved-views",
        groups=["unihub-agent"],
        iss="test",
        aud="test",
        iat=0,
        exp=1,
        raw={},
    )


class _InMemorySavedViewsService:
    """Owner-scoped stand-in with the real duplicate/limit/404 semantics."""

    def __init__(self, *, limit: int = 50) -> None:
        self.limit = limit
        self.views: dict[str, dict[int, dict[str, Any]]] = {}
        self.calls: list[tuple[Any, ...]] = []
        self._next_id = 1

    def _owned(self, owner_subject: str, view_id: int) -> dict[str, Any]:
        view = self.views.get(owner_subject, {}).get(view_id)
        if view is None:
            raise SavedViewNotFound
        return view

    def _item(self, view: dict[str, Any]) -> dict[str, Any]:
        return {**view, "state": dict(view["state"])}

    async def list_views(self, owner_subject: str) -> list[dict[str, Any]]:
        self.calls.append(("list", owner_subject))
        return [self._item(view) for view in self.views.get(owner_subject, {}).values()]

    async def create_view(
        self,
        owner_subject: str,
        *,
        name: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(("create", owner_subject, name, state))
        owned = self.views.setdefault(owner_subject, {})
        if len(owned) >= self.limit:
            raise SavedViewLimitReached
        if any(view["name"].casefold() == name.casefold() for view in owned.values()):
            raise SavedViewDuplicateName
        view_id = self._next_id
        self._next_id += 1
        view = {
            "id": view_id,
            "module_id": state["tab"],
            "name": name,
            "state": state,
            "schema_version": 1,
            "created_at": "2026-09-11T10:00:00+00:00",
            "updated_at": "2026-09-11T10:00:00+00:00",
        }
        owned[view_id] = view
        return self._item(view)

    async def update_view(
        self,
        owner_subject: str,
        view_id: int,
        *,
        name: str | None,
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self.calls.append(("update", owner_subject, view_id, name, state))
        view = self._owned(owner_subject, view_id)
        if name is not None and any(
            other_id != view_id and other["name"].casefold() == name.casefold()
            for other_id, other in self.views[owner_subject].items()
        ):
            raise SavedViewDuplicateName
        updated = {
            **view,
            "name": name if name is not None else view["name"],
            "state": state if state is not None else view["state"],
        }
        if state is not None:
            updated["module_id"] = state["tab"]
        self.views[owner_subject][view_id] = updated
        return self._item(updated)

    async def delete_view(self, owner_subject: str, view_id: int) -> None:
        self.calls.append(("delete", owner_subject, view_id))
        self._owned(owner_subject, view_id)
        del self.views[owner_subject][view_id]


def _client(
    service: _InMemorySavedViewsService,
    *,
    subject: str,
) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_auth] = lambda: _claims(subject)
    app.dependency_overrides[get_saved_views_service] = lambda: service
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://retail.example.invalid",
    )


@pytest.mark.anyio
async def test_post_creates_owner_bound_view_and_never_exposes_owner_subject() -> None:
    service = _InMemorySavedViewsService()
    async with _client(service, subject="subject-a") as client:
        response = await client.post(
            "/api/saved-views",
            json={"name": "  Dimineață  ", "state": STATE},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Dimineață"
    assert body["module_id"] == "hub"
    assert body["schema_version"] == 1
    assert body["state"]["tab"] == "hub"
    assert "owner_subject" not in body
    assert service.calls == [
        ("create", "subject-a", "Dimineață", {**STATE, "filters": dict(STATE["filters"])})
    ]


@pytest.mark.anyio
async def test_list_is_owner_scoped_and_never_exposes_owner_subject() -> None:
    service = _InMemorySavedViewsService()
    async with _client(service, subject="subject-a") as client_a:
        await client_a.post("/api/saved-views", json={"name": "A", "state": STATE})
    async with _client(service, subject="subject-b") as client_b:
        await client_b.post("/api/saved-views", json={"name": "B", "state": STATE})

    async with _client(service, subject="subject-a") as client_a:
        response = await client_a.get("/api/saved-views")

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["A"]
    assert all("owner_subject" not in item for item in body["items"])
    assert service.calls[-1] == ("list", "subject-a")


@pytest.mark.anyio
async def test_client_supplied_owner_subject_is_rejected_before_any_write() -> None:
    service = _InMemorySavedViewsService()
    async with _client(service, subject="subject-a") as client:
        create = await client.post(
            "/api/saved-views",
            json={"name": "Injected", "owner_subject": "subject-b", "state": STATE},
        )
        update = await client.patch(
            "/api/saved-views/1",
            json={"owner_subject": "subject-b", "name": "Injected"},
        )

    assert create.status_code == 422
    assert update.status_code == 422
    assert service.calls == []


@pytest.mark.anyio
async def test_foreign_and_missing_ids_are_404_for_update_and_delete() -> None:
    service = _InMemorySavedViewsService()
    async with _client(service, subject="subject-a") as client_a:
        created = await client_a.post(
            "/api/saved-views", json={"name": "Dimineață", "state": STATE}
        )
    view_id = created.json()["id"]

    async with _client(service, subject="subject-b") as client_b:
        foreign_update = await client_b.patch(
            f"/api/saved-views/{view_id}", json={"name": "Furat"}
        )
        foreign_delete = await client_b.delete(f"/api/saved-views/{view_id}")
        missing_update = await client_b.patch(
            "/api/saved-views/999999", json={"name": "Inexistent"}
        )
        missing_delete = await client_b.delete("/api/saved-views/999999")

    assert [
        foreign_update.status_code,
        foreign_delete.status_code,
        missing_update.status_code,
        missing_delete.status_code,
    ] == [404, 404, 404, 404]
    assert all(call[1] == "subject-b" for call in service.calls[1:])

    async with _client(service, subject="subject-a") as client_a:
        listing = await client_a.get("/api/saved-views")
    assert [item["name"] for item in listing.json()["items"]] == ["Dimineață"]


@pytest.mark.anyio
async def test_duplicate_name_for_the_same_owner_conflicts_with_409() -> None:
    service = _InMemorySavedViewsService()
    async with _client(service, subject="subject-a") as client:
        first = await client.post(
            "/api/saved-views", json={"name": "Dimineață", "state": STATE}
        )
        duplicate = await client.post(
            "/api/saved-views", json={"name": "dimineață", "state": STATE}
        )
        created_second = await client.post(
            "/api/saved-views", json={"name": "Seară", "state": STATE}
        )
        duplicate_rename = await client.patch(
            f"/api/saved-views/{created_second.json()['id']}",
            json={"name": "DIMINEAȚĂ"},
        )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert created_second.status_code == 201
    assert duplicate_rename.status_code == 409


@pytest.mark.anyio
async def test_identical_name_is_allowed_for_a_different_owner() -> None:
    service = _InMemorySavedViewsService()
    async with _client(service, subject="subject-a") as client_a:
        owner_a = await client_a.post(
            "/api/saved-views", json={"name": "Dimineață", "state": STATE}
        )
    async with _client(service, subject="subject-b") as client_b:
        owner_b = await client_b.post(
            "/api/saved-views", json={"name": "Dimineață", "state": STATE}
        )

    assert owner_a.status_code == 201
    assert owner_b.status_code == 201


@pytest.mark.anyio
async def test_owner_limit_is_enforced_with_409() -> None:
    service = _InMemorySavedViewsService(limit=TEST_OWNER_LIMIT)
    async with _client(service, subject="subject-a") as client:
        statuses = [
            (
                await client.post(
                    "/api/saved-views", json={"name": f"View {index}", "state": STATE}
                )
            ).status_code
            for index in range(TEST_OWNER_LIMIT + 1)
        ]

    assert statuses == [201] * TEST_OWNER_LIMIT + [409]


@pytest.mark.anyio
async def test_update_and_delete_use_the_authenticated_subject() -> None:
    service = _InMemorySavedViewsService()
    async with _client(service, subject="subject-a") as client:
        created = await client.post(
            "/api/saved-views", json={"name": "Dimineață", "state": STATE}
        )
        view_id = created.json()["id"]
        updated = await client.patch(
            f"/api/saved-views/{view_id}",
            json={"name": "Seară", "state": {**STATE, "section": "history"}},
        )
        deleted = await client.delete(f"/api/saved-views/{view_id}")
        remaining = await client.get("/api/saved-views")

    assert updated.status_code == 200
    assert updated.json()["name"] == "Seară"
    assert updated.json()["state"]["section"] == "history"
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert remaining.json() == {"items": []}
    assert service.calls[1][0:3] == ("update", "subject-a", view_id)
    assert service.calls[2] == ("delete", "subject-a", view_id)


@pytest.mark.anyio
async def test_malformed_state_is_rejected_before_persistence() -> None:
    service = _InMemorySavedViewsService()
    async with _client(service, subject="subject-a") as client:
        responses = [
            await client.post(
                "/api/saved-views",
                json={"name": "No state", "state": {**STATE, "tab": "grile"}},
            ),
            await client.post(
                "/api/saved-views",
                json={"name": "Bad section", "state": {**STATE, "section": "unknown"}},
            ),
            await client.post(
                "/api/saved-views",
                json={"name": "x" * 81, "state": STATE},
            ),
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    assert service.calls == []


def test_application_registers_saved_views_routes_under_authentication() -> None:
    from main import app

    routes = [
        context
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute)
        and (context.path or "").startswith("/api/saved-views")
    ]

    registered: dict[str, set[str]] = {}
    for context in routes:
        assert context.path is not None
        registered.setdefault(context.path, set()).update(context.methods or ())

    assert registered == EXPECTED_METHODS
    for context in routes:
        assert context.dependant is not None
        assert require_auth in {
            dependency.call for dependency in context.dependant.dependencies
        }


def test_openapi_declares_the_error_statuses_the_router_already_returns() -> None:
    """The contract must publish the 404/409 the router already raises.

    Create reports a duplicate name or an exhausted owner limit as 409; update
    reports an absent/foreign view as 404 and a rename conflict as 409; delete
    reports an absent/foreign view as 404. All of them are description-only.
    """
    from main import app

    paths = app.openapi()["paths"]
    create = paths["/api/saved-views"]["post"]["responses"]
    update = paths["/api/saved-views/{view_id}"]["patch"]["responses"]
    delete = paths["/api/saved-views/{view_id}"]["delete"]["responses"]

    assert set(create) >= {"201", "409", "422"}
    assert set(update) >= {"200", "404", "409", "422"}
    assert set(delete) >= {"200", "404", "422"}

    for response in (create["409"], update["404"], update["409"], delete["404"]):
        assert isinstance(response.get("description"), str) and response["description"]

    # The single create conflict status covers both real situations.
    documented = create["409"]["description"].casefold()
    assert "conflict" in documented and "limit" in documented


def test_openapi_leaves_the_saved_views_list_without_invented_errors() -> None:
    """Listing is owner-scoped: there is no absent or conflicting view to report."""
    from main import app

    responses = app.openapi()["paths"]["/api/saved-views"]["get"]["responses"]

    assert set(responses) >= {"200"}
    assert not {"404", "409"} & set(responses)
