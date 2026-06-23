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


def require_salary_access(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    route = request.scope.get("route")
    route_template = getattr(route, "path", "/salarii")

    if not can_access_salaries(claims):
        logger.warning(
            "sensitive_access denied resource=salarii subject=%s route=%s",
            claims.sub,
            route_template,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Salary access requires the unihub-manager, "
                "unihub-hr, or unihub-admin role"
            ),
        )

    logger.info(
        "sensitive_access allowed resource=salarii subject=%s route=%s",
        claims.sub,
        route_template,
    )
    request.state.salary_claims = claims
    return claims


def require_import_admin(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    route = request.scope.get("route")
    route_template = getattr(route, "path", "/api/import")
    if not can_administer_imports(claims):
        logger.warning(
            "sensitive_access denied resource=sales_import subject=%s route=%s",
            claims.sub,
            route_template,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sales imports require the unihub-admin role",
        )
    logger.info(
        "sensitive_access allowed resource=sales_import subject=%s route=%s",
        claims.sub,
        route_template,
    )
    return claims
