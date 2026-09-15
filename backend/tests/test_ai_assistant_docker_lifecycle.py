"""Opt-in real local Docker proof with isolated PostgreSQL and no model spend."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from docker.errors import NotFound

from ai_assistant import runtime as runtime_module
from ai_assistant.runtime import AiSandboxRuntime
from schemas.ai_assistant import RuntimeTurnRequest, RuntimeUpload
from tests.test_ai_assistant_db_authority import AI_LOGIN, authority_database, dsn_for
from tests.test_ai_assistant_runtime_health import fake_runtime
from tests.test_ai_assistant_startup import LABELS

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1" or os.getenv("AI_TEST_REAL_DOCKER") != "1",
    reason="requires opt-in local Docker and isolated PostgreSQL",
)


class DockerResult:
    def __init__(self, sandbox: Any, mode: str):
        self.sandbox = sandbox
        self.mode = mode
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.last_response_id = "deterministic-docker-proof"
        self.final_output = "tiny artifact ready"

    async def stream_events(self) -> Any:
        result = await self.sandbox.exec("printf tiny > output/proof.txt", timeout=10)
        assert result.ok()
        self.started.set()
        if self.mode == "stop":
            await self.release.wait()
        if False:
            yield None

    def cancel(self, mode: str = "immediate") -> None:
        self.release.set()


async def collect(runtime: AiSandboxRuntime, request: RuntimeTurnRequest) -> list[Any]:
    return [json.loads(chunk) async for chunk in runtime.stream_turn(request)]


@pytest.mark.anyio
async def test_real_docker_startup_and_all_run_cleanup_paths(
    authority_database: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = replace(
        fake_runtime(tmp_path, ready=False).settings,
        sandbox_image="unihub-retail-ai-sandbox:v3-dev",
        readonly_dsn=dsn_for(AI_LOGIN),
    )
    monkeypatch.setenv("AI_ASSISTANT_READONLY_DSN", settings.readonly_dsn)
    runtime = AiSandboxRuntime(settings)
    filters = {"label": [f"{key}={value}" for key, value in LABELS.items()]}
    assert not runtime.docker.containers.list(all=True, filters=filters), "preexisting matching containers: abort proof"
    created: list[Any] = []
    try:
        for state in ("running", "exited", "created", "paused"):
            item = runtime.docker.containers.create(settings.sandbox_image, command=["sleep", "120"], labels=LABELS)
            created.append(item)
            if state != "created":
                item.start()
            if state == "exited":
                item.stop(timeout=1)
            if state == "paused":
                item.pause()
        unrelated = runtime.docker.containers.create(settings.sandbox_image, command=["sleep", "120"], labels={"unihub.test": "ai-unrelated"})
        created.append(unrelated)
        unrelated.start()
        await runtime.startup()
        assert runtime.ready
        assert not runtime.docker.containers.list(all=True, filters=filters)
        unrelated.reload()
        assert unrelated.status == "running"
        await _exercise_runs(runtime, monkeypatch, filters)
        unrelated.reload()
        assert unrelated.status == "running"
    finally:
        await runtime.shutdown()
        # Fresh SDK client because shutdown closes its transport.
        client = runtime_module.docker_from_env()
        for item in created:
            try:
                client.containers.get(item.id).remove(force=True, v=True)
            except NotFound:
                pass
        client.close()


async def _exercise_runs(runtime: AiSandboxRuntime, monkeypatch: pytest.MonkeyPatch, filters: Any) -> None:
    mode = "complete"
    results: list[DockerResult] = []

    def run(*args: Any, **kwargs: Any) -> DockerResult:
        result = DockerResult(kwargs["run_config"].sandbox.session, mode)
        results.append(result)
        return result

    monkeypatch.setattr(runtime_module, "Runner", SimpleNamespace(run_streamed=run))
    for mode in ("complete", "stop", "setup_failure"):
        request = RuntimeTurnRequest(conversation_id=uuid4(), owner_subject="docker-proof", text="tiny artifact", effort="none")
        if mode == "setup_failure":
            request.uploads = [RuntimeUpload(storage_key="input/missing", sandbox_name="missing.txt")]
        task = asyncio.create_task(collect(runtime, request))
        if mode == "stop":
            async with asyncio.timeout(30):
                while len(results) < 2:
                    await asyncio.sleep(0.02)
                await results[-1].started.wait()
            await runtime.stop(request.conversation_id)
        async with asyncio.timeout(60):
            events = await task
        expected = {"complete": "complete", "stop": "stopped", "setup_failure": "error"}[mode]
        assert events[-1]["type"] == expected, events
        if mode == "complete":
            artifact = events[-1]["artifacts"][0]
            assert (runtime.settings.storage_root / artifact["storage_key"]).read_bytes() == b"tiny"
        assert not runtime._active
        assert not runtime.docker.containers.list(all=True, filters=filters)
