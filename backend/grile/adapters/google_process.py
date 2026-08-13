from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
import signal
import sys
from typing import Any


DEFAULT_CHILD_TIMEOUT_SECONDS = 180.0
DEFAULT_CHILD_OUTPUT_LIMIT_BYTES = 8 * 1024 * 1024
DEFAULT_CHILD_ERROR_LIMIT_BYTES = 64 * 1024


class GrileGoogleProcessError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class GrileGoogleSnapshot:
    value_ranges: list[dict[str, Any]]
    modified_time: str | None


def _bounded_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise GrileGoogleProcessError(
            "provider_config_invalid",
            f"{name} must be numeric",
        ) from exc
    if not minimum <= value <= maximum:
        raise GrileGoogleProcessError(
            "provider_config_invalid",
            f"{name} must be between {minimum:g} and {maximum:g}",
        )
    return value


def _bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise GrileGoogleProcessError(
            "provider_config_invalid",
            f"{name} must be an integer",
        ) from exc
    if not minimum <= value <= maximum:
        raise GrileGoogleProcessError(
            "provider_config_invalid",
            f"{name} must be between {minimum} and {maximum}",
        )
    return value


async def _terminate(
    process: asyncio.subprocess.Process,
    *,
    grace_seconds: float = 2.0,
) -> None:
    if process.returncode is not None:
        return
    try:
        # The provider is started in a new session so a future discovery helper
        # or HTTP subprocess cannot survive cancellation as an orphan.
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.send_signal(signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), grace_seconds)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        await process.wait()


async def _read_bounded(
    stream: asyncio.StreamReader,
    *,
    limit: int,
    error_code: str,
    label: str,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await stream.read(min(64 * 1024, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            raise GrileGoogleProcessError(
                error_code,
                f"Google child {label} exceeded the configured limit",
            )
        chunks.append(chunk)


def _snapshot_from_output(stdout: bytes) -> GrileGoogleSnapshot:
    try:
        payload = json.loads(stdout)
        value_ranges = payload["value_ranges"]
        modified_time = payload.get("modified_time")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GrileGoogleProcessError(
            "provider_output_invalid",
            "Google child returned an invalid payload",
        ) from exc
    if not isinstance(value_ranges, list) or not all(
        isinstance(item, dict) for item in value_ranges
    ):
        raise GrileGoogleProcessError(
            "provider_output_invalid",
            "Google child returned an invalid value_ranges payload",
        )
    if modified_time is not None and not isinstance(modified_time, str):
        raise GrileGoogleProcessError(
            "provider_output_invalid",
            "Google child returned an invalid modified_time payload",
        )
    return GrileGoogleSnapshot(value_ranges=value_ranges, modified_time=modified_time)


async def fetch_grile_snapshot(
    sheet_id: str,
    template_version: str,
    *,
    timeout_seconds: float | None = None,
) -> GrileGoogleSnapshot:
    """Read one sheet in a short-lived, hard-killable provider process."""

    if not sheet_id or len(sheet_id) > 256 or template_version not in {"v2", "v3"}:
        raise GrileGoogleProcessError(
            "provider_input_invalid",
            "Invalid Google sheet request",
        )
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else _bounded_float(
            "GRILE_GOOGLE_CHILD_TIMEOUT_SECONDS",
            DEFAULT_CHILD_TIMEOUT_SECONDS,
            minimum=5,
            maximum=600,
        )
    )
    if not 1 <= timeout <= 600:
        raise GrileGoogleProcessError(
            "provider_config_invalid",
            "Google child timeout must be between 1 and 600 seconds",
        )
    output_limit = _bounded_int(
        "GRILE_GOOGLE_CHILD_OUTPUT_LIMIT_BYTES",
        DEFAULT_CHILD_OUTPUT_LIMIT_BYTES,
        minimum=64 * 1024,
        maximum=64 * 1024 * 1024,
    )

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "grile.adapters.google_child",
        sheet_id,
        template_version,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_task = asyncio.create_task(
        _read_bounded(
            process.stdout,
            limit=output_limit,
            error_code="provider_output_too_large",
            label="stdout",
        ),
        name=f"grile-google-stdout:{process.pid}",
    )
    stderr_task = asyncio.create_task(
        _read_bounded(
            process.stderr,
            limit=DEFAULT_CHILD_ERROR_LIMIT_BYTES,
            error_code="provider_error_output_too_large",
            label="stderr",
        ),
        name=f"grile-google-stderr:{process.pid}",
    )
    wait_task = asyncio.create_task(process.wait(), name=f"grile-google-wait:{process.pid}")
    try:
        try:
            stdout, stderr, _return_code = await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task, wait_task),
                timeout,
            )
        except TimeoutError as exc:
            await _terminate(process)
            raise GrileGoogleProcessError(
                "provider_timeout",
                "Google read exceeded the configured deadline",
            ) from exc
        except asyncio.CancelledError:
            await _terminate(process)
            raise
        except GrileGoogleProcessError:
            await _terminate(process)
            raise

        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[:500]
            raise GrileGoogleProcessError(
                "provider_failed",
                detail or "Google provider process failed",
            )
        return _snapshot_from_output(stdout)
    finally:
        if process.returncode is None:
            await _terminate(process)
        for task in (stdout_task, stderr_task, wait_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(stdout_task, stderr_task, wait_task, return_exceptions=True)
