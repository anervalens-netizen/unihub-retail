"""Thread-affine Google boundary for monthly Grile operations.

Only plain dictionaries, lists and bytes cross this boundary.  Discovery,
credentials and Google client objects stay in the single worker thread.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from io import BytesIO
import os
from pathlib import Path
import threading
from typing import Any, Callable, Mapping

from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import httplib2


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_TRANSIENT = {429, 500, 502, 503, 504}
GOOGLE_HTTP_TIMEOUT_SECONDS = 90


class GoogleAdapterClosed(RuntimeError):
    """The serialized client is unavailable for further work."""


class GoogleAdapterTimeout(TimeoutError):
    """A sync request exceeded its async deadline; its future may still run."""


def _default_service_factory() -> tuple[Any, Any]:
    """Construct clients; this function is called only by the adapter thread."""
    from google.oauth2.service_account import Credentials

    base_dir = Path(__file__).resolve().parents[1]
    path = Path(
        os.getenv(
            "GRILE_GOOGLE_SA_FILE",
            base_dir / "config" / "google" / "service-account.json",
        )
    )
    if not path.exists():
        raise FileNotFoundError(f"Service account Google lipsa: {path}")
    credentials = Credentials.from_service_account_file(str(path), scopes=SCOPES)
    transport = AuthorizedHttp(
        credentials,
        http=httplib2.Http(timeout=GOOGLE_HTTP_TIMEOUT_SECONDS),
    )
    return (
        build("sheets", "v4", http=transport, cache_discovery=False),
        build("drive", "v3", http=transport, cache_discovery=False),
    )


class GoogleSyncAdapter:
    """One lazily initialized, one-thread Google client per worker process."""

    def __init__(
        self,
        *,
        service_factory: Callable[[], tuple[Any, Any]] | None = None,
        max_workers: int = 1,
        thread_name_prefix: str = "grile-monthly-google",
    ) -> None:
        if max_workers != 1:
            raise ValueError("GoogleSyncAdapter requires max_workers=1")
        self._factory = service_factory or _default_service_factory
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=thread_name_prefix,
        )
        self._local = threading.local()
        self._state_lock = threading.Lock()
        self._closed = False
        self._fail_closed = False
        self._inflight_destructive = 0

    @property
    def fail_closed(self) -> bool:
        with self._state_lock:
            return self._fail_closed

    @property
    def inflight_destructive(self) -> int:
        with self._state_lock:
            return self._inflight_destructive

    def _services(self) -> tuple[Any, Any]:
        services = getattr(self._local, "services", None)
        if services is None:
            services = self._factory()
            self._local.services = services
        return services

    def _invoke(self, operation: str, request: Mapping[str, Any]) -> Any:
        sheets, drive = self._services()
        spreadsheet_id = request.get("spreadsheet_id")
        if operation == "read_values":
            return sheets.spreadsheets().values().batchGet(
                spreadsheetId=spreadsheet_id,
                ranges=list(request["ranges"]),
                valueRenderOption=request.get("value_render_option", "FORMULA"),
                dateTimeRenderOption=request.get("date_time_render_option", "SERIAL_NUMBER"),
            ).execute()
        if operation == "clear":
            return sheets.spreadsheets().values().batchClear(
                spreadsheetId=spreadsheet_id,
                body={"ranges": list(request["ranges"])},
            ).execute()
        if operation == "restore":
            return sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": list(request.get("data", [])),
                },
            ).execute()
        if operation == "export_xlsx":
            request_obj = drive.files().export_media(
                fileId=spreadsheet_id,
                mimeType=request.get("mime_type", XLSX_MIME),
            )
            output = BytesIO()
            downloader = MediaIoBaseDownload(output, request_obj)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return output.getvalue()
        raise ValueError(f"Unknown monthly Google operation: {operation}")

    async def start(self) -> None:
        """Start the bounded queue; clients remain lazy and thread-affine."""
        with self._state_lock:
            if self._closed:
                raise GoogleAdapterClosed("monthly Google adapter is closed")

    async def request(
        self,
        operation: str,
        request: Mapping[str, Any],
        *,
        destructive: bool = False,
        timeout: float | None = None,
    ) -> Any:
        if operation == "warmup":
            operation = "__warmup__"

        def invoke() -> Any:
            if operation == "__warmup__":
                self._services()
                return {"status": "ready"}
            return self._invoke(operation, dict(request))

        with self._state_lock:
            if self._closed or (destructive and self._fail_closed):
                raise GoogleAdapterClosed("monthly Google adapter is closed")
            if destructive:
                self._inflight_destructive += 1

        future: Future[Any] = self._executor.submit(invoke)
        wrapped = asyncio.wrap_future(future)
        try:
            # shield keeps an in-flight provider request alive when the async
            # caller is cancelled; the durable intent decides what happens next.
            result = await asyncio.wait_for(asyncio.shield(wrapped), timeout)
            return result
        except asyncio.TimeoutError as exc:
            if destructive:
                with self._state_lock:
                    self._fail_closed = True
            raise GoogleAdapterTimeout("monthly Google request timed out") from exc
        finally:
            if destructive:
                def clear_inflight(_: Future[Any]) -> None:
                    with self._state_lock:
                        self._inflight_destructive = max(0, self._inflight_destructive - 1)

                future.add_done_callback(clear_inflight)

    async def close(self, *, timeout: float = 30.0) -> bool:
        """Drain the serialized queue, or fail closed if a call is stuck."""
        with self._state_lock:
            if self._closed:
                return not self._fail_closed
            self._closed = True

        barrier = self._executor.submit(lambda: None)
        drained = True
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(barrier)), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            drained = False
            with self._state_lock:
                self._fail_closed = True
        self._executor.shutdown(wait=drained, cancel_futures=not drained)
        return drained


def is_transient_error(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status in _TRANSIENT


async def call_with_backoff(
    adapter: GoogleSyncAdapter,
    operation: str,
    request: Mapping[str, Any],
    *,
    label: str,
    attempts: int = 4,
    base_delay: float = 1.0,
    destructive: bool = False,
    deadline: float | None = None,
) -> Any:
    """Retry reads/exports asynchronously; destructive calls run once."""
    total_attempts = 1 if destructive else max(1, attempts)
    loop = asyncio.get_running_loop()
    for attempt in range(total_attempts):
        timeout = None if deadline is None else max(0.0, deadline - loop.time())
        try:
            return await adapter.request(
                operation,
                dict(request),
                destructive=destructive,
                timeout=timeout,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - caller classifies provider errors
            if attempt >= total_attempts - 1 or not is_transient_error(exc):
                raise
            delay = base_delay * (2**attempt)
            if deadline is not None:
                delay = min(delay, max(0.0, deadline - loop.time()))
            await asyncio.sleep(delay)
    raise RuntimeError(f"{label} did not execute")
