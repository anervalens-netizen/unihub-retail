"""Dashboard-only API-boundary canonicalization for store selections."""
from __future__ import annotations

from typing import Any

from services.filters import normalize_filter


def canonical_dashboard_site_codes(value: Any) -> str | None:
    """Trim, uppercase, sort and deduplicate the comma-separated store scope."""
    normalized = normalize_filter(value)
    if normalized is None:
        return None
    site_codes = {
        site_code.strip().upper()
        for site_code in normalized.split(",")
        if site_code.strip()
    }
    return ",".join(sorted(site_codes)) or None
