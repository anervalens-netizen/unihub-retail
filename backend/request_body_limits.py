"""ASGI request-body limits applied before JSON or multipart parsing."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Awaitable, Callable

DEFAULT_JSON_BODY_BYTES = 1024 * 1024
DEFAULT_MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def _positive_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1024:
        raise RuntimeError(f"{name} must be at least 1024 bytes")
    return value


@dataclass(frozen=True, slots=True)
class RequestBodyLimits:
    json_bytes: int
    sales_multipart_bytes: int
    promo_multipart_bytes: int
    erp_multipart_bytes: int

    @classmethod
    def from_env(cls) -> "RequestBodyLimits":
        overhead = _positive_env("MAX_HTTP_MULTIPART_OVERHEAD_BYTES", DEFAULT_MULTIPART_OVERHEAD_BYTES)
        return cls(
            json_bytes=_positive_env("MAX_HTTP_JSON_BODY_BYTES", DEFAULT_JSON_BODY_BYTES),
            sales_multipart_bytes=_positive_env("MAX_SALES_UPLOAD_BYTES", 32 * 1024 * 1024) + overhead,
            promo_multipart_bytes=_positive_env("MAX_PROMO_REPORT_UPLOAD_BYTES", 32 * 1024 * 1024) + overhead,
            erp_multipart_bytes=_positive_env("MAX_ERP_RECONCILIATION_UPLOAD_BYTES", 16 * 1024 * 1024) + overhead,
        )

    def for_request(self, path: str, content_type: str) -> int:
        if content_type.casefold().startswith("multipart/form-data"):
            return {
                "/api/import/sales": self.sales_multipart_bytes,
                "/api/import/promo-actuals": self.promo_multipart_bytes,
                "/api/import/erp-reconciliation": self.erp_multipart_bytes,
            }.get(path, self.json_bytes)
        return self.json_bytes


class _BodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]], *, limits: RequestBodyLimits | None = None) -> None:
        self.app = app
        self.limits = limits or RequestBodyLimits.from_env()

    async def __call__(self, scope: dict[str, Any], receive: Callable[[], Awaitable[dict[str, Any]]], send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        if scope.get("type") != "http" or scope.get("method") not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin-1").casefold(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        limit = self.limits.for_request(str(scope.get("path", "")), headers.get("content-type", ""))
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await self._reject(send, 400, "Content-Length invalid")
                return
            if declared < 0:
                await self._reject(send, 400, "Content-Length invalid")
                return
            if declared > limit:
                await self._reject(send, 413, "Corpul cererii depaseste limita permisa")
                return

        consumed = 0
        response_started = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal consumed
            message = await receive()
            if message.get("type") == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    raise _BodyTooLarge
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _BodyTooLarge:
            if response_started:
                raise
            await self._reject(send, 413, "Corpul cererii depaseste limita permisa")

    @staticmethod
    async def _reject(send: Callable[[dict[str, Any]], Awaitable[None]], status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}, separators=(",", ":")).encode("utf-8")
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))]})
        await send({"type": "http.response.body", "body": body})
