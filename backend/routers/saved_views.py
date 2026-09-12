"""Personal Saved Views HTTP surface.

Ownership is never accepted from the client: the caller's canonical OIDC
`AuthClaims.sub` is the only `owner_subject` used for repository access, so a
foreign or missing id is indistinguishable from a missing row (404). The
router persists only the already-stable V3 URL context contract and exposes no
sharing, publishing or approval endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from auth import AuthClaims, require_auth
from composition import build_saved_views_service
from schemas.saved_views import (
    SavedViewCreate,
    SavedViewDeleteResponse,
    SavedViewItem,
    SavedViewListResponse,
    SavedViewUpdate,
)
from services.saved_views import (
    SavedViewDuplicateName,
    SavedViewLimitReached,
    SavedViewNotFound,
    SavedViewsService,
)

router = APIRouter(prefix="/api/saved-views", tags=["saved-views"])

get_saved_views_service = build_saved_views_service


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail)


def _missing() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Saved view not found")


@router.get("", response_model=SavedViewListResponse)
async def list_saved_views(
    claims: AuthClaims = Depends(require_auth),
    svc: SavedViewsService = Depends(get_saved_views_service),
) -> SavedViewListResponse:
    return SavedViewListResponse(
        items=[SavedViewItem.model_validate(item) for item in await svc.list_views(claims.sub)]
    )


@router.post(
    "",
    response_model=SavedViewItem,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Saved view name conflict or limit reached"}},
)
async def create_saved_view(
    payload: SavedViewCreate,
    claims: AuthClaims = Depends(require_auth),
    svc: SavedViewsService = Depends(get_saved_views_service),
) -> SavedViewItem:
    try:
        item = await svc.create_view(
            claims.sub,
            name=payload.name,
            state=payload.state.model_dump(mode="json"),
        )
    except SavedViewDuplicateName as exc:
        raise _conflict("A saved view with this name already exists") from exc
    except SavedViewLimitReached as exc:
        raise _conflict("Saved view limit reached") from exc
    return SavedViewItem.model_validate(item)


@router.patch(
    "/{view_id}",
    response_model=SavedViewItem,
    responses={
        404: {"description": "Saved view not found"},
        409: {"description": "Saved view name conflict"},
    },
)
async def update_saved_view(
    view_id: int,
    payload: SavedViewUpdate,
    claims: AuthClaims = Depends(require_auth),
    svc: SavedViewsService = Depends(get_saved_views_service),
) -> SavedViewItem:
    try:
        item = await svc.update_view(
            claims.sub,
            view_id,
            name=payload.name,
            state=(
                payload.state.model_dump(mode="json")
                if payload.state is not None
                else None
            ),
        )
    except SavedViewDuplicateName as exc:
        raise _conflict("A saved view with this name already exists") from exc
    except SavedViewNotFound as exc:
        raise _missing() from exc
    return SavedViewItem.model_validate(item)


@router.delete(
    "/{view_id}",
    response_model=SavedViewDeleteResponse,
    responses={404: {"description": "Saved view not found"}},
)
async def delete_saved_view(
    view_id: int,
    claims: AuthClaims = Depends(require_auth),
    svc: SavedViewsService = Depends(get_saved_views_service),
) -> SavedViewDeleteResponse:
    try:
        await svc.delete_view(claims.sub, view_id)
    except SavedViewNotFound as exc:
        raise _missing() from exc
    return SavedViewDeleteResponse(ok=True)
