"""Dashboard-only API-boundary canonicalization for store selections."""
from __future__ import annotations

from typing import Any

from domain.filter_scope import normalize_filter_values


def canonical_dashboard_site_codes(value: Any) -> list[str] | None:
    """Return the API's immutable, case-preserving store scope.

    The client order is meaningful for compatibility, so only the first
    occurrence of an exact store code is retained. UI sentinel tokens and
    blank tokens never reach services or repositories.
    """
    if value is None:
        return None
    return normalize_filter_values(value)
