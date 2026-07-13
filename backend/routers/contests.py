from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from auth import AuthClaims, require_auth
from db.connection import get_pool
from repositories.contests import ContestsRepository
from schemas.contests import ContestResponse
from services.contests import ContestsService

# NB: `/active` accepta `site_codes` (comma) ca override intern de scope.
# FieldOps pastreaza in mod normal scope-ul configurat al concursului; nu folosi
# override-ul pentru concursuri de zona/ASM.
router = APIRouter(prefix="/api/contests", tags=["contests"])


async def get_contests_service() -> ContestsService:
    pool = await get_pool()
    repo = ContestsRepository(pool)
    return ContestsService(repo, pool)


def _internal_site_codes_override(site_codes: str | None, claims: AuthClaims) -> list[str] | None:
    if site_codes and claims.iss == "hub-internal":
        return [code.strip() for code in site_codes.split(",") if code.strip()] or None
    return None


@router.get("/active/all", response_model=list[ContestResponse])
async def get_active_contests(
    month: str = Query(...),
    site_codes: str | None = Query(
        None,
        description=(
            "Optional: lista comma-separated de site_code-uri care suprascrie "
            "scope-ul din config. Onorat DOAR pentru apeluri interne "
            "(principalul hub via X-Hub-Internal). Ignorat pentru useri normali."
        ),
    ),
    claims: AuthClaims = Depends(require_auth),
    svc: ContestsService = Depends(get_contests_service),
) -> list[ContestResponse]:
    """Toate concursurile active pentru luna data + clasamentele agentilor."""
    return await svc.get_active_contests(
        month,
        site_codes_override=_internal_site_codes_override(site_codes, claims),
    )


@router.get("/active", response_model=ContestResponse | None)
async def get_active_contest(
    month: str = Query(...),
    site_codes: str | None = Query(
        None,
        description=(
            "Optional: lista comma-separated de site_code-uri care suprascrie "
            "scope-ul din config. Onorat DOAR pentru apeluri interne "
            "(principalul hub via X-Hub-Internal). Ignorat pentru useri normali."
        ),
    ),
    claims: AuthClaims = Depends(require_auth),
    svc: ContestsService = Depends(get_contests_service),
) -> ContestResponse | None:
    """Concursul activ pentru luna data + clasamentul agentilor. None daca nu exista.

    `site_codes` este un override de scope sensibil (poate cere clasamentul
    oricaror magazine), asa ca il acceptam doar de la principalul intern hub
    (`iss == 'hub-internal'`, setat de require_auth pe X-Hub-Internal de pe
    loopback). UI-ul Retail si FieldOps nu trimit acest parametru pentru
    concursurile de zona. Pentru orice alt apelant parametrul este ignorat si
    scope-ul ramane cel din config.
    """
    return await svc.get_active_contest(
        month,
        site_codes_override=_internal_site_codes_override(site_codes, claims),
    )
