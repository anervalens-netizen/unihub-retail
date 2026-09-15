from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID, uuid4

from schemas.ai_assistant import RuntimeSteerRequest

RunPhase = Literal["setup", "running", "steering", "finishing", "stopping"]


@dataclass(slots=True)
class ActiveRun:
    """One reserved run slot for a conversation.

    The slot is created before Docker/session setup begins. This makes Stop and
    Steer observable during setup and gives cleanup an identity token so an old
    run can never remove a newer reservation.
    """

    token: UUID = field(default_factory=uuid4)
    phase: RunPhase = "setup"
    task: asyncio.Task[Any] | None = None
    sandbox: Any | None = None
    result: Any | None = None
    pending_steers: list[RuntimeSteerRequest] = field(default_factory=list)
    stop_requested: bool = False
    owner_subject: str = ""

    def queue_steer(self, request: RuntimeSteerRequest) -> None:
        self.pending_steers.append(request)
        self.pending_steers.sort(key=lambda item: item.order_key)
