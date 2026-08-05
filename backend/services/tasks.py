from __future__ import annotations

from typing import Any
from fastapi import HTTPException

from repositories.tasks import TasksRepository


class TasksService:
    def __init__(self, repo: TasksRepository):
        self.repo = repo

    async def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        row = await self.repo.create_task(data)
        if not row:
            raise HTTPException(status_code=500, detail="Eroare la crearea task-ului")
        return dict(row)

    async def list_tasks(
        self,
        status: str | None,
        assignee: str | None,
        site_code: str | None,
        only_mine: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows, total = await self.repo.list_tasks(
            status,
            assignee,
            site_code,
            only_mine,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [
                {key: value for key, value in dict(row).items() if key != "total_count"}
                for row in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def update_task(self, task_id: int, data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            raise HTTPException(status_code=400, detail="Niciun câmp de actualizat")
            
        row = await self.repo.update_task(task_id, data)
        if row is None:
            raise HTTPException(status_code=404, detail="Task negăsit")
        return dict(row)

    async def delete_task(self, task_id: int) -> bool:
        deleted = await self.repo.delete_task(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Task negăsit")
        return True
