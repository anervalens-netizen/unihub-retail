from auth import AuthClaims
from routers.store_pnl import can_access_store_pnl, require_store_pnl_owner
from fastapi import HTTPException


def claims(email: str) -> AuthClaims:
    return AuthClaims(email, email, email, [], "issuer", "audience", 0, 1, {})


def test_store_pnl_owner_is_allowed(monkeypatch) -> None:
    monkeypatch.setenv("PNL_OWNER_EMAILS", "owner@example.com")
    assert can_access_store_pnl(claims("OWNER@example.com"))


def test_store_pnl_non_owner_is_forbidden(monkeypatch) -> None:
    monkeypatch.setenv("PNL_OWNER_EMAILS", "owner@example.com")
    try:
        require_store_pnl_owner(claims("other@example.com"))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("non-owner accepted")
