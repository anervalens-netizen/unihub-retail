"""Deterministic generation identity for Promo v1 to v2 migration."""

from __future__ import annotations

import hashlib
from typing import Any


def target_generation_id(
    pointer_bytes: bytes,
    source_plans: list[Any],
) -> str:
    seed = hashlib.sha256(
        pointer_bytes
        + b"\0promo-v1-to-v2\0"
        + b"".join(
            source.source_sha256.encode("ascii")
            + hashlib.sha256(source.material).hexdigest().encode("ascii")
            for source in source_plans
        )
    ).hexdigest()
    return seed[:32]
