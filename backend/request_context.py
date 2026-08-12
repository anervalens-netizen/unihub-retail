from __future__ import annotations

import re
import uuid
import logging
import os
import time
from contextvars import ContextVar, Token
from typing import Any

import sentry_sdk
from structlog.contextvars import bind_contextvars, clear_contextvars
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from observability.prometheus import canonical_handler

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("unihub.request")
_SERVICE_ROLES = frozenset(
    {"operations", "imports", "grile", "exports", "salary_exports"}
)


def normalize_request_id(raw_request_id: str | None) -> str:
    candidate = (raw_request_id or "").strip()
    if candidate and len(candidate) <= 128 and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


def get_request_id(default: str | None = None) -> str | None:
    return request_id_var.get(default)


def bind_request_id(request_id: str) -> Token[str | None]:
    clear_contextvars()
    bind_contextvars(request_id=request_id)
    return request_id_var.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    request_id_var.reset(token)
    clear_contextvars()


def apply_request_id_to_sentry_scope(scope: Any, request_id: str) -> None:
    scope.set_tag("request_id", request_id)
    scope.set_extra("request_id", request_id)


def telemetry_service_role() -> str:
    role = os.getenv("RETAIL_WORKER_ROLE", "").strip().lower()
    return role if role in _SERVICE_ROLES else "web"


def apply_route_to_sentry_scope(scope: Any, route_template: str) -> None:
    scope.set_tag("route_template", route_template)
    scope.set_tag("service_role", telemetry_service_role())
    set_transaction_name = getattr(scope, "set_transaction_name", None)
    if callable(set_transaction_name):
        set_transaction_name(route_template)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = normalize_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        started_at = time.perf_counter()
        token = bind_request_id(request_id)
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        with sentry_sdk.isolation_scope() as sentry_scope:
            apply_request_id_to_sentry_scope(sentry_scope, request_id)
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                route_template = canonical_handler(scope)
                apply_route_to_sentry_scope(sentry_scope, route_template)
                logger.info(
                    "request completed",
                    extra={
                        "request_id": request_id,
                        "method": scope.get("method", "-"),
                        "route_template": route_template,
                        "status": status_code,
                        "duration_ms": round(
                            (time.perf_counter() - started_at) * 1000,
                            2,
                        ),
                        "service_role": telemetry_service_role(),
                    },
                )
                reset_request_id(token)
