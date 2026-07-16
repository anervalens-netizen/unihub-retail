"""Pure, fail-closed policy for high-impact OIDC group authorization."""
from __future__ import annotations

import os

TARGET_FINALIZER_GROUPS_ENV = "TARGET_CALCULATOR_FINALIZER_GROUPS"
GRILE_FINALIZER_GROUPS_ENV = "GRILE_FINALIZER_GROUPS"
GRILE_TARGET_SYNC_GROUPS_ENV = "GRILE_TARGET_SYNC_GROUPS"
STORE_PNL_ACCESS_GROUPS_ENV = "STORE_PNL_ACCESS_GROUPS"
DEPRECATED_TARGET_EMAILS_ENV = "TARGET_CALCULATOR_FINALIZER_EMAILS"
DEPRECATED_GRILE_EMAILS_ENV = "GRILE_FINALIZER_EMAILS"
DEPRECATED_PNL_OWNER_EMAILS_ENV = "PNL_OWNER_EMAILS"
DEPRECATED_VITE_PNL_OWNER_EMAILS_ENV = "VITE_PNL_OWNER_EMAILS"


def parse_group_list(raw: str | None, env_name: str) -> frozenset[str]:
    """Parse a complete group policy or reject it without partial acceptance."""
    if raw is None or not raw.strip():
        return frozenset()
    groups: set[str] = set()
    for item in raw.split(","):
        if any(ord(char) < 32 or ord(char) == 127 for char in item):
            raise ValueError(f"{env_name} has invalid group configuration")
        try:
            group = item.strip().casefold()
        except Exception as exc:
            raise ValueError(f"{env_name} has invalid group configuration") from exc
        if (
            not group
            or "@" in group
            or len(group) > 128
            or not group.isprintable()
        ):
            raise ValueError(f"{env_name} has invalid group configuration")
        groups.add(group)
    return frozenset(groups)


def configured_groups(env_name: str) -> frozenset[str]:
    """Return no groups at runtime for absent, empty, or malformed policy."""
    try:
        return parse_group_list(os.getenv(env_name), env_name)
    except ValueError:
        return frozenset()


def has_configured_group(claim_groups: list[str], env_name: str) -> bool:
    allowed = configured_groups(env_name)
    if not allowed:
        return False
    normalized: set[str] = set()
    for group in claim_groups:
        if isinstance(group, str):
            try:
                normalized.add(group.strip().casefold())
            except Exception:
                continue
    return bool(normalized & allowed)


def privileged_access_config_errors(production: bool) -> list[str]:
    """Return safe startup errors without exposing configured values."""
    errors: list[str] = []
    for env_name in (
        TARGET_FINALIZER_GROUPS_ENV,
        GRILE_FINALIZER_GROUPS_ENV,
        GRILE_TARGET_SYNC_GROUPS_ENV,
        STORE_PNL_ACCESS_GROUPS_ENV,
    ):
        raw = os.getenv(env_name)
        if raw is None or not raw.strip():
            if production:
                errors.append(f"{env_name} este nesetat sau gol (obligatoriu în producție)")
            continue
        try:
            parse_group_list(raw, env_name)
        except ValueError:
            errors.append(f"{env_name} are configurare de grup invalidă")
    if production:
        for env_name in (
            DEPRECATED_TARGET_EMAILS_ENV,
            DEPRECATED_GRILE_EMAILS_ENV,
            DEPRECATED_PNL_OWNER_EMAILS_ENV,
            DEPRECATED_VITE_PNL_OWNER_EMAILS_ENV,
        ):
            if os.getenv(env_name, "").strip():
                errors.append(f"{env_name} este deprecated și nu este permis în producție")
    return errors
