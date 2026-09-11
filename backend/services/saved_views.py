from __future__ import annotations

import json
from typing import Any

from repositories.saved_views import SavedViewNameConflict, SavedViewsRepository


class SavedViewDuplicateName(RuntimeError):
    pass


class SavedViewLimitReached(RuntimeError):
    pass


class SavedViewNotFound(RuntimeError):
    pass


class SavedViewsService:
    def __init__(self, repository: SavedViewsRepository):
        self.repository = repository

    @staticmethod
    def _item(row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "module_id": str(row["module_id"]),
            "name": str(row["name"]),
            "state": json.loads(str(row["state_json"])),
            "schema_version": int(row["schema_version"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    async def list_views(self, owner_subject: str) -> list[dict[str, Any]]:
        rows = await self.repository.list_views(owner_subject)
        return [self._item(row) for row in rows]

    async def create_view(
        self,
        owner_subject: str,
        *,
        name: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            row = await self.repository.create_view(
                owner_subject,
                module_id=str(state["tab"]),
                name=name,
                state=state,
            )
        except SavedViewNameConflict as exc:
            raise SavedViewDuplicateName from exc
        if row is None:
            raise SavedViewLimitReached
        return self._item(row)

    async def update_view(
        self,
        owner_subject: str,
        view_id: int,
        *,
        name: str | None,
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            row = await self.repository.update_view(
                owner_subject,
                view_id,
                name=name,
                module_id=str(state["tab"]) if state is not None else None,
                state=state,
            )
        except SavedViewNameConflict as exc:
            raise SavedViewDuplicateName from exc
        if row is None:
            raise SavedViewNotFound
        return self._item(row)

    async def delete_view(self, owner_subject: str, view_id: int) -> None:
        if not await self.repository.delete_view(owner_subject, view_id):
            raise SavedViewNotFound
