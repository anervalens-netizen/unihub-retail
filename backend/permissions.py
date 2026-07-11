from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, status

from auth import AuthClaims, require_auth

logger = logging.getLogger(__name__)

SALARY_ACCESS_GROUPS = frozenset(
    {
        "authentik admins",
        "unihub-admin",
        "unihub-hr",
        "unihub-manager",
    }
)
ADMIN_ACCESS_GROUPS = frozenset({"authentik admins", "unihub-admin"})
MANAGEMENT_ACCESS_GROUPS = frozenset(
    {
        "authentik admins",
        "unihub-admin",
        "unihub-manager",
        "unihub-hr",
    }
)
BUSINESS_WRITE_GROUPS = frozenset(
    {
        "authentik admins",
        "unihub-admin",
        "unihub-manager",
    }
)


def normalized_groups(groups: list[str]) -> set[str]:
    return {
        group.strip().casefold()
        for group in groups
        if isinstance(group, str) and group.strip()
    }


def can_access_salaries(claims: AuthClaims) -> bool:
    return bool(normalized_groups(claims.groups) & SALARY_ACCESS_GROUPS)


def can_administer_imports(claims: AuthClaims) -> bool:
    return bool(normalized_groups(claims.groups) & ADMIN_ACCESS_GROUPS)


def can_access_management(claims: AuthClaims) -> bool:
    return bool(normalized_groups(claims.groups) & MANAGEMENT_ACCESS_GROUPS)


def can_write_business_data(claims: AuthClaims) -> bool:
    return bool(normalized_groups(claims.groups) & BUSINESS_WRITE_GROUPS)


def _route_template(request: Request, fallback: str) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", fallback)


def _require_group_access(
    *,
    request: Request,
    claims: AuthClaims,
    allowed: bool,
    resource: str,
    detail: str,
    fallback_route: str,
) -> AuthClaims:
    route_template = _route_template(request, fallback_route)
    if not allowed:
        logger.warning(
            "sensitive_access denied resource=%s subject=%s route=%s",
            resource,
            claims.sub,
            route_template,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )
    logger.info(
        "sensitive_access allowed resource=%s subject=%s route=%s",
        resource,
        claims.sub,
        route_template,
    )
    return claims


def require_privileged_access(
    *,
    request: Request,
    claims: AuthClaims,
    allowed: bool,
    resource: str,
    detail: str,
    fallback_route: str,
) -> AuthClaims:
    """Audit a dedicated privileged decision without exposing token details."""
    route_template = _route_template(request, fallback_route)
    decision = "allowed" if allowed else "denied"
    log = logger.info if allowed else logger.warning
    log(
        "privileged_access decision=%s resource=%s subject=%s route=%s",
        decision,
        resource,
        claims.sub,
        route_template,
    )
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    return claims


def require_salary_access(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    _require_group_access(
        request=request,
        claims=claims,
        allowed=can_access_salaries(claims),
        resource="salarii",
        detail=(
            "Salary access requires the unihub-manager, "
            "unihub-hr, or unihub-admin role"
        ),
        fallback_route="/salarii",
    )
    request.state.salary_claims = claims
    return claims


def require_import_admin(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    return _require_group_access(
        request=request,
        claims=claims,
        allowed=can_administer_imports(claims),
        resource="sales_import",
        detail="Sales imports require the unihub-admin role",
        fallback_route="/api/import",
    )


def require_management_access(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    return _require_group_access(
        request=request,
        claims=claims,
        allowed=can_access_management(claims),
        resource="management",
        detail="Management access requires the unihub-manager, unihub-hr, or unihub-admin role",
        fallback_route="/api/management",
    )


def require_report_export_access(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    return _require_group_access(
        request=request,
        claims=claims,
        allowed=can_access_management(claims),
        resource="report_export",
        detail="Server-side exports require the unihub-manager, unihub-hr, or unihub-admin role",
        fallback_route="/api/exports",
    )


def require_business_write_access(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    return _require_group_access(
        request=request,
        claims=claims,
        allowed=can_write_business_data(claims),
        resource="business_write",
        detail="Business writes require the unihub-manager or unihub-admin role",
        fallback_route="/api",
    )
