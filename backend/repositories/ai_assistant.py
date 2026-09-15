from __future__ import annotations

from typing import Any
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

    async def create_user_submission(
        self,
        owner_subject: str,
        conversation_id: UUID,
        message_id: UUID,
        *,
        text: str,
        effort: str,
        title: str | None,
        artifacts: list[dict[str, Any]],
        steer: bool = False,
    ) -> tuple[asyncpg.Record, asyncpg.Record, list[asyncpg.Record]] | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                conversation = await conn.fetchrow(
                    """
                    SELECT id, title, effort, previous_response_id, created_at, updated_at
                    FROM ai_assistant_conversations
                    WHERE id = $1 AND owner_subject = $2
                    FOR UPDATE
                    """,
                    conversation_id,
                    owner_subject,
                )
                if conversation is None:
                    return None
                message = await conn.fetchrow(
                    """
                    INSERT INTO ai_assistant_messages (
                        id, conversation_id, role, text, status
                    )
                    VALUES ($1, $2, 'user', $3, 'complete')
                    RETURNING id, conversation_id, ordinal, role, text, status, created_at
                    """,
                    message_id,
                    conversation_id,
                    text,
                )
                assert message is not None
                artifact_rows: list[asyncpg.Record] = []
                for artifact in artifacts:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO ai_assistant_artifacts (
                            id, conversation_id, message_id, filename, mime_type,
                            size_bytes, storage_key, kind
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'input')
                        RETURNING id, conversation_id, message_id, filename, mime_type,
                                  size_bytes, storage_key, kind, created_at
                        """,
                        artifact["id"],
                        conversation_id,
                        message_id,
                        artifact["filename"],
                        artifact["mime_type"],
                        artifact["size_bytes"],
                        artifact["storage_key"],
                    )
                    assert row is not None
                    artifact_rows.append(row)
                await conn.execute(
                    """
                    UPDATE ai_assistant_conversations
                    SET effort = $3,
                        title = COALESCE($4, title),
                        updated_at = now()
                    WHERE id = $1 AND owner_subject = $2
                    """,
                    conversation_id,
                    owner_subject,
                    conversation["effort"] if steer else effort,
                    None if steer else title,
                )
                return conversation, message, artifact_rows

    async def compensate_rejected_submission(
        self, owner_subject: str, conversation_id: UUID, message_id: UUID,
    ) -> list[str]:
        """Remove one definitely rejected submission, retaining concurrent work."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                owned = await conn.fetchval(
                    """
                    SELECT 1 FROM ai_assistant_conversations
                    WHERE id = $1 AND owner_subject = $2 FOR UPDATE
                    """, conversation_id, owner_subject,
                )
                if owned is None:
                    raise LookupError("AI compensation conversation not found")
                submission = await conn.fetchval(
                    """
                    SELECT 1 FROM ai_assistant_messages
                    WHERE id = $1 AND conversation_id = $2 AND role = 'user'
                    """, message_id, conversation_id,
                )
                if submission is None:
                    raise LookupError("AI compensation submission not found")
                deleted = await conn.fetch(
                    """
                    DELETE FROM ai_assistant_artifacts
                    WHERE conversation_id = $1 AND message_id = $2 AND kind = 'input'
                    RETURNING storage_key
                    """, conversation_id, message_id,
                )
                await conn.execute(
                    """
                    DELETE FROM ai_assistant_messages
                    WHERE conversation_id = $1 AND id = $2 AND role = 'user'
                    """, conversation_id, message_id,
                )
                await conn.execute(
                    """
                    UPDATE ai_assistant_conversations AS c
                    SET updated_at = GREATEST(c.created_at, (
                        SELECT max(created_at) FROM ai_assistant_messages
                        WHERE conversation_id = c.id
                    ))
                    WHERE c.id = $1 AND c.owner_subject = $2
                    """, conversation_id, owner_subject,
                )
            # Returning outside the transaction ensures host cleanup follows COMMIT.
            return [row["storage_key"] for row in deleted]

    async def create_assistant_completion(
        self,
        owner_subject: str,
        conversation_id: UUID,
        message_id: UUID,
        *,
        text: str,
        status: str,
        previous_response_id: str | None,
        artifacts: list[dict[str, Any]],
    ) -> tuple[asyncpg.Record, list[asyncpg.Record]] | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                owned = await conn.fetchval(
                    """
                    SELECT 1
                    FROM ai_assistant_conversations
                    WHERE id = $1 AND owner_subject = $2
                    FOR UPDATE
                    """,
                    conversation_id,
                    owner_subject,
                )
                if owned is None:
                    return None
                message = await conn.fetchrow(
                    """
                    INSERT INTO ai_assistant_messages (
                        id, conversation_id, role, text, status
                    )
                    VALUES ($1, $2, 'assistant', $3, $4)
                    RETURNING id, conversation_id, ordinal, role, text, status, created_at
                    """,
                    message_id,
                    conversation_id,
                    text,
                    status,
                )
                assert message is not None
                artifact_rows: list[asyncpg.Record] = []
                for artifact in artifacts:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO ai_assistant_artifacts (
                            id, conversation_id, message_id, filename, mime_type,
                            size_bytes, storage_key, kind
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'output')
                        RETURNING id, conversation_id, message_id, filename, mime_type,
                                  size_bytes, storage_key, kind, created_at
                        """,
                        artifact["id"],
                        conversation_id,
                        message_id,
                        artifact["filename"],
                        artifact["mime_type"],
                        artifact["size_bytes"],
                        artifact["storage_key"],
                    )
                    assert row is not None
                    artifact_rows.append(row)
                await conn.execute(
                    """
                    UPDATE ai_assistant_conversations
                    SET previous_response_id = $3,
                        updated_at = now()
                    WHERE id = $1 AND owner_subject = $2
                    """,
                    conversation_id,
                    owner_subject,
                    previous_response_id,
                )
                return message, artifact_rows

    async def create_error_message(
        self,
        owner_subject: str,
        conversation_id: UUID,
        message_id: UUID,
        *,
        text: str,
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                INSERT INTO ai_assistant_messages (
                    id, conversation_id, role, text, status
                )
                SELECT $3, c.id, 'assistant', $4, 'error'
                FROM ai_assistant_conversations AS c
                WHERE c.id = $1 AND c.owner_subject = $2
                RETURNING id, conversation_id, ordinal, role, text, status, created_at
                """,
                conversation_id,
                owner_subject,
                message_id,
                text,
            )

    async def list_messages(
        self, owner_subject: str, conversation_id: UUID
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT m.id, m.conversation_id, m.ordinal, m.role, m.text,
                       m.status, m.created_at
                FROM ai_assistant_messages AS m
                JOIN ai_assistant_conversations AS c ON c.id = m.conversation_id
                WHERE m.conversation_id = $1 AND c.owner_subject = $2
                ORDER BY m.ordinal ASC
                """,
                conversation_id,
                owner_subject,
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
