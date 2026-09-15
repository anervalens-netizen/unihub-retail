from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from schemas.common import StrictApiModel

AiReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
AiMessageRole = Literal["user", "assistant", "system"]
AiMessageStatus = Literal["complete", "streaming", "error", "stopped"]
AiArtifactKind = Literal["input", "output"]
RUNTIME_ADMISSION_REJECTION_MESSAGE = "A run is already active for this conversation."


class AiArtifactItem(StrictApiModel):
    id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    kind: AiArtifactKind
    download_url: str
    created_at: datetime


class AiMessageItem(StrictApiModel):
    id: UUID
    role: AiMessageRole
    text: str
    status: AiMessageStatus
    created_at: datetime
    attachments: list[AiArtifactItem] = Field(default_factory=list)


class AiConversationItem(StrictApiModel):
    id: UUID
    title: str
    effort: AiReasoningEffort
    created_at: datetime
    updated_at: datetime


class AiConversationListResponse(StrictApiModel):
    items: list[AiConversationItem]


class AiMessageListResponse(StrictApiModel):
    items: list[AiMessageItem]


class AiConversationCreate(StrictApiModel):
    effort: AiReasoningEffort = "high"


class AiStopResponse(StrictApiModel):
    ok: bool


class AiSteerResponse(StrictApiModel):
    accepted: bool
    message: AiMessageItem


class RuntimeUpload(StrictApiModel):
    storage_key: str
    sandbox_name: str


class RuntimeTurnRequest(StrictApiModel):
    conversation_id: UUID
    owner_subject: str = Field(min_length=1, max_length=256)
    text: str
    effort: AiReasoningEffort
    previous_response_id: str | None = None
    order_key: int = Field(ge=1)
    current_view: dict[str, Any] | None = None
    uploads: list[RuntimeUpload] = Field(default_factory=list)


class RuntimeSteerRequest(StrictApiModel):
    text: str
    order_key: int = Field(ge=1)
    previous_order_key: int | None = Field(default=None, ge=1)
    current_view: dict[str, Any] | None = None
    uploads: list[RuntimeUpload] = Field(default_factory=list)


class RuntimeArtifact(StrictApiModel):
    id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    storage_key: str


class RuntimeCompleteEvent(StrictApiModel):
    type: Literal["complete"] = "complete"
    text: str
    previous_response_id: str | None = None
    artifacts: list[RuntimeArtifact] = Field(default_factory=list)
