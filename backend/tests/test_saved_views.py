from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from repositories.saved_views import SavedViewNameConflict
from schemas.saved_views import SavedViewCreate, SavedViewState, SavedViewUpdate
from services.saved_views import (
    SavedViewDuplicateName,
    SavedViewLimitReached,
    SavedViewNotFound,
    SavedViewsService,
)


def _state(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "tab": "hub",
        "period": "2026-09",
        "filters": {
            "firma": "Toate firmele",
            "rm": "Toți",
            "magazin": ["M001"],
            "agent": ["A001"],
        },
        "section": "current",
        "subtab": None,
    }
    result.update(overrides)
    return result


def _row(*, view_id: int = 1, name: str = "Dimineață", state: dict[str, Any] | None = None):
    payload = state or _state()
    return {
        "id": view_id,
        "module_id": payload["tab"],
        "name": name,
        "state_json": json.dumps(payload),
        "schema_version": 1,
        "created_at": "2026-09-11T10:00:00+00:00",
        "updated_at": "2026-09-11T10:00:00+00:00",
    }


class FakeRepository:
    def __init__(self):
        self.calls: list[tuple] = []
        self.create_result = _row()
        self.update_result = _row()
        self.delete_result = True
        self.raise_conflict = False

    async def list_views(self, owner_subject: str):
        self.calls.append(("list", owner_subject))
        return [_row()]

    async def create_view(self, owner_subject: str, **kwargs):
        self.calls.append(("create", owner_subject, kwargs))
        if self.raise_conflict:
            raise SavedViewNameConflict
        return self.create_result

    async def update_view(self, owner_subject: str, view_id: int, **kwargs):
        self.calls.append(("update", owner_subject, view_id, kwargs))
        if self.raise_conflict:
            raise SavedViewNameConflict
        return self.update_result

    async def delete_view(self, owner_subject: str, view_id: int):
        self.calls.append(("delete", owner_subject, view_id))
        return self.delete_result


def test_saved_view_contract_is_strict_and_canonicalizes_filter_lists():
    model = SavedViewCreate.model_validate(
        {
            "name": "  Vizita mea  ",
            "state": {
                **_state(),
                "filters": {
                    "firma": "  Arsis  ",
                    "rm": "  RM Est  ",
                    "magazin": [" M001 ", "M001", "M002"],
                    "agent": [" A001 ", "A001"],
                },
            },
        }
    )
    assert model.name == "Vizita mea"
    assert model.state.filters.firma == "Arsis"
    assert model.state.filters.rm == "RM Est"
    assert model.state.filters.magazin == ["M001", "M002"]
    assert model.state.filters.agent == ["A001"]

    with pytest.raises(ValidationError):
        SavedViewCreate.model_validate(
            {"name": "X", "owner_subject": "attacker", "state": _state()}
        )


def test_saved_view_contract_rejects_invalid_module_shape_and_oversized_selection():
    with pytest.raises(ValidationError):
        SavedViewState.model_validate(
            _state(tab="management", section="current", subtab="pnl")
        )
    with pytest.raises(ValidationError):
        SavedViewState.model_validate(
            _state(
                filters={
                    "firma": "Arsis",
                    "rm": "RM Est",
                    "magazin": [f"M{index:03d}" for index in range(51)],
                    "agent": [],
                }
            )
        )
    with pytest.raises(ValidationError):
        SavedViewUpdate.model_validate({})


@pytest.mark.anyio
async def test_service_derives_all_ownership_operations_from_caller_subject():
    repo = FakeRepository()
    service = SavedViewsService(repo)  # type: ignore[arg-type]

    items = await service.list_views("subject-a")
    created = await service.create_view("subject-a", name="Dimineață", state=_state())
    updated = await service.update_view(
        "subject-a",
        7,
        name="Seară",
        state=_state(section="history"),
    )
    await service.delete_view("subject-a", 7)

    assert items[0]["name"] == "Dimineață"
    assert created["module_id"] == "hub"
    assert updated["state"]["section"] == "history"
    assert repo.calls[0] == ("list", "subject-a")
    assert repo.calls[1][0:2] == ("create", "subject-a")
    assert repo.calls[2][0:3] == ("update", "subject-a", 7)
    assert repo.calls[3] == ("delete", "subject-a", 7)


@pytest.mark.anyio
async def test_service_maps_limit_conflict_and_cross_owner_miss_fail_closed():
    repo = FakeRepository()
    service = SavedViewsService(repo)  # type: ignore[arg-type]

    repo.create_result = None
    with pytest.raises(SavedViewLimitReached):
        await service.create_view("subject-a", name="Limit", state=_state())

    repo.create_result = _row()
    repo.raise_conflict = True
    with pytest.raises(SavedViewDuplicateName):
        await service.create_view("subject-a", name="Duplicate", state=_state())

    repo.raise_conflict = False
    repo.update_result = None
    with pytest.raises(SavedViewNotFound):
        await service.update_view("subject-b", 7, name="No access", state=None)

    repo.delete_result = False
    with pytest.raises(SavedViewNotFound):
        await service.delete_view("subject-b", 7)
