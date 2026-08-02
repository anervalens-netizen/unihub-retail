"""Dashboard-only API-boundary canonicalization for store selections."""
from __future__ import annotations

from typing import Any

from services.filters import normalize_filter


def canonical_dashboard_site_codes(value: Any) -> str | None:
    """Return the API's immutable, case-preserving store scope.

    The client order is meaningful for compatibility, so only the first
    occurrence of an exact store code is retained. UI sentinel tokens and
    blank tokens never reach services or repositories.
    """
    if value is None:
        return None
    seen: set[str] = set()
    site_codes: list[str] = []
    for raw_site_code in str(value).split(","):
        site_code = normalize_filter(raw_site_code)
        if site_code is None or site_code in seen:
            continue
        seen.add(site_code)
        site_codes.append(site_code)
    return ",".join(site_codes) or None
