"""Hard-killable, one-operation process boundary for complex XLSX rendering."""

from __future__ import annotations

import asyncio
import multiprocessing
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Literal


RendererName = Literal["daily_metrics", "daily_comparison"]
DEFAULT_EXPORT_RENDERER_TIMEOUT_SECONDS = 5 * 60


class ExportRendererProcessError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def export_renderer_timeout_seconds() -> float:
    raw = os.getenv(
        "EXPORT_RENDERER_TIMEOUT_SECONDS",
        str(DEFAULT_EXPORT_RENDERER_TIMEOUT_SECONDS),
    )
    try:
        value = float(raw)
    except ValueError as exc:
        raise ExportRendererProcessError(
            "renderer_config_invalid",
            "EXPORT_RENDERER_TIMEOUT_SECONDS must be numeric",
        ) from exc
    if not 10 <= value <= 15 * 60:
        raise ExportRendererProcessError(
            "renderer_config_invalid",
            "EXPORT_RENDERER_TIMEOUT_SECONDS must be between 10 and 900",
        )
    return value


def _safe_send(connection: Connection, message: dict[str, Any]) -> None:
    try:
        connection.send(message)
    except (BrokenPipeError, EOFError, OSError):
        # The parent may have timed out and destroyed the operation already.
        pass


def _child_main(
    renderer_name: RendererName,
    payload: dict[str, Any],
    send_connection: Connection,
) -> None:
    try:
        from services.export_complex_worker import (
            render_daily_comparison_xlsx,
            render_daily_metrics_xlsx,
        )

        renderer = {
            "daily_metrics": render_daily_metrics_xlsx,
            "daily_comparison": render_daily_comparison_xlsx,
        }[renderer_name]
        result = renderer(payload)
        _safe_send(send_connection, {"ok": True, "result": result})
    except MemoryError:
        _safe_send(
            send_connection,
            {
                "ok": False,
                "code": "renderer_memory_limit",
                "message": "Complex export exceeded its memory limit",
            },
        )
    except BaseException as exc:  # noqa: BLE001 - isolated process boundary
        _safe_send(
            send_connection,
            {
                "ok": False,
                "code": "renderer_failed",
                "message": f"{type(exc).__name__}: {exc}"[:500],
            },
        )
    finally:
        send_connection.close()


def _receive(connection: Connection) -> dict[str, Any] | None:
    try:
        value = connection.recv()
    except EOFError:
        return None
    return value if isinstance(value, dict) else None


def _terminate_process(
    process: BaseProcess,
    grace_seconds: float = 2.0,
) -> None:
    if not process.is_alive():
        process.join(timeout=0.1)
        return
    process.terminate()
    process.join(timeout=grace_seconds)
    if process.is_alive():
        # multiprocessing.Process.kill is SIGKILL on the supported Linux runtime.
        process.kill()
        process.join(timeout=grace_seconds)


def _cleanup_reported_artifact(message: dict[str, Any] | None) -> None:
    if not message or not message.get("ok"):
        return
    result = message.get("result")
    if not isinstance(result, dict):
        return
    raw_path = result.get("path")
    if isinstance(raw_path, str) and raw_path:
        Path(raw_path).unlink(missing_ok=True)


def _cleanup_operation_directory(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)


async def _drain_receive_task(
    task: asyncio.Task[dict[str, Any] | None],
) -> dict[str, Any] | None:
    values = await asyncio.gather(task, return_exceptions=True)
    value = values[0] if values else None
    return value if isinstance(value, dict) else None


async def run_export_renderer_process(
    renderer_name: RendererName,
    payload: dict[str, Any],
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Run exactly one renderer and destroy its process on timeout/cancellation."""

    if renderer_name not in {"daily_metrics", "daily_comparison"}:
        raise ExportRendererProcessError(
            "renderer_input_invalid",
            "Unknown complex export renderer",
        )
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else export_renderer_timeout_seconds()
    )
    if timeout <= 0 or timeout > 15 * 60:
        raise ExportRendererProcessError(
            "renderer_config_invalid",
            "Complex export timeout must be positive and at most 900 seconds",
        )

    operation_directory = Path(
        tempfile.mkdtemp(prefix="unihub-export-operation-")
    ).resolve()
    child_payload = dict(payload)
    child_payload["output_path"] = str(operation_directory / "artifact.xlsx")

    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_child_main,
        args=(renderer_name, child_payload, send_connection),
        name=f"unihub-export-{renderer_name}",
        daemon=False,
    )
    receive_task: asyncio.Task[dict[str, Any] | None] | None = None
    message: dict[str, Any] | None = None
    transferred = False
    try:
        try:
            process.start()
        except BaseException as exc:
            raise ExportRendererProcessError(
                "renderer_start_failed",
                f"Complex export renderer could not start: {type(exc).__name__}",
            ) from exc
        finally:
            send_connection.close()

        receive_task = asyncio.create_task(
            asyncio.to_thread(_receive, receive_connection),
            name=f"export-renderer-receive:{process.pid}",
        )
        try:
            message = await asyncio.wait_for(asyncio.shield(receive_task), timeout)
        except TimeoutError as exc:
            await asyncio.to_thread(_terminate_process, process)
            received = await _drain_receive_task(receive_task)
            _cleanup_reported_artifact(received)
            _cleanup_operation_directory(operation_directory)
            raise ExportRendererProcessError(
                "renderer_timeout",
                "Complex export renderer exceeded its wall-clock deadline",
            ) from exc
        except asyncio.CancelledError:
            await asyncio.to_thread(_terminate_process, process)
            received = await _drain_receive_task(receive_task)
            _cleanup_reported_artifact(received)
            _cleanup_operation_directory(operation_directory)
            raise

        await asyncio.to_thread(process.join, 2.0)
        if process.is_alive():
            await asyncio.to_thread(_terminate_process, process)
            _cleanup_reported_artifact(message)
            _cleanup_operation_directory(operation_directory)
            raise ExportRendererProcessError(
                "renderer_exit_timeout",
                "Complex export renderer did not exit after producing a result",
            )
        if message is None:
            _cleanup_operation_directory(operation_directory)
            raise ExportRendererProcessError(
                "renderer_crashed",
                f"Complex export renderer exited without a result (exit={process.exitcode})",
            )
        if not message.get("ok"):
            _cleanup_operation_directory(operation_directory)
            raise ExportRendererProcessError(
                str(message.get("code") or "renderer_failed"),
                str(message.get("message") or "Complex export renderer failed")[:500],
            )
        result = message.get("result")
        if not isinstance(result, dict):
            _cleanup_reported_artifact(message)
            _cleanup_operation_directory(operation_directory)
            raise ExportRendererProcessError(
                "renderer_output_invalid",
                "Complex export renderer returned an invalid result",
            )
        transferred = True
        return {**result, "operation_directory": str(operation_directory)}
    finally:
        receive_connection.close()
        if process.is_alive():
            await asyncio.to_thread(_terminate_process, process)
        if receive_task is not None and not receive_task.done():
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
        if not transferred:
            _cleanup_operation_directory(operation_directory)
