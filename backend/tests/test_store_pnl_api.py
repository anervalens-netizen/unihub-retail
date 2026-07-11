from auth import AuthClaims
from routers.store_pnl import can_access_store_pnl, require_store_pnl_owner
from fastapi import HTTPException


def claims(email: str, groups: list[str] | None = None) -> AuthClaims:
    return AuthClaims(email, email, email, groups or [], "issuer", "audience", 0, 1, {})


def test_store_pnl_management_group_is_allowed() -> None:
    assert can_access_store_pnl(claims("owner@example.invalid", ["unihub-manager"]))


def test_store_pnl_non_management_user_is_forbidden() -> None:
    try:
        require_store_pnl_owner(claims("other@example.invalid"))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("non-owner accepted")
