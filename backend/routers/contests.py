from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from models import ContestResponse
from repositories.contests import ContestsRepository
from services.contests import ContestsService

router = APIRouter(prefix="/api/contests", tags=["contests"])


async def get_contests_service() -> ContestsService:
    pool = await get_pool()
    repo = ContestsRepository(pool)
    return ContestsService(repo, pool)


@router.get("/active", response_model=ContestResponse | None)
async def get_active_contest(
    month: str = Query(...),
    svc: ContestsService = Depends(get_contests_service),
) -> ContestResponse | None:
    """Concursul activ pentru luna data + clasamentul agentilor. None daca nu exista."""
    return await svc.get_active_contest(month)
