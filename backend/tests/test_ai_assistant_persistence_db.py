"""Isolated-database certification for AI assistant persistence.

Covers the V3 AI durability contract:
* deterministic message ordering through the BIGSERIAL ``ordinal``;
* one transaction for user submission metadata (message + artifact metadata);
* one transaction for assistant completion (message + artifact metadata +
  ``previous_response_id``);
* host-side file cleanup when a metadata transaction fails.

Run only against a disposable isolated PostgreSQL (see ``UNIHUB_TEST_DATABASE``).
These tests are destructive by design and never touch production.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest

from ai_assistant.settings import AiAssistantSettings
from db.connection import get_database_url, get_pool
from repositories.ai_assistant import AiAssistantRepository
from services.ai_assistant import AiAssistantService

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="AI persistence certification requires an isolated PostgreSQL database",
)

OWNER = "cert-owner-subject"


def build_settings(tmp_path: Path) -> AiAssistantSettings:
    storage = tmp_path / "store"
    snapshots = storage / "snapshots"
    storage.mkdir(parents=True, exist_ok=True)
    snapshots.mkdir(parents=True, exist_ok=True)
    return AiAssistantSettings(
        model="gpt-5.6-luna",
        runtime_url="http://127.0.0.1:9911",
        storage_root=storage,
        snapshot_root=snapshots,
        knowledge_root=tmp_path / "knowledge",
        sandbox_image="unihub-retail-ai-sandbox:test",
        max_artifact_bytes=8 * 1024 * 1024,
        setup_timeout_seconds=90,
    )


async def service_for(tmp_path: Path) -> tuple[AiAssistantService, AiAssistantRepository]:
    repo = AiAssistantRepository(await get_pool())
    return AiAssistantService(repo, build_settings(tmp_path)), repo


async def new_conversation(service: AiAssistantService) -> UUID:
    conversation = await service.create_conversation(OWNER, "high")
    return conversation.id


def artifact(storage_key: str) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "filename": "probe.csv",
        "mime_type": "text/csv",
        "size_bytes": 12,
        "storage_key": storage_key,
    }


@pytest.fixture(autouse=True)
async def clean_certification_owner():
    """Keep the isolated database deterministic across reruns."""
    yield
    try:
        pool = await get_pool()
    except Exception:  # pragma: no cover - pool unavailable means nothing to clean
        return
    await pool.execute(
        "DELETE FROM ai_assistant_conversations WHERE owner_subject = $1", OWNER
    )


@pytest.mark.anyio
async def test_message_retrieval_follows_durable_ordinal_order(tmp_path: Path) -> None:
    service, repo = await service_for(tmp_path)
    conversation_id = await new_conversation(service)
    pool = await get_pool()

    # Concurrent user submissions with deliberately identical timestamps: only the
    # sequence-issued ordinal can define retrieval order.
    async def submit(index: int) -> None:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO ai_assistant_messages (
                        id, conversation_id, role, text, status, created_at
                    )
                    VALUES ($1, $2, 'user', $3, 'complete', TIMESTAMPTZ '2026-09-15 10:00:00+00')
                    """,
                    uuid4(),
                    conversation_id,
                    f"concurrent-{index}",
                )

    await asyncio.gather(*(submit(index) for index in range(8)))

    rows = await repo.list_messages(OWNER, conversation_id)
    ordinals = [int(row["ordinal"]) for row in rows]
    assert ordinals == sorted(ordinals)
    assert len(ordinals) == 8
    assert len(set(ordinals)) == 8


@pytest.mark.anyio
async def test_user_submission_metadata_is_one_transaction(tmp_path: Path) -> None:
    service, repo = await service_for(tmp_path)
    conversation_id = await new_conversation(service)
    before = await repo.get_conversation(OWNER, conversation_id)
    assert before is not None

    duplicated = f"input/shared/{uuid4().hex}/artifact/dup.csv"
    with pytest.raises(asyncpg.UniqueViolationError):
        await repo.create_user_submission(
            OWNER,
            conversation_id,
            uuid4(),
            text="trebuie să fie atomic",
            effort="max",
            title="titlu nou",
            artifacts=[artifact(duplicated), artifact(duplicated)],
        )

    # Neither the user message nor any artifact metadata partially committed...
    messages = await repo.list_messages(OWNER, conversation_id)
    assert messages == []
    artifacts = await repo.list_artifacts(OWNER, conversation_id)
    assert artifacts == []
    # ...and the conversation update rolled back with them.
    after = await repo.get_conversation(OWNER, conversation_id)
    assert after is not None
    assert after["title"] == before["title"]
    assert after["effort"] == before["effort"]
    assert after["updated_at"] == before["updated_at"]


@pytest.mark.anyio
async def test_assistant_completion_and_continuation_roll_back_together(
    tmp_path: Path,
) -> None:
    service, repo = await service_for(tmp_path)
    conversation_id = await new_conversation(service)

    submitted = await repo.create_user_submission(
        OWNER,
        conversation_id,
        uuid4(),
        text="prima întrebare",
        effort="high",
        title=None,
        artifacts=[],
    )
    assert submitted is not None
    original_continuation = submitted[0]["previous_response_id"]

    duplicated = f"output/shared/{uuid4().hex}/artifact/dup.xlsx"
    with pytest.raises(asyncpg.UniqueViolationError):
        await repo.create_assistant_completion(
            OWNER,
            conversation_id,
            uuid4(),
            text="răspuns",
            status="complete",
            previous_response_id="resp-should-not-persist",
            artifacts=[artifact(duplicated), artifact(duplicated)],
        )

    messages = await repo.list_messages(OWNER, conversation_id)
    assert [row["role"] for row in messages] == ["user"]
    conversation = await repo.get_conversation(OWNER, conversation_id)
    assert conversation is not None
    assert conversation["previous_response_id"] == original_continuation
    assert await repo.list_artifacts(OWNER, conversation_id) == []


@pytest.mark.anyio
async def test_duplicate_artifact_storage_key_is_rejected_across_calls(
    tmp_path: Path,
) -> None:
    service, repo = await service_for(tmp_path)
    conversation_id = await new_conversation(service)
    key = f"input/cross/{uuid4().hex}/artifact/unique.csv"

    first = await repo.create_user_submission(
        OWNER,
        conversation_id,
        uuid4(),
        text="prima",
        effort="high",
        title=None,
        artifacts=[artifact(key)],
    )
    assert first is not None

    with pytest.raises(asyncpg.UniqueViolationError):
        await repo.create_user_submission(
            OWNER,
            conversation_id,
            uuid4(),
            text="a doua",
            effort="high",
            title=None,
            artifacts=[artifact(key)],
        )

    messages = await repo.list_messages(OWNER, conversation_id)
    assert len(messages) == 1


@pytest.mark.anyio
async def test_host_files_are_removed_when_metadata_transaction_fails(
    tmp_path: Path,
) -> None:
    service, repo = await service_for(tmp_path)
    conversation_id = await new_conversation(service)

    class _Upload:
        def __init__(self, filename: str, payload: bytes) -> None:
            self.filename = filename
            self.content_type = "text/csv"
            self._payload = payload

        async def read(self) -> bytes:
            return self._payload

    class _FailingRepo:
        async def get_conversation(self, *_args: Any, **_kwargs: Any) -> Any:
            return await repo.get_conversation(OWNER, conversation_id)

        async def create_user_submission(self, *_args: Any, **_kwargs: Any) -> None:
            raise asyncpg.UniqueViolationError("forced metadata failure")

    failing = AiAssistantService(_FailingRepo(), service.settings)  # type: ignore[arg-type]

    with pytest.raises(asyncpg.UniqueViolationError):
        await failing.begin_user_message(
            OWNER,
            conversation_id,
            text="cu fișier",
            effort="high",
            files=[_Upload("probe.csv", b"store,value\nA,1\n")],  # type: ignore[list-item]
        )

    leftovers = [
        path
        for path in service.settings.storage_root.rglob("*")
        if path.is_file()
    ]
    assert leftovers == []
    assert await repo.list_messages(OWNER, conversation_id) == []


@pytest.mark.anyio
async def test_isolated_database_rejects_ai_table_writes_without_authority(
    tmp_path: Path,
) -> None:
    """The dedicated read-only identity must not mutate AI tables."""
    readonly_dsn = os.getenv("AI_ASSISTANT_READONLY_DSN")
    if not readonly_dsn:
        pytest.skip("AI_ASSISTANT_READONLY_DSN is not configured for this run")

    connection = await asyncpg.connect(readonly_dsn)
    try:
        for statement in (
            "INSERT INTO ai_assistant_conversations (id, owner_subject, title) "
            "VALUES (gen_random_uuid(), 'x', 'x')",
            "UPDATE ai_assistant_messages SET text = text WHERE false",
            "DELETE FROM ai_assistant_artifacts WHERE false",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await connection.execute(statement)

        # The same identity still reads the Retail read model successfully.
        assert await connection.fetchval("SELECT count(*) FROM stores") is not None
        assert (
            await connection.fetchval("SELECT count(*) FROM reporting_agent_month")
            is not None
        )
        assert await connection.fetchval("SELECT count(*) FROM store_targets") is not None
    finally:
        await connection.close()


@pytest.mark.anyio
async def test_database_url_is_the_isolated_test_database() -> None:
    # validate_test_database_url refuses production or a shared cluster.
    get_database_url()
