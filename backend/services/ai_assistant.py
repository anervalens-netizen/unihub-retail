from __future__ import annotations

import mimetypes
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4

from fastapi import UploadFile

from ai_assistant.settings import AiAssistantSettings, resolve_storage_key
from repositories.ai_assistant import AiAssistantRepository
from schemas.ai_assistant import (
    AiArtifactItem,
    AiConversationItem,
    AiMessageItem,
    AiReasoningEffort,
    RuntimeArtifact,
    RuntimeUpload,
)

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._() -]+")


class AiConversationNotFound(LookupError):
    pass


class AiArtifactNotFound(LookupError):
    pass


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip()
    name = _SAFE_FILENAME_RE.sub("_", name).strip(" .")
    if not name:
        return "file.bin"
    return name[:180].rstrip(" .") or "file.bin"


class AiAssistantService:
    def __init__(self, repo: AiAssistantRepository, settings: AiAssistantSettings):
        self.repo = repo
        self.settings = settings

    @staticmethod
    def _conversation(row: Any) -> AiConversationItem:
        return AiConversationItem(
            id=row["id"],
            title=row["title"],
            effort=row["effort"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _artifact(row: Any) -> AiArtifactItem:
        artifact_id = row["id"]
        return AiArtifactItem(
            id=artifact_id,
            filename=row["filename"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            kind=row["kind"],
            download_url=f"/api/ai/artifacts/{artifact_id}/download",
            created_at=row["created_at"],
        )

    @staticmethod
    def _message(row: Any, attachments: list[AiArtifactItem] | None = None) -> AiMessageItem:
        return AiMessageItem(
            id=row["id"],
            role=row["role"],
            text=row["text"],
            status=row["status"],
            created_at=row["created_at"],
            attachments=attachments or [],
        )

    def _remove_storage_keys(self, storage_keys: list[str]) -> None:
        for storage_key in storage_keys:
            try:
                path = resolve_storage_key(self.settings.storage_root, storage_key)
                path.unlink(missing_ok=True)
                parent = path.parent
                if parent != self.settings.storage_root:
                    try:
                        parent.rmdir()
                    except OSError:
                        pass
            except (OSError, ValueError):
                continue

    async def list_conversations(self, owner_subject: str) -> list[AiConversationItem]:
        rows = await self.repo.list_conversations(owner_subject)
        return [self._conversation(row) for row in rows]

    async def create_conversation(
        self, owner_subject: str, effort: AiReasoningEffort
    ) -> AiConversationItem:
        row = await self.repo.create_conversation(owner_subject, uuid4(), effort)
        return self._conversation(row)

    async def require_conversation(self, owner_subject: str, conversation_id: UUID):
        row = await self.repo.get_conversation(owner_subject, conversation_id)
        if row is None:
            raise AiConversationNotFound
        return row

    async def list_messages(
        self, owner_subject: str, conversation_id: UUID
    ) -> list[AiMessageItem]:
        await self.require_conversation(owner_subject, conversation_id)
        rows = await self.repo.list_messages(owner_subject, conversation_id)
        artifacts = await self.repo.list_artifacts(owner_subject, conversation_id)
        grouped: dict[UUID, list[AiArtifactItem]] = {}
        for row in artifacts:
            message_id = row["message_id"]
            if message_id is not None:
                grouped.setdefault(message_id, []).append(self._artifact(row))
        return [
            self._message(row, grouped.get(row["id"], []))
            for row in rows
        ]

    async def begin_user_message(
        self,
        owner_subject: str,
        conversation_id: UUID,
        *,
        text: str,
        effort: AiReasoningEffort,
        files: list[UploadFile],
        steer: bool = False,
    ) -> tuple[AiMessageItem, list[RuntimeUpload], str | None, int]:
        conversation = await self.require_conversation(owner_subject, conversation_id)
        prepared: list[dict[str, Any]] = []
        runtime_uploads: list[RuntimeUpload] = []
        written_keys: list[str] = []
        try:
            for upload in files:
                artifact_id = uuid4()
                filename = _safe_filename(upload.filename or "upload.bin")
                payload = await upload.read()
                if len(payload) > self.settings.max_artifact_bytes:
                    raise ValueError(f"{filename} exceeds AI artifact size limit")
                storage_key = (
                    Path("input") / str(conversation_id) / str(artifact_id) / filename
                ).as_posix()
                target = resolve_storage_key(self.settings.storage_root, storage_key)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                written_keys.append(storage_key)
                mime_type = (
                    upload.content_type
                    or mimetypes.guess_type(filename)[0]
                    or "application/octet-stream"
                )
                prepared.append(
                    {
                        "id": artifact_id,
                        "filename": filename,
                        "mime_type": mime_type,
                        "size_bytes": len(payload),
                        "storage_key": storage_key,
                    }
                )
                runtime_uploads.append(
                    RuntimeUpload(
                        storage_key=storage_key,
                        sandbox_name=f"{artifact_id.hex[:12]}-{filename}",
                    )
                )

            title: str | None = None
            if conversation["title"] == "Conversație nouă" and text.strip():
                title = text.strip().replace("\n", " ")[:80]
            created = await self.repo.create_user_submission(
                owner_subject,
                conversation_id,
                uuid4(),
                text=text,
                effort=effort,
                title=title,
                artifacts=prepared,
                steer=steer,
            )
            if created is None:
                raise AiConversationNotFound
            prior_conversation, message_row, artifact_rows = created
            attachments = [self._artifact(row) for row in artifact_rows]
            return (
                self._message(message_row, attachments),
                runtime_uploads,
                prior_conversation["previous_response_id"],
                int(message_row["ordinal"]),
            )
        except Exception:
            self._remove_storage_keys(written_keys)
            raise

    async def compensate_rejected_submission(
        self, owner_subject: str, conversation_id: UUID, message_id: UUID,
    ) -> None:
        storage_keys = await self.repo.compensate_rejected_submission(
            owner_subject, conversation_id, message_id,
        )
        # Unlike best-effort cleanup during submission failure, failures here must
        # reach the caller. Never delete host files before metadata COMMIT succeeds.
        for storage_key in storage_keys:
            resolve_storage_key(self.settings.storage_root, storage_key).unlink(missing_ok=True)

    async def finish_assistant_message(
        self,
        owner_subject: str,
        conversation_id: UUID,
        *,
        text: str,
        previous_response_id: str | None,
        artifacts: list[RuntimeArtifact],
        status: str = "complete",
    ) -> AiMessageItem:
        prepared = [
            {
                "id": artifact.id,
                "filename": _safe_filename(artifact.filename),
                "mime_type": artifact.mime_type,
                "size_bytes": artifact.size_bytes,
                "storage_key": artifact.storage_key,
            }
            for artifact in artifacts
        ]
        storage_keys = [artifact.storage_key for artifact in artifacts]
        try:
            created = await self.repo.create_assistant_completion(
                owner_subject,
                conversation_id,
                uuid4(),
                text=text,
                status=status,
                previous_response_id=previous_response_id,
                artifacts=prepared,
            )
            if created is None:
                raise AiConversationNotFound
            message_row, artifact_rows = created
            return self._message(
                message_row,
                [self._artifact(row) for row in artifact_rows],
            )
        except Exception:
            self._remove_storage_keys(storage_keys)
            raise

    async def record_error_message(
        self,
        owner_subject: str,
        conversation_id: UUID,
        text: str,
    ) -> AiMessageItem | None:
        row = await self.repo.create_error_message(
            owner_subject,
            conversation_id,
            uuid4(),
            text=text,
        )
        return None if row is None else self._message(row)

    async def artifact_path(
        self, owner_subject: str, artifact_id: UUID
    ) -> tuple[Path, str, str]:
        row = await self.repo.get_artifact(owner_subject, artifact_id)
        if row is None:
            raise AiArtifactNotFound
        path = resolve_storage_key(self.settings.storage_root, row["storage_key"])
        if not path.is_file():
            raise AiArtifactNotFound
        return path, row["filename"], row["mime_type"]
