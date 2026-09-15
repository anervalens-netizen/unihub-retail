from __future__ import annotations

import asyncio
import io
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
from typing import Any, AsyncIterator, Literal
from uuid import UUID, uuid4

from agents import ModelSettings, Runner
from agents.run import RunConfig
from agents.sandbox import LocalSnapshot, Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.entries import Dir
from agents.sandbox.manifest import EnvEntry, EnvValue, Environment
from agents.sandbox.sandboxes.docker import DockerSandboxClient, DockerSandboxClientOptions
from docker import from_env as docker_from_env
from openai.types.responses import ResponseTextDeltaEvent
from openai.types.shared import Reasoning

from ai_assistant.run_state_machine import ActiveRun
from ai_assistant.settings import (
    AI_READONLY_DSN_ENV,
    AiAssistantSettings,
    load_ai_assistant_settings,
    resolve_storage_key,
)
from schemas.ai_assistant import (
    AiReasoningEffort,
    RuntimeArtifact,
    RuntimeSteerRequest,
    RuntimeTurnRequest,
)

logger = logging.getLogger(__name__)

_BASE_INSTRUCTIONS = """You are the private AI analyst and working agent inside UniHub Retail.
Work only when the owner sends a request.
Use the sandbox freely to inspect data, write code, manipulate files, perform analysis and produce finished artifacts.
Do the work instead of merely describing how it could be done.
Read /workspace/knowledge when product, KPI, data-model or artifact conventions matter.
The Retail PostgreSQL connection is available as UNIHUB_READONLY_DSN and is technically read-only; query it directly whenever data is required.
Owner uploads are under /workspace/input. Use /workspace/work for intermediate work and /workspace/output for final deliverables.
When the owner refers to the current page, selection, filters or card, inspect /workspace/input/current-view.json when present.
Put finished files the owner should receive under /workspace/output.
Do not ask unnecessary confirmation questions.
"""
_SAFE_ARTIFACT_NAME_RE = re.compile(r"[^A-Za-z0-9._() -]+")


class HostEnvValue(EnvValue):
    type: Literal["unihub_host_env"] = "unihub_host_env"
    name: str

    async def resolve(self) -> str:
        value = os.getenv(self.name, "")
        if not value:
            raise RuntimeError(f"required host environment variable {self.name} is empty")
        return value


def _ndjson(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _manifest() -> Manifest:
    return Manifest(
        root="/workspace",
        entries={
            "knowledge": Dir(description="Versioned UniHub Retail context"),
            "input": Dir(description="Owner uploads and current-view context"),
            "work": Dir(description="Agent scratch workspace"),
            "output": Dir(description="Finished deliverables returned to the owner"),
        },
        environment=Environment(
            value={
                "UNIHUB_READONLY_DSN": EnvEntry(
                    description="Read-only Retail PostgreSQL DSN",
                    ephemeral=True,
                    value=HostEnvValue(name=AI_READONLY_DSN_ENV),
                )
            }
        ),
    )


def _agent(settings: AiAssistantSettings, effort: AiReasoningEffort) -> SandboxAgent[None]:
    return SandboxAgent(
        name="UniHub AI",
        model=settings.model,
        base_instructions=_BASE_INSTRUCTIONS,
        default_manifest=_manifest(),
        model_settings=ModelSettings(
            reasoning=Reasoning(effort=effort),
            verbosity="low",
        ),
    )


def _owner_input(text: str, current_view: dict[str, object] | None, uploads: list[str]) -> str:
    parts = [text.strip() or "Inspect the attached files and respond with the useful result."]
    if current_view is not None:
        parts.append("Current UniHub UI context is available in /workspace/input/current-view.json.")
    if uploads:
        parts.append("Files attached to this turn: " + ", ".join(f"/workspace/input/{name}" for name in uploads))
    return "\n\n".join(parts)


def _safe_artifact_filename(value: str, artifact_id: UUID) -> str:
    name = _SAFE_ARTIFACT_NAME_RE.sub("_", Path(value).name).strip(" .")
    if not name:
        return f"artifact-{artifact_id}.bin"
    return name[:180].rstrip(" .") or f"artifact-{artifact_id}.bin"


class AiSandboxRuntime:
    def __init__(self, settings: AiAssistantSettings | None = None):
        self.settings = settings or load_ai_assistant_settings(runtime=True)
        self.client = DockerSandboxClient(docker_from_env())
        self.options = DockerSandboxClientOptions(
            image=self.settings.sandbox_image,
            labels={
                "com.unihub.component": "ai-assistant",
                "com.unihub.runtime": "sandbox-agent",
            },
        )
        self._active: dict[UUID, ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def _reserve(self, conversation_id: UUID) -> ActiveRun | None:
        async with self._lock:
            if conversation_id in self._active:
                return None
            active = ActiveRun(task=asyncio.current_task())
            self._active[conversation_id] = active
            return active

    async def _is_current(self, conversation_id: UUID, active: ActiveRun) -> bool:
        async with self._lock:
            return self._active.get(conversation_id) is active

    async def _stage_knowledge(self, sandbox: Any) -> None:
        for source in sorted(self.settings.knowledge_root.glob("*.md")):
            with source.open("rb") as handle:
                await sandbox.write(Path("knowledge") / source.name, handle)

    async def _stage_request_files(
        self,
        sandbox: Any,
        *,
        current_view: dict[str, object] | None,
        uploads: list[Any],
    ) -> list[str]:
        context_payload = json.dumps(
            current_view if current_view is not None else {},
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        await sandbox.write(Path("input/current-view.json"), io.BytesIO(context_payload))
        names: list[str] = []
        for upload in uploads:
            source = resolve_storage_key(self.settings.storage_root, upload.storage_key)
            if not source.is_file():
                raise FileNotFoundError(f"AI input artifact missing: {upload.storage_key}")
            with source.open("rb") as handle:
                await sandbox.write(Path("input") / upload.sandbox_name, handle)
            names.append(upload.sandbox_name)
        return names

    async def _output_hashes(self, sandbox: Any) -> dict[str, str]:
        result = await sandbox.exec(
            "find output -type f -print0 | sort -z | xargs -0 -r sha256sum -z",
            timeout=30,
        )
        if not result.ok():
            raise RuntimeError("unable to enumerate sandbox output files")
        hashes: dict[str, str] = {}
        for record in result.stdout.split(b"\0"):
            if not record:
                continue
            digest, raw_path = record.split(b"  ", 1)
            path = raw_path.decode("utf-8", errors="strict")
            if path.startswith("output/"):
                hashes[path.removeprefix("output/")] = digest.decode("ascii")
        return hashes

    async def _collect_artifacts(
        self,
        conversation_id: UUID,
        sandbox: Any,
        before: dict[str, str],
    ) -> list[RuntimeArtifact]:
        after = await self._output_hashes(sandbox)
        artifacts: list[RuntimeArtifact] = []
        for relative, digest in sorted(after.items()):
            if before.get(relative) == digest:
                continue
            stream = await sandbox.read(Path("output") / relative)
            try:
                payload = stream.read()
            finally:
                stream.close()
            if not isinstance(payload, bytes):
                payload = bytes(payload)
            if len(payload) > self.settings.max_artifact_bytes:
                raise RuntimeError(f"generated artifact exceeds configured limit: {relative}")
            artifact_id = uuid4()
            filename = _safe_artifact_filename(relative, artifact_id)
            storage_key = (
                Path("output") / str(conversation_id) / str(artifact_id) / filename
            ).as_posix()
            target = resolve_storage_key(self.settings.storage_root, storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            artifacts.append(
                RuntimeArtifact(
                    id=artifact_id,
                    filename=filename,
                    mime_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
                    size_bytes=len(payload),
                    storage_key=storage_key,
                )
            )
        return artifacts

    async def _cleanup_sandbox(self, conversation_id: UUID, active: ActiveRun) -> None:
        sandbox = active.sandbox
        if sandbox is None:
            return
        try:
            await sandbox.aclose()
        except Exception:
            logger.exception("AI sandbox close failed conversation=%s", conversation_id)
        try:
            await self.client.delete(sandbox)
        except Exception:
            logger.exception("AI sandbox deletion failed conversation=%s", conversation_id)

    async def steer(self, conversation_id: UUID, request: RuntimeSteerRequest) -> None:
        async with self._lock:
            active = self._active.get(conversation_id)
            if active is None or active.phase in {"finishing", "stopping"}:
                raise LookupError("no active AI run for this conversation")
            active.queue_steer(request)
            if active.result is not None:
                active.phase = "steering"
                active.result.cancel(mode="after_turn")

    async def stop(self, conversation_id: UUID) -> None:
        task: asyncio.Task[Any] | None = None
        async with self._lock:
            active = self._active.get(conversation_id)
            if active is None or active.phase == "finishing":
                raise LookupError("no active AI run for this conversation")
            active.stop_requested = True
            active.phase = "stopping"
            if active.result is not None:
                active.result.cancel()
            else:
                task = active.task
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def _drain_pending_steers(self, active: ActiveRun) -> list[RuntimeSteerRequest]:
        async with self._lock:
            pending = list(active.pending_steers)
            active.pending_steers.clear()
            return pending

    async def _stop_requested(self, active: ActiveRun) -> bool:
        async with self._lock:
            return active.stop_requested

    async def _install_result(self, conversation_id: UUID, active: ActiveRun, result: Any) -> bool:
        async with self._lock:
            if self._active.get(conversation_id) is not active or active.stop_requested:
                result.cancel()
                return False
            active.result = result
            active.phase = "running"
            return True

    async def stream_turn(self, request: RuntimeTurnRequest) -> AsyncIterator[bytes]:
        conversation_id = request.conversation_id
        active = await self._reserve(conversation_id)
        if active is None:
            yield _ndjson({"type": "error", "message": "A run is already active for this conversation."})
            return

        agent = _agent(self.settings, request.effort)
        run_config: RunConfig | None = None
        before_outputs: dict[str, str] = {}
        result: Any | None = None
        accumulated: list[str] = []
        try:
            try:
                async with asyncio.timeout(self.settings.setup_timeout_seconds):
                    snapshot = LocalSnapshot(
                        id=str(conversation_id),
                        base_path=self.settings.snapshot_root,
                    )
                    sandbox = await self.client.create(
                        manifest=agent.default_manifest,
                        snapshot=snapshot,
                        options=self.options,
                    )
                    active.sandbox = sandbox
                    await sandbox.start()
                    await self._stage_knowledge(sandbox)
                    upload_names = await self._stage_request_files(
                        sandbox,
                        current_view=request.current_view,
                        uploads=request.uploads,
                    )
                    before_outputs = await self._output_hashes(sandbox)
                    initial_input = _owner_input(
                        request.text,
                        request.current_view,
                        upload_names,
                    )
                    pending_before_first_call = await self._drain_pending_steers(active)
                    for steer_request in pending_before_first_call:
                        steer_names = await self._stage_request_files(
                            sandbox,
                            current_view=steer_request.current_view,
                            uploads=steer_request.uploads,
                        )
                        initial_input += (
                            "\n\nOwner steering update before the first model call:\n"
                            + _owner_input(
                                steer_request.text,
                                steer_request.current_view,
                                steer_names,
                            )
                        )
                    if await self._stop_requested(active):
                        yield _ndjson({"type": "stopped"})
                        return
                    run_config = RunConfig(
                        sandbox=SandboxRunConfig(session=sandbox),
                        workflow_name="UniHub AI owner request",
                    )
                    result = Runner.run_streamed(
                        agent,
                        initial_input,
                        run_config=run_config,
                        previous_response_id=request.previous_response_id,
                        max_turns=None,
                    )
                    if not await self._install_result(conversation_id, active, result):
                        yield _ndjson({"type": "stopped"})
                        return
            except TimeoutError:
                yield _ndjson({"type": "error", "message": "Pornirea sandboxului AI a depășit timpul permis."})
                return

            yield _ndjson({"type": "status", "message": "UniHub AI lucrează în sandbox."})

            while result is not None and run_config is not None:
                async for event in result.stream_events():
                    if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                        accumulated.append(event.data.delta)
                        yield _ndjson({"type": "delta", "text": event.data.delta})
                    elif event.type == "run_item_stream_event" and event.name == "tool_called":
                        yield _ndjson({"type": "status", "message": "Folosesc instrumentele din sandbox…"})

                async with self._lock:
                    if active.stop_requested:
                        yield _ndjson({"type": "stopped"})
                        return
                    pending = list(active.pending_steers)
                    active.pending_steers.clear()
                    if not pending:
                        active.phase = "finishing"

                if pending:
                    state = result.to_state()
                    fallback_inputs: list[str] = []
                    state_usable = True
                    for steer_request in pending:
                        names = await self._stage_request_files(
                            active.sandbox,
                            current_view=steer_request.current_view,
                            uploads=steer_request.uploads,
                        )
                        steer_input = _owner_input(
                            steer_request.text,
                            steer_request.current_view,
                            names,
                        )
                        fallback_inputs.append(steer_input)
                        if state_usable:
                            try:
                                state.add_input(steer_input)
                            except Exception:
                                state_usable = False
                    if await self._stop_requested(active):
                        yield _ndjson({"type": "stopped"})
                        return
                    if state_usable:
                        next_result = Runner.run_streamed(
                            agent,
                            state,
                            run_config=run_config,
                            max_turns=None,
                        )
                    else:
                        next_result = Runner.run_streamed(
                            agent,
                            "\n\n".join(fallback_inputs),
                            run_config=run_config,
                            previous_response_id=result.last_response_id,
                            max_turns=None,
                        )
                    if not await self._install_result(conversation_id, active, next_result):
                        yield _ndjson({"type": "stopped"})
                        return
                    result = next_result
                    yield _ndjson({"type": "status", "message": "Direcția nouă a fost aplicată."})
                    continue

                final_text = (
                    result.final_output
                    if isinstance(result.final_output, str)
                    else "".join(accumulated)
                )
                artifacts = await self._collect_artifacts(
                    conversation_id,
                    active.sandbox,
                    before_outputs,
                )
                yield _ndjson(
                    {
                        "type": "complete",
                        "text": final_text,
                        "previous_response_id": result.last_response_id,
                        "artifacts": [
                            artifact.model_dump(mode="json") for artifact in artifacts
                        ],
                    }
                )
                return
        except asyncio.CancelledError:
            if active.stop_requested:
                yield _ndjson({"type": "stopped"})
                return
            raise
        except Exception:
            logger.exception("AI sandbox run failed conversation=%s", conversation_id)
            yield _ndjson({"type": "error", "message": "UniHub AI nu a putut finaliza cererea."})
        finally:
            await self._cleanup_sandbox(conversation_id, active)
            async with self._lock:
                if self._active.get(conversation_id) is active:
                    self._active.pop(conversation_id, None)
