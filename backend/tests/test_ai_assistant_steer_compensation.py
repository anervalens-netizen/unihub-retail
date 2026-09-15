"""Definite runtime rejection compensation against canonical isolated PostgreSQL."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
from typing import Any
from auth import AuthClaims
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, UploadFile

from routers import ai_assistant as routes
from schemas.ai_assistant import RUNTIME_ADMISSION_REJECTION_MESSAGE, RuntimeTurnRequest
from test_ai_assistant_persistence_db import (
    OWNER, clean_certification_owner, new_conversation, pytestmark, service_for,
)


@dataclass
class _SteerSnapshot:
    conversation_id: Any
    before: dict
    prior_messages: list
    prior_artifacts: list
    previous_path: Path
    completion: list


async def _snapshot_prior_state(service: Any, repo: Any) -> _SteerSnapshot:
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
    return _SteerSnapshot(conversation_id, before, prior_messages, prior_artifacts, previous_path, [])


def _install_steer_transport(monkeypatch: Any, service: Any, repo: Any, conversation_id: Any, outcome: str) -> list:
    completion: list = []

    async def post(*args, **kwargs):
        if outcome == "finishing":
            await service.finish_assistant_message(
                OWNER, conversation_id, text="concurrent completion", previous_response_id="new-response", artifacts=[],
            )
            completion.append(dict(await repo.get_conversation(OWNER, conversation_id)))
        if outcome == "transport":
            raise httpx.ReadTimeout("ambiguous response")
        code = 200 if outcome == "accepted" else 500 if outcome == "http500" else 409
        return httpx.Response(code)

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.side_effect = post
    monkeypatch.setattr(routes.httpx, "AsyncClient", lambda **kwargs: client)
    return completion


async def _install_compensation_failure(repo: Any, monkeypatch: Any, outcome: str) -> None:
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


async def _run_rejected_steer(service: Any, conversation_id: Any, outcome: str) -> None:
    call = routes.steer(
        conversation_id, text="new steer", current_view=None,
        files=[UploadFile(filename="same.csv", file=BytesIO(b"new"))],
        claims=AuthClaims(OWNER, "owner@example.invalid", "user", [], "issuer", "audience", 0, 0, {}),
        service=service,
    )
    if outcome == "accepted":
        assert (await call).accepted
        return
    with pytest.raises(HTTPException) as error:
        await call
    assert error.value.status_code == (409 if outcome in {"inactive", "finishing"} else 503)
    if outcome in {"db_failure", "file_failure"}:
        assert "anularea salvării" in error.value.detail


async def _assert_compensation_preserved(repo: Any, service: Any, outcome: str, snapshot: _SteerSnapshot) -> None:
    messages = await repo.list_messages(OWNER, snapshot.conversation_id)
    artifacts = await repo.list_artifacts(OWNER, snapshot.conversation_id)
    after = dict(await repo.get_conversation(OWNER, snapshot.conversation_id))
    assert messages[:2] == snapshot.prior_messages
    assert artifacts[0] == snapshot.prior_artifacts[0]
    assert snapshot.previous_path.read_bytes() == b"previous"
    assert after["title"] == snapshot.before["title"]
    assert after["effort"] == snapshot.before["effort"]
    compensated = outcome in {"inactive", "finishing", "file_failure"}
    assert any(row["text"] == "new steer" for row in messages) is not compensated
    assert len(artifacts) == (1 if compensated else 2)
    host_files = list(service.settings.storage_root.rglob("same.csv"))
    assert len(host_files) == (1 if outcome in {"inactive", "finishing"} else 2)
    if compensated:
        assert after == (snapshot.completion[0] if snapshot.completion else snapshot.before)
    else:
        assert after["previous_response_id"] == "prior-response"


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["accepted", "inactive", "finishing", "transport", "http500", "db_failure", "file_failure"])
async def test_steer_compensation(tmp_path: Path, monkeypatch, outcome: str) -> None:
    service, repo = await service_for(tmp_path)
    snapshot = await _snapshot_prior_state(service, repo)
    snapshot.completion = _install_steer_transport(monkeypatch, service, repo, snapshot.conversation_id, outcome)
    await _install_compensation_failure(repo, monkeypatch, outcome)
    try:
        await _run_rejected_steer(service, snapshot.conversation_id, outcome)
    finally:
        if outcome == "db_failure":
            await repo.pool.execute("DROP TRIGGER reject_compensation ON ai_assistant_conversations")
    await _assert_compensation_preserved(repo, service, outcome, snapshot)


@pytest.mark.anyio
async def test_rejected_steers_preserve_empty_conversation_and_other_owner(tmp_path: Path) -> None:
    service, repo = await service_for(tmp_path)
    conversation_id = await new_conversation(service)
    before = dict(await repo.get_conversation(OWNER, conversation_id))
    submissions = [await service.begin_user_message(
        OWNER, conversation_id, text=text, effort="max", files=[], steer=True,
    ) for text in ("first rejected", "second rejected")]
    with pytest.raises(LookupError):
        await service.compensate_rejected_submission("other-owner", conversation_id, submissions[0][0].id)
    assert len(await repo.list_messages(OWNER, conversation_id)) == 2
    for submission in submissions:
        await service.compensate_rejected_submission(OWNER, conversation_id, submission[0].id)
    assert await repo.list_messages(OWNER, conversation_id) == []
    assert dict(await repo.get_conversation(OWNER, conversation_id)) == before


class _AdmissionRejectedResponse:
    status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def aiter_lines(self):
        yield json.dumps({"type": "error", "message": RUNTIME_ADMISSION_REJECTION_MESSAGE})


class _AdmissionRejectedClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def stream(self, *args, **kwargs):
        return _AdmissionRejectedResponse()


@pytest.mark.anyio
async def test_rejected_turn_compensates_exact_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repo = await service_for(tmp_path)
    conversation_id = await new_conversation(service)
    user_message, uploads, previous_response_id, order_key, _ = await service.begin_user_message(
        OWNER,
        conversation_id,
        text="rejected turn",
        effort="max",
        files=[UploadFile(filename="turn.csv", file=BytesIO(b"turn"))],
    )
    stored_path = service.settings.storage_root / uploads[0].storage_key
    monkeypatch.setattr(routes.httpx, "AsyncClient", lambda **kwargs: _AdmissionRejectedClient())
    payload = RuntimeTurnRequest(
        conversation_id=conversation_id,
        owner_subject=OWNER,
        text="rejected turn",
        effort="max",
        previous_response_id=previous_response_id,
        order_key=order_key,
        current_view=None,
        uploads=uploads,
    )

    events = [
        json.loads(line)
        async for line in routes._stream_runtime_events(
            service=service,
            owner_subject=OWNER,
            conversation_id=conversation_id,
            runtime_url="http://runtime/internal/ai/run",
            payload=payload,
            user_message=user_message,
        )
    ]

    assert events[-1] == {"type": "error", "message": RUNTIME_ADMISSION_REJECTION_MESSAGE}
    assert await repo.list_messages(OWNER, conversation_id) == []
    assert await repo.list_artifacts(OWNER, conversation_id) == []
    assert (await repo.get_conversation(OWNER, conversation_id))["previous_response_id"] is None
    assert not stored_path.exists()
