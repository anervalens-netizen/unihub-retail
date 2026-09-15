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
from urllib.parse import urlsplit, urlunsplit
from ai_assistant.storage_slots import StorageSlots
from tests.test_ai_assistant_db_guard import GUARD_LOGIN, guard_database

import pytest
from docker.errors import NotFound

from ai_assistant import runtime as runtime_module
from ai_assistant.runtime import AiSandboxRuntime
from schemas.ai_assistant import RuntimeTurnRequest, RuntimeUpload
from tests.test_ai_assistant_db_authority import AI_LOGIN, authority_database, dsn_for
from tests.test_ai_assistant_runtime_health import fake_runtime
from tests.test_ai_assistant_startup import LABELS

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1" or os.getenv("AI_TEST_REAL_DOCKER") != "1" or not os.getenv("AI_TEST_STORAGE_ROOT"),
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
        sql = await self.sandbox.exec('psql "$UNIHUB_READONLY_DSN" -Atc "SELECT current_user"', timeout=10)
        assert sql.ok() and sql.stdout.strip() == b"unihub_ai_readonly"
        self.started.set()
        if self.mode == "stop":
            await self.release.wait()
        if False:
            yield None

    def cancel(self, mode: str = "immediate") -> None:
        self.release.set()


async def collect(runtime: AiSandboxRuntime, request: RuntimeTurnRequest) -> list[Any]:
    return [json.loads(chunk) async for chunk in runtime.stream_turn(request)]


def _assert_disposable_storage_root() -> Path:
    root = Path(os.environ["AI_TEST_STORAGE_ROOT"])
    assert root.parent == Path("/tmp") and root.name.startswith("unihub-ai-storage.")
    return root


def _bridge_dsn_for_canonical_runner(runtime: AiSandboxRuntime, settings: Any) -> str:
    """Select only this canonical runner's PostgreSQL by its exact published port."""
    port = str(urlsplit(settings.readonly_dsn).port)
    databases = [c for c in runtime.docker.containers.list(filters={"label": "unihub.test=retail"})
                 if any(p["HostPort"] == port for p in (c.attrs["NetworkSettings"]["Ports"].get("5432/tcp") or []))]
    assert len(databases) == 1
    networks = databases[0].attrs["NetworkSettings"]["Networks"]
    assert len(networks) == 1
    host = next(iter(networks.values()))["IPAddress"]
    parsed = urlsplit(settings.readonly_dsn)
    return urlunsplit(parsed._replace(netloc=f"{parsed.username}:{parsed.password}@{host}:5432"))


def _seed_state_containers(runtime: AiSandboxRuntime, settings: Any, created: list[Any]) -> Any:
    """Create one container per cleanup state plus an unrelated witness container.

    ``created`` is appended in place so a partial failure still leaves every
    created container reachable by the caller's cleanup path.
    """
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
    return unrelated


def _remove_created_containers(runtime: AiSandboxRuntime, created: list[Any]) -> None:
    # Fresh SDK client because shutdown closes its transport.
    client = runtime_module.docker_from_env()
    try:
        for item in created:
            try:
                client.containers.get(item.id).remove(force=True, v=True)
            except NotFound:
                pass
    finally:
        client.close()


@pytest.mark.anyio
async def test_real_docker_startup_and_all_run_cleanup_paths(
    authority_database: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = replace(
        fake_runtime(tmp_path, ready=False).settings,
        sandbox_image=os.getenv("AI_TEST_SANDBOX_IMAGE", "unihub-retail-ai-sandbox:pr409-slots"),
        readonly_dsn=dsn_for(AI_LOGIN),
        guard_dsn=dsn_for(GUARD_LOGIN),
    )
    monkeypatch.setenv("AI_ASSISTANT_READONLY_DSN", settings.readonly_dsn)
    runtime = AiSandboxRuntime(settings)
    root = _assert_disposable_storage_root()
    runtime.slots = StorageSlots(root / "ai-sandbox-slots", root / "ai-storage-images")
    bridge_dsn = _bridge_dsn_for_canonical_runner(runtime, settings)
    runtime.settings = replace(settings, readonly_dsn=bridge_dsn)
    monkeypatch.setenv("AI_ASSISTANT_READONLY_DSN", bridge_dsn)
    filters = {"label": [f"{key}={value}" for key, value in LABELS.items()]}
    assert not runtime.docker.containers.list(all=True, filters=filters), "preexisting matching containers: abort proof"
    created: list[Any] = []
    try:
        unrelated = _seed_state_containers(runtime, settings, created)
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
        _remove_created_containers(runtime, created)


async def _exercise_runs(runtime: AiSandboxRuntime, monkeypatch: pytest.MonkeyPatch, filters: Any) -> None:
    mode = "complete"
    results: list[DockerResult] = []

    def run(*args: Any, **kwargs: Any) -> DockerResult:
        result = DockerResult(kwargs["run_config"].sandbox.session, mode)
        results.append(result)
        return result

    monkeypatch.setattr(runtime_module, "Runner", SimpleNamespace(run_streamed=run))
    for mode in ("complete", "stop", "setup_failure"):
        request = RuntimeTurnRequest(conversation_id=uuid4(), owner_subject="docker-proof", text="tiny artifact", effort="none", order_key=1)
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
