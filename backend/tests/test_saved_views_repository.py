from __future__ import annotations

from typing import Any

import pytest

from repositories.saved_views import (
    MAX_SAVED_VIEWS_PER_OWNER,
    SavedViewsRepository,
)


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.count = 0
        self.row = {
            "id": 1,
            "module_id": "hub",
            "name": "View",
            "state_json": '{"tab":"hub","filters":{},"section":"current","subtab":null}',
            "schema_version": 1,
            "created_at": "2026-09-11T10:00:00+00:00",
            "updated_at": "2026-09-11T10:00:00+00:00",
        }
        self.delete_result = "DELETE 1"

    def transaction(self):
        return _AsyncContext(None)

    async def fetch(self, query: str, *params):
        self.calls.append(("fetch", query, params))
        return [self.row]

    async def fetchval(self, query: str, *params):
        self.calls.append(("fetchval", query, params))
        return self.count

    async def fetchrow(self, query: str, *params):
        self.calls.append(("fetchrow", query, params))
        return self.row

    async def execute(self, query: str, *params):
        self.calls.append(("execute", query, params))
        if query.startswith("DELETE"):
            return self.delete_result
        return "SELECT 1"


class FakePool:
    def __init__(self, connection: FakeConnection):
        self.connection = connection

    def acquire(self):
        return _AsyncContext(self.connection)


@pytest.mark.anyio
async def test_repository_scopes_list_update_and_delete_by_owner_subject():
    connection = FakeConnection()
    repo = SavedViewsRepository(FakePool(connection))  # type: ignore[arg-type]

    await repo.list_views("subject-a")
    await repo.update_view(
        "subject-a",
        9,
        name="Updated",
        module_id=None,
        state=None,
    )
    await repo.delete_view("subject-a", 9)

    list_call, update_call, delete_call = connection.calls
    assert "WHERE owner_subject = $1" in list_call[1]
    assert list_call[2] == ("subject-a",)
    assert "WHERE id = $1 AND owner_subject = $2" in update_call[1]
    assert update_call[2][0:2] == (9, "subject-a")
    assert "WHERE id = $1 AND owner_subject = $2" in delete_call[1]
    assert delete_call[2] == (9, "subject-a")


@pytest.mark.anyio
async def test_repository_serializes_create_limit_per_owner_before_insert():
    connection = FakeConnection()
    connection.count = MAX_SAVED_VIEWS_PER_OWNER
    repo = SavedViewsRepository(FakePool(connection))  # type: ignore[arg-type]

    result = await repo.create_view(
        "subject-a",
        module_id="hub",
        name="Limit",
        state={"tab": "hub", "filters": {}, "section": "current", "subtab": None},
    )

    assert result is None
    assert connection.calls[0][0] == "execute"
    assert "pg_advisory_xact_lock" in connection.calls[0][1]
    assert connection.calls[0][2] == ("subject-a",)
    assert connection.calls[1][0] == "fetchval"
    assert connection.calls[1][2] == ("subject-a",)
    assert all(call[0] != "fetchrow" for call in connection.calls)
