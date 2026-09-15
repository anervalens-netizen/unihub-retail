from __future__ import annotations

from uuid import UUID

import asyncpg


class AiAssistantRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def list_conversations(self, owner_subject: str, limit: int = 30) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, title, effort, previous_response_id, created_at, updated_at
                FROM ai_assistant_conversations
                WHERE owner_subject = $1
                ORDER BY updated_at DESC, created_at DESC
                LIMIT $2
                """,
                owner_subject,
                limit,
            )

    async def create_conversation(
        self, owner_subject: str, conversation_id: UUID, effort: str
    ) -> asyncpg.Record:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ai_assistant_conversations (id, owner_subject, effort)
                VALUES ($1, $2, $3)
                RETURNING id, title, effort, previous_response_id, created_at, updated_at
                """,
                conversation_id,
                owner_subject,
                effort,
            )
        assert row is not None
        return row

    async def get_conversation(
        self, owner_subject: str, conversation_id: UUID
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, title, effort, previous_response_id, created_at, updated_at
                FROM ai_assistant_conversations
                WHERE id = $1 AND owner_subject = $2
                """,
                conversation_id,
                owner_subject,
            )

    async def update_conversation(
        self,
        owner_subject: str,
        conversation_id: UUID,
        *,
        effort: str | None = None,
        title: str | None = None,
        previous_response_id: str | None = None,
        set_previous_response_id: bool = False,
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                UPDATE ai_assistant_conversations
                SET effort = COALESCE($3, effort),
                    title = COALESCE($4, title),
                    previous_response_id = CASE WHEN $5 THEN $6 ELSE previous_response_id END,
                    updated_at = now()
                WHERE id = $1 AND owner_subject = $2
                RETURNING id, title, effort, previous_response_id, created_at, updated_at
                """,
                conversation_id,
                owner_subject,
                effort,
                title,
                set_previous_response_id,
                previous_response_id,
            )

    async def create_message(
        self,
        owner_subject: str,
        conversation_id: UUID,
        message_id: UUID,
        *,
        role: str,
        text: str,
        status: str,
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                INSERT INTO ai_assistant_messages (id, conversation_id, role, text, status)
                SELECT $3, c.id, $4, $5, $6
                FROM ai_assistant_conversations AS c
                WHERE c.id = $1 AND c.owner_subject = $2
                RETURNING id, conversation_id, role, text, status, created_at
                """,
                conversation_id,
                owner_subject,
                message_id,
                role,
                text,
                status,
            )

    async def list_messages(
        self, owner_subject: str, conversation_id: UUID
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT m.id, m.conversation_id, m.role, m.text, m.status, m.created_at
                FROM ai_assistant_messages AS m
                JOIN ai_assistant_conversations AS c ON c.id = m.conversation_id
                WHERE m.conversation_id = $1 AND c.owner_subject = $2
                ORDER BY m.created_at ASC, m.id ASC
                """,
                conversation_id,
                owner_subject,
            )

    async def create_artifact(
        self,
        owner_subject: str,
        *,
        artifact_id: UUID,
        conversation_id: UUID,
        message_id: UUID | None,
        filename: str,
        mime_type: str,
        size_bytes: int,
        storage_key: str,
        kind: str,
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                INSERT INTO ai_assistant_artifacts (
                    id, conversation_id, message_id, filename, mime_type,
                    size_bytes, storage_key, kind
                )
                SELECT $3, c.id, $4, $5, $6, $7, $8, $9
                FROM ai_assistant_conversations AS c
                WHERE c.id = $1 AND c.owner_subject = $2
                RETURNING id, conversation_id, message_id, filename, mime_type,
                          size_bytes, storage_key, kind, created_at
                """,
                conversation_id,
                owner_subject,
                artifact_id,
                message_id,
                filename,
                mime_type,
                size_bytes,
                storage_key,
                kind,
            )

    async def list_artifacts(
        self, owner_subject: str, conversation_id: UUID
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT a.id, a.conversation_id, a.message_id, a.filename,
                       a.mime_type, a.size_bytes, a.storage_key, a.kind, a.created_at
                FROM ai_assistant_artifacts AS a
                JOIN ai_assistant_conversations AS c ON c.id = a.conversation_id
                WHERE a.conversation_id = $1 AND c.owner_subject = $2
                ORDER BY a.created_at ASC, a.id ASC
                """,
                conversation_id,
                owner_subject,
            )

    async def get_artifact(
        self, owner_subject: str, artifact_id: UUID
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT a.id, a.conversation_id, a.message_id, a.filename,
                       a.mime_type, a.size_bytes, a.storage_key, a.kind, a.created_at
                FROM ai_assistant_artifacts AS a
                JOIN ai_assistant_conversations AS c ON c.id = a.conversation_id
                WHERE a.id = $1 AND c.owner_subject = $2
                """,
                artifact_id,
                owner_subject,
            )
