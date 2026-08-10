"""Explicit projections from internal Dashboard query rows to public contracts."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def public_stats_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload.pop("import_month", None)
    return payload
