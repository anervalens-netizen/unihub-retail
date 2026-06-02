from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from models import ContestResponse
from repositories.contests import ContestsRepository
from services.contests import ContestsService

# NB: `/active` accepta `site_codes` (comma) ca override de scope, folosit de
# proxy-ul intern FieldOps (X-Hub-Internal) pentru scoping per Team Leader.
router = APIRouter(prefix="/api/contests", tags=["contests"])


async def get_contests_service() -> ContestsService:
    pool = await get_pool()
    repo = ContestsRepository(pool)
    return ContestsService(repo, pool)


@router.get("/active", response_model=ContestResponse | None)
async def get_active_contest(
    month: str = Query(...),
    site_codes: str | None = Query(
        None,
        description=(
            "Optional: lista comma-separated de site_code-uri care suprascrie "
            "scope-ul din config (folosit de proxy-ul intern FieldOps pentru "
            "scoping per Team Leader). Ignorat daca lipseste."
        ),
    ),
    svc: ContestsService = Depends(get_contests_service),
) -> ContestResponse | None:
    """Concursul activ pentru luna data + clasamentul agentilor. None daca nu exista."""
    override = (
        [code.strip() for code in site_codes.split(",") if code.strip()]
        if site_codes
        else None
    )
    return await svc.get_active_contest(month, site_codes_override=override or None)
