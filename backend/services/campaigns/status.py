"""Pure status mapping for Campaigns response projections."""
from __future__ import annotations


def calculation_status(
    *,
    configured: bool,
    error: str | None,
    partial: bool = False,
) -> str:
    if error is not None:
        return "invalid"
    if partial:
        return "partial"
    return "complete" if configured else "not_configured"
