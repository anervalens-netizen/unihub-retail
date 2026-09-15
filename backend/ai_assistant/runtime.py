from __future__ import annotations

import asyncio
import io
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Literal
from uuid import UUID

from agents import ModelSettings, Runner
from agents.run import RunConfig
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.entries import Dir
from agents.sandbox.manifest import EnvEntry, EnvValue, Environment
from ai_assistant.docker_client import BoundedDockerSandboxClient, SlotDockerOptions, WorkspaceSnapshot, LABELS
from ai_assistant.storage_slots import StorageSlots, clean_slot, storage_io
from ai_assistant.guard_authority import verify_guard_authority, verify_guard_database
from docker import from_env as docker_from_env
from openai.types.responses import ResponseTextDeltaEvent
from openai.types.shared import Reasoning

from ai_assistant.artifacts import collect_output_artifacts, output_hashes
from ai_assistant.db_authority import verify_sandbox_readonly_authority
from ai_assistant.db_guard import DatabaseSessionGuard
from ai_assistant.run_state_machine import ActiveRun
from ai_assistant.settings import (
    AI_READONLY_DSN_ENV,
    AiAssistantSettings,
    load_ai_assistant_settings,
    resolve_storage_key,
)
from schemas.ai_assistant import (
    AiReasoningEffort,
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
The root filesystem is read-only. All durable writes, user configuration and package installs belong under /workspace (8 GiB total); /tmp is only 512 MiB of ephemeral memory.
Plain pip install uses the workspace target automatically; npm install -g uses the workspace prefix. Workspace Python/npm executables are on PATH.
Do not ask unnecessary confirmation questions.
"""


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
            "home": Dir(description="Writable user home and configuration"),
            "work": Dir(description="Agent scratch workspace and Python/npm user packages"),
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


class AiSandboxRuntime:
    def __init__(self, settings: AiAssistantSettings | None = None):
        self.settings = settings or load_ai_assistant_settings(runtime=True)
        self.docker = docker_from_env(timeout=10)
        self.client = BoundedDockerSandboxClient(self.docker)
        self.slots = StorageSlots()
        self.db_guard = DatabaseSessionGuard(self.settings.guard_dsn)
        self._orphans_ready = False
        self._startup_error: str | None = "AI sandbox startup reconciliation is incomplete"
        self._active: dict[UUID, ActiveRun] = {}
        self._lock = asyncio.Lock()
        self._authority_ready = False
        self._authority_error: str | None = "AI read-only database authority is not verified"

    @property
    def authority_ready(self) -> bool:
        """True only after the sandbox credential proved its read-only contract."""
        return self._authority_ready

    @property
    def authority_error(self) -> str | None:
        return self._authority_error

    @property
    def ready(self) -> bool:
        return self._orphans_ready and self.authority_ready and self.db_guard.ready

    @property
    def readiness_error(self) -> str | None:
        return self._startup_error or self.authority_error or self.db_guard.error

    def _remove_stale_sandboxes(self) -> None:
        labels = {
            "com.unihub.component": "ai-assistant",
            "com.unihub.runtime": "sandbox-agent",
        }
        containers = self.docker.containers.list(
            all=True, filters={"label": [f"{key}={value}" for key, value in labels.items()]}
        )
        for container in containers:
            # Defense in depth: do not trust a partial/overbroad daemon filter.
            if all(container.labels.get(key) == value for key, value in labels.items()):
                container.remove(force=True, v=True)

    def _verify_slots_unused(self, slot: Any = None) -> None:
        slots = (slot,) if slot is not None else self.slots.slots
        for container in self.docker.containers.list(all=True):
            container.reload()
            for mount in container.attrs.get("Mounts", []):
                source_value = mount.get("Source")
                if mount.get("Type") != "bind" or not isinstance(source_value, str):
                    continue
                source = Path(source_value).resolve()
                if any(source.is_relative_to(item.mount) or item.workspace.is_relative_to(source) for item in slots):
                    raise RuntimeError("AI storage slot is still attached to a container")

    async def startup(self) -> None:
        try:
            await storage_io(self.slots.verify)
            await storage_io(self._remove_stale_sandboxes)
            await storage_io(self._verify_slots_unused)
            await storage_io(self.slots.reconcile)
            self._orphans_ready = True
            self._startup_error = None
            await self.verify_readonly_authority()
            await verify_guard_authority(self.settings.guard_dsn)
            await verify_guard_database(self.settings.readonly_dsn, self.settings.guard_dsn)
            await self.db_guard.start()
        except Exception:
            self._startup_error = "AI runtime startup preflight failed"
            logger.error(self._startup_error)
            raise

    async def shutdown(self) -> None:
        await self.db_guard.close()
        await storage_io(self.docker.close)

    async def verify_readonly_authority(self) -> None:
        """Fail closed before the runtime is allowed to report healthy.

        ``UNIHUB_READONLY_DSN`` is handed to arbitrary model-generated code, so
        the runtime must connect with it and prove the read-only authority
        contract before any run can start. The failure text never contains the
        DSN or its password.
        """
        try:
            principal = await verify_sandbox_readonly_authority(self.settings.readonly_dsn)
        except Exception as exc:
            self._authority_ready = False
            self._authority_error = str(exc) or type(exc).__name__
            logger.error("AI read-only database authority rejected: %s", self._authority_error)
            raise
        self._authority_ready = True
        self._authority_error = None
        logger.info("AI read-only database authority verified principal=%s", principal)

    async def _reserve(self, conversation_id: UUID, owner_subject: str) -> ActiveRun | None:
        """Reserve the conversation slot and one owner run slot together.

        The conversation bound keeps Steer/Stop deterministic; the owner bound
        makes Docker/model spend mathematically bounded even when the caller
        opens many conversations. Both are taken under the same lock.
        """
        async with self._lock:
            if conversation_id in self._active:
                return None
            ceiling = self.settings.max_concurrent_runs_per_owner
            owned = sum(
                1 for run in self._active.values() if run.owner_subject == owner_subject
            )
            if owned >= ceiling:
                return None
            slot = self.slots.acquire()
            if slot is None:
                return None
            active = ActiveRun(task=asyncio.current_task(), owner_subject=owner_subject, slot=slot)
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

    async def _cleanup_sandbox(self, conversation_id: UUID, active: ActiveRun) -> None:
        if active.cleanup_done:
            return
        active.cleanup_done = True
        failed = False
        sandbox = active.sandbox
        if sandbox is not None:
            try:
                if active.sandbox_started:
                    await sandbox.aclose()
            except BaseException:
                failed = True
                logger.error("AI snapshot/close failed conversation=%s", conversation_id)
            try:
                await self.client.delete(sandbox)
            except BaseException:
                failed = True
                logger.error("AI sandbox deletion failed conversation=%s", conversation_id)
        if active.slot is not None and not failed:
            try:
                await storage_io(self._verify_slots_unused, active.slot)
                await storage_io(clean_slot, active.slot)
                active.slot_clean = True
            except BaseException:
                failed = True
        if failed:
            raise RuntimeError("AI sandbox cleanup failed; storage slot quarantined")

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

    async def _start_run(
        self,
        conversation_id: UUID,
        active: ActiveRun,
        request: RuntimeTurnRequest,
        agent: SandboxAgent[None],
    ) -> tuple[Any, RunConfig, dict[str, str]] | None:
        """Create the sandbox, stage owner input and start the first model run.

        Returns ``None`` when a concurrent Stop must win before model execution.
        """
        if active.slot is None:
            raise RuntimeError("AI run has no storage slot")
        snapshot = WorkspaceSnapshot(
            id=str(conversation_id),
            base_path=self.settings.snapshot_root,
        )
        sandbox = await self.client.create(
            manifest=agent.default_manifest,
            snapshot=snapshot,
            options=SlotDockerOptions(image=self.settings.sandbox_image, labels=LABELS, slot=active.slot),
        )
        active.sandbox = sandbox
        await sandbox.start()
        active.sandbox_started = True
        await self._stage_knowledge(sandbox)
        upload_names = await self._stage_request_files(
            sandbox,
            current_view=request.current_view,
            uploads=request.uploads,
        )
        before_outputs = await output_hashes(sandbox)
        initial_input = _owner_input(
            request.text,
            request.current_view,
            upload_names,
        )
        for steer_request in await self._drain_pending_steers(active):
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
            return None
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
            return None
        return result, run_config, before_outputs

    async def _stream_events(
        self, result: Any, accumulated: list[str]
    ) -> AsyncIterator[bytes]:
        async for event in result.stream_events():
            if event.type == "raw_response_event" and isinstance(
                event.data, ResponseTextDeltaEvent
            ):
                accumulated.append(event.data.delta)
                yield _ndjson({"type": "delta", "text": event.data.delta})
            elif event.type == "run_item_stream_event" and event.name == "tool_called":
                yield _ndjson(
                    {"type": "status", "message": "Folosesc instrumentele din sandbox…"}
                )

    async def _resume_with_steers(
        self,
        conversation_id: UUID,
        active: ActiveRun,
        agent: SandboxAgent[None],
        run_config: RunConfig,
        result: Any,
        pending: list[RuntimeSteerRequest],
    ) -> Any | None:
        """Start the resumed model run that carries the queued owner steers.

        Returns ``None`` when a concurrent Stop must win instead of the resume.
        """
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
            return None
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
            return None
        return next_result

    async def _drain_or_finish(
        self, active: ActiveRun
    ) -> list[RuntimeSteerRequest] | None:
        """Take the queued owner steers, or report that Stop won the race.

        ``None`` means this run was stopped. An empty list means the model turn
        finished with nothing queued, so the reservation moves to ``finishing``.
        """
        async with self._lock:
            if active.stop_requested:
                return None
            pending = list(active.pending_steers)
            active.pending_steers.clear()
            if not pending:
                active.phase = "finishing"
            return pending

    async def _release(self, conversation_id: UUID, active: ActiveRun) -> None:
        """Drop the reservation only if it is still the one this run created."""
        async with self._lock:
            if self._active.get(conversation_id) is active:
                self._active.pop(conversation_id, None)
                if active.slot is not None:
                    self.slots.release(active.slot, clean=active.slot_clean)

    async def stream_turn(self, request: RuntimeTurnRequest) -> AsyncIterator[bytes]:
        conversation_id = request.conversation_id
        active = await self._reserve(conversation_id, request.owner_subject)
        if active is None:
            yield _ndjson({"type": "error", "message": "A run is already active for this conversation."})
            return

        agent = _agent(self.settings, request.effort)
        accumulated: list[str] = []
        try:
            try:
                async with asyncio.timeout(self.settings.setup_timeout_seconds):
                    started = await self._start_run(conversation_id, active, request, agent)
            except TimeoutError:
                yield _ndjson({"type": "error", "message": "Pornirea sandboxului AI a depășit timpul permis."})
                return
            if started is None:
                yield _ndjson({"type": "stopped"})
                return
            result, run_config, before_outputs = started

            yield _ndjson({"type": "status", "message": "UniHub AI lucrează în sandbox."})

            while True:
                async for event in self._stream_events(result, accumulated):
                    yield event
                pending = await self._drain_or_finish(active)
                if pending is None:
                    yield _ndjson({"type": "stopped"})
                    return
                if not pending:
                    break
                next_result = await self._resume_with_steers(
                    conversation_id, active, agent, run_config, result, pending
                )
                if next_result is None:
                    yield _ndjson({"type": "stopped"})
                    return
                result = next_result
                yield _ndjson({"type": "status", "message": "Direcția nouă a fost aplicată."})

            final_text = (
                result.final_output
                if isinstance(result.final_output, str)
                else "".join(accumulated)
            )
            artifacts = await collect_output_artifacts(
                self.settings,
                conversation_id,
                active.sandbox,
                before_outputs,
            )
            await self._cleanup_sandbox(conversation_id, active)
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
        except asyncio.CancelledError:
            if active.stop_requested:
                yield _ndjson({"type": "stopped"})
                return
            raise
        except Exception:
            logger.exception("AI sandbox run failed conversation=%s", conversation_id)
            yield _ndjson({"type": "error", "message": "UniHub AI nu a putut finaliza cererea."})
        finally:
            try:
                await self._cleanup_sandbox(conversation_id, active)
            finally:
                await self._release(conversation_id, active)
