"""Admin replay contract for exact dead outbox events."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import inspect
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from test_transactional_outbox import (
    MemoryOutboxRepository,
    required_symbol,
)


NOW = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)


class RecordingReplayRepository(MemoryOutboxRepository):
    requested_actor_hash: str | None = None

    async def replay_dead(self, **kwargs: Any) -> int:
        self.requested_actor_hash = str(kwargs["requested_by_sub_sha256"])
        return await super().replay_dead(**kwargs)


def test_replay_surface_is_exact_event_only_and_cli_uses_operations_authority() -> None:
    replay = required_symbol("services.outbox_replay", "replay_dead_event")
    assert set(inspect.signature(replay).parameters) == {
        "repository",
        "event_id",
        "reason",
        "requested_by_sub",
        "now",
    }

    cli = Path("backend/scripts/replay_outbox_event.py")
    assert cli.is_file(), "Release-B admin replay CLI is missing"
    source = cli.read_text(encoding="utf-8")
    assert "DatabaseAuthority.OPERATIONS" in source
    assert "--event-id" in source
    assert "--reason" in source
    assert "--all" not in source
    assert "retail_outbox_events" not in source, (
        "CLI must use the validated replay service, not raw state-changing SQL"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    ["", " ", "Operator Retry", "9starts_with_digit", "x" * 81],
)
async def test_replay_rejects_unbounded_or_noncanonical_reason(reason: str) -> None:
    replay = required_symbol("services.outbox_replay", "replay_dead_event")
    repository = MemoryOutboxRepository()
    event = repository.seed(
        now=NOW,
        name="dead-invalid-reason",
        state="dead",
        attempt_count=8,
    )

    with pytest.raises(ValueError, match="reason"):
        await replay(
            repository=repository,
            event_id=event.id,
            reason=reason,
            requested_by_sub="authentik-user",
            now=NOW,
        )

    assert event.state == "dead"
    assert repository.replay_audit == []


@pytest.mark.asyncio
async def test_replay_refuses_unknown_pending_and_completed_events() -> None:
    replay = required_symbol("services.outbox_replay", "replay_dead_event")
    repository = MemoryOutboxRepository()
    pending = repository.seed(now=NOW, name="pending")
    completed = repository.seed(now=NOW, name="completed", state="completed")

    for event_id in (uuid4(), pending.id, completed.id):
        with pytest.raises((LookupError, RuntimeError), match="dead|event"):
            await replay(
                repository=repository,
                event_id=event_id,
                reason="operator_retry",
                requested_by_sub="authentik-user",
                now=NOW,
            )
    assert repository.replay_audit == []


@pytest.mark.asyncio
async def test_replay_hashes_actor_appends_audit_and_requeues_once() -> None:
    replay = required_symbol("services.outbox_replay", "replay_dead_event")
    repository = RecordingReplayRepository()
    event = repository.seed(
        now=NOW,
        name="dead-replay",
        state="dead",
        attempt_count=8,
    )
    previous_dead_at = event.dead_at
    actor = "authentik-sensitive-subject"

    replay_number = await replay(
        repository=repository,
        event_id=event.id,
        reason="operator_retry",
        requested_by_sub=actor,
        now=NOW,
    )

    assert replay_number == 1
    assert event.state == "pending"
    assert event.attempt_count == 0
    assert event.available_at == NOW
    assert event.replay_count == 1
    assert event.dead_at is None
    assert event.last_error_code is None
    assert repository.requested_actor_hash == sha256(actor.encode()).hexdigest()
    assert actor not in repr(repository.replay_audit)
    assert repository.replay_audit == [
        repository.replay_audit[0]
    ]
    audit = repository.replay_audit[0]
    assert audit.event_id == event.id
    assert audit.replay_number == 1
    assert audit.previous_attempt_count == 8
    assert audit.previous_dead_at == previous_dead_at
    assert audit.reason == "operator_retry"
    assert audit.requested_at == NOW

    with pytest.raises(RuntimeError, match="dead"):
        await replay(
            repository=repository,
            event_id=event.id,
            reason="operator_retry",
            requested_by_sub=actor,
            now=NOW,
        )
    assert len(repository.replay_audit) == 1
