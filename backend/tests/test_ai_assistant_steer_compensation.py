"""Definite runtime rejection compensation against canonical isolated PostgreSQL."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from auth import AuthClaims
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, UploadFile

from routers import ai_assistant as routes
from test_ai_assistant_persistence_db import (
    OWNER, clean_certification_owner, new_conversation, pytestmark, service_for,
)


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["accepted", "inactive", "finishing", "transport", "http500", "db_failure", "file_failure"])
async def test_steer_compensation(tmp_path: Path, monkeypatch, outcome: str) -> None:
    service, repo = await service_for(tmp_path)
    conversation_id = await new_conversation(service)
    await service.begin_user_message(
        OWNER, conversation_id, text="previous", effort="max",
        files=[UploadFile(filename="same.csv", file=BytesIO(b"previous"))],
    )
    await service.finish_assistant_message(
        OWNER, conversation_id, text="previous answer", previous_response_id="prior-response", artifacts=[],
    )
    before = dict(await repo.get_conversation(OWNER, conversation_id))
    prior_messages = await repo.list_messages(OWNER, conversation_id)
    prior_artifacts = await repo.list_artifacts(OWNER, conversation_id)
    previous_path = service.settings.storage_root / prior_artifacts[0]["storage_key"]
    completion_state = None

    async def post(*args, **kwargs):
        nonlocal completion_state
        if outcome == "finishing":
            await service.finish_assistant_message(
                OWNER, conversation_id, text="concurrent completion", previous_response_id="new-response", artifacts=[],
            )
            completion_state = dict(await repo.get_conversation(OWNER, conversation_id))
        if outcome == "transport":
            raise httpx.ReadTimeout("ambiguous response")
        code = 200 if outcome == "accepted" else 500 if outcome == "http500" else 409
        return httpx.Response(code)

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.side_effect = post
    monkeypatch.setattr(routes.httpx, "AsyncClient", lambda **kwargs: client)
    if outcome == "db_failure":
        # Real PostgreSQL failure after deletes must roll back the whole transaction.
        async with repo.pool.acquire() as conn:
            await conn.execute("""
                CREATE FUNCTION pg_temp.reject_compensation() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'forced compensation failure'; END $$;
                CREATE TRIGGER reject_compensation BEFORE UPDATE ON ai_assistant_conversations
                FOR EACH ROW WHEN (NEW.updated_at < OLD.updated_at)
                EXECUTE FUNCTION pg_temp.reject_compensation();
            """)
    if outcome == "file_failure":
        monkeypatch.setattr(Path, "unlink", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("forced unlink failure")))
    try:
        call = routes.steer(
            conversation_id, text="new steer", current_view=None,
            files=[UploadFile(filename="same.csv", file=BytesIO(b"new"))],
            claims=AuthClaims(OWNER, "owner@example.invalid", "user", [], "issuer", "audience", 0, 0, {}),
            service=service,
        )
        if outcome == "accepted":
            assert (await call).accepted
        else:
            with pytest.raises(HTTPException) as error:
                await call
            assert error.value.status_code == (409 if outcome in {"inactive", "finishing"} else 503)
            if outcome in {"db_failure", "file_failure"}:
                assert "anularea salvării" in error.value.detail
    finally:
        if outcome == "db_failure":
            await repo.pool.execute("DROP TRIGGER reject_compensation ON ai_assistant_conversations")

    messages = await repo.list_messages(OWNER, conversation_id)
    artifacts = await repo.list_artifacts(OWNER, conversation_id)
    after = dict(await repo.get_conversation(OWNER, conversation_id))
    assert messages[:2] == prior_messages
    assert artifacts[0] == prior_artifacts[0]
    assert previous_path.read_bytes() == b"previous"
    assert after["title"] == before["title"]
    assert after["effort"] == before["effort"]
    compensated = outcome in {"inactive", "finishing", "file_failure"}
    assert any(row["text"] == "new steer" for row in messages) is not compensated
    assert len(artifacts) == (1 if compensated else 2)
    host_files = list(service.settings.storage_root.rglob("same.csv"))
    assert len(host_files) == (1 if outcome in {"inactive", "finishing"} else 2)
    if compensated:
        assert after == (completion_state or before)
    else:
        assert after["previous_response_id"] == "prior-response"


@pytest.mark.anyio
async def test_rejected_steers_preserve_empty_conversation_and_other_owner(tmp_path: Path) -> None:
    service, repo = await service_for(tmp_path)
    conversation_id = await new_conversation(service)
    before = dict(await repo.get_conversation(OWNER, conversation_id))
    submissions = [await service.begin_user_message(
        OWNER, conversation_id, text=text, effort="max", files=[], steer=True,
    ) for text in ("first rejected", "second rejected")]
    with pytest.raises(LookupError):
        await service.compensate_rejected_steer("other-owner", conversation_id, submissions[0][0].id)
    assert len(await repo.list_messages(OWNER, conversation_id)) == 2
    for submission in submissions:
        await service.compensate_rejected_steer(OWNER, conversation_id, submission[0].id)
    assert await repo.list_messages(OWNER, conversation_id) == []
    assert dict(await repo.get_conversation(OWNER, conversation_id)) == before
