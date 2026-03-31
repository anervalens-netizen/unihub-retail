from __future__ import annotations

from typing import Any

_FILTER_SENTINELS = {
    "",
    "Toate",
    "Toti",
    "To\u021bi",
    "To\u00c8\u203aI",  # legacy mojibake value kept for backward compatibility
    "To\u00c3\u02c6\u20ac\u203aI",  # older corrupted variant seen in local state
}


def normalize_filter(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if cleaned in _FILTER_SENTINELS:
        return None
    return cleaned


def build_scope_filter(
    user: dict[str, Any],
    base_alias: str = "s",
    param_start: int = 1,
) -> tuple[str, list[Any]]:
    if user["role"] != "tl":
        return "", []
    site_column = f"{base_alias}.site_code" if base_alias else "site_code"
    return (
        f"{site_column} IN (SELECT site_code FROM tl_store_assignments WHERE user_id = ${param_start}::INTEGER)",
        [user["id"]],
    )
