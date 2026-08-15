"""Validated admin replay service for one exact dead outbox event."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import re
from typing import Any
from uuid import UUID


_REASON_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,79}$")


async def replay_dead_event(
    *,
    repository: Any,
    event_id: UUID,
    reason: str,
    requested_by_sub: str,
    now: datetime,
) -> int:
    """Hash the operator subject and append one replay audit before requeue."""
    if not _REASON_RE.fullmatch(reason):
        raise ValueError("replay reason must be canonical and at most 80 characters")
    actor = requested_by_sub.strip()
    if not actor:
        raise ValueError("requested_by_sub is required")
    actor_sha256 = sha256(actor.encode("utf-8")).hexdigest()
    return await repository.replay_dead(
        event_id=event_id,
        reason=reason,
        requested_by_sub_sha256=actor_sha256,
        now=now,
    )
