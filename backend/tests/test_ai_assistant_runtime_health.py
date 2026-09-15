"""The AI runtime must not report healthy before the read-only DSN is verified.

The review finding: the runtime accepted any syntactically valid PostgreSQL DSN
and then handed it to arbitrary model-generated code. Startup now connects with
that exact credential, proves the read-only authority contract and keeps the
process fail-closed and observable when the contract is rejected.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from ai_assistant import runtime as runtime_module
from ai_assistant import runtime_app
from ai_assistant.db_authority import AiReadOnlyAuthorityError
from ai_assistant.runtime import AiSandboxRuntime
from ai_assistant.settings import AiAssistantSettings
from schemas.ai_assistant import RuntimeTurnRequest


def fake_runtime(
    tmp_path: Path,
    *,
    ready: bool,
    error: str | None = None,
    readonly_dsn: str = "postgresql://unihub_ai_readonly@db.internal:5432/unihub",
) -> AiSandboxRuntime:
    runtime = object.__new__(AiSandboxRuntime)
    runtime.settings = AiAssistantSettings(  # type: ignore[assignment]
        model="gpt-5.6-luna",
        runtime_url="http://127.0.0.1:9911",
        storage_root=tmp_path,
        snapshot_root=tmp_path,
        knowledge_root=Path(runtime_module.__file__).resolve().parent / "knowledge",
        sandbox_image="unihub-retail-sandbox:test",
        max_artifact_bytes=1024,
        setup_timeout_seconds=30,
        readonly_dsn=readonly_dsn,
    )
    runtime._orphans_ready = True
    runtime._startup_error = None
    runtime.db_guard = cast(Any, SimpleNamespace(ready=True, error=None))
    runtime._authority_ready = ready  # type: ignore[attr-defined]
    runtime._authority_error = error  # type: ignore[attr-defined]
    return runtime


def request_for(runtime: Any) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],
            "app": SimpleNamespace(state=SimpleNamespace(ai_runtime=runtime)),
        }
    )


def turn_payload() -> RuntimeTurnRequest:
    return RuntimeTurnRequest(
        conversation_id=uuid4(), owner_subject="owner-a", text="salut", effort="high"
    )


@pytest.mark.anyio
async def test_health_is_unavailable_until_the_dsn_contract_is_verified(
    tmp_path: Path,
) -> None:
    unverified = fake_runtime(
        tmp_path, ready=False, error="principal has elevated role attributes"
    )
    response = await runtime_app.health(request_for(unverified))

    assert response.status_code == 503
    assert b"elevated role attributes" in response.body

    response = await runtime_app.health(request_for(fake_runtime(tmp_path, ready=True)))

    assert response.status_code == 200
    assert response.body == b'{"status":"ok"}'


@pytest.mark.anyio
async def test_run_endpoint_refuses_to_expose_an_unverified_credential(
    tmp_path: Path,
) -> None:
    with pytest.raises(HTTPException) as failure:
        await runtime_app.run_turn(
            turn_payload(), request_for(fake_runtime(tmp_path, ready=False))
        )

    assert failure.value.status_code == 503

    stream = await runtime_app.run_turn(
        turn_payload(), request_for(fake_runtime(tmp_path, ready=True))
    )
    assert stream.media_type == "application/x-ndjson"


@pytest.mark.anyio
async def test_lifespan_stays_alive_but_unhealthy_after_a_rejected_dsn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RejectedRuntime(AiSandboxRuntime):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs
            self.settings = fake_runtime(tmp_path, ready=False).settings
            self._authority_ready = False
            self._authority_error = "AI sandbox read-only login has elevated role attributes"

        async def startup(self) -> None:
            self._orphans_ready = True
            self._startup_error = None
            raise AiReadOnlyAuthorityError(self._authority_error or "")

        async def shutdown(self) -> None:
            pass

    monkeypatch.setattr(runtime_app, "AiSandboxRuntime", RejectedRuntime)
    app = cast(FastAPI, SimpleNamespace(state=SimpleNamespace()))

    async with runtime_app.lifespan(app):
        runtime = app.state.ai_runtime
        assert isinstance(runtime, RejectedRuntime)
        assert runtime.authority_ready is False
        assert (await runtime_app.health(request_for(runtime))).status_code == 503
        with pytest.raises(HTTPException):
            await runtime_app.run_turn(turn_payload(), request_for(runtime))


@pytest.mark.anyio
async def test_runtime_records_verified_readiness_and_clears_it_on_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = fake_runtime(tmp_path, ready=False, error="not verified")
    assert runtime.authority_ready is False

    async def accept(dsn: str) -> str:
        assert dsn.endswith("/unihub")
        return "unihub_ai_readonly"

    monkeypatch.setattr(runtime_module, "verify_sandbox_readonly_authority", accept)
    await runtime.verify_readonly_authority()
    assert runtime.authority_ready is True
    assert runtime.authority_error is None
    # The sandbox credential must never leak through the settings representation.
    assert "unihub_ai_readonly" not in repr(runtime.settings)

    async def reject(dsn: str) -> str:
        del dsn
        raise AiReadOnlyAuthorityError("login holds effective write authority")

    monkeypatch.setattr(runtime_module, "verify_sandbox_readonly_authority", reject)
    with pytest.raises(AiReadOnlyAuthorityError):
        await runtime.verify_readonly_authority()
    assert runtime.authority_ready is False
    assert runtime.authority_error == "login holds effective write authority"
