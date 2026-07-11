"""Structured JSON/structlog logging configuration.

Activat cu LOG_FORMAT=json sau LOG_FORMAT=structlog în environment.
Fără această variabilă, comportamentul e identic cu stdlib default (text plain).

Usage în main.py (top-level, înainte de FastAPI()):
    from logging_config import setup_logging
    setup_logging()
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from prometheus_client import Counter

from request_context import request_id_var

# Câmpuri interne Python LogRecord care nu au valoare în JSON output
_SKIP_FIELDS = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JSONFormatter(logging.Formatter):
    """Formatează fiecare LogRecord ca un obiect JSON pe o singură linie."""

    def format(self, record: logging.LogRecord) -> str:
        # Asigură că record.message e populat (folosit de unele handlere)
        record.message = record.getMessage()
        if record.exc_info:
            # Adaugă traceback-ul ca string — util pentru Loki / Sentry ingestion
            record.exc_text = self.formatException(record.exc_info)

        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }
        if record.exc_text:
            entry["exc"] = record.exc_text

        # Orice câmp extra adăugat cu logger.info("msg", extra={"key": val})
        for key, val in record.__dict__.items():
            if key not in _SKIP_FIELDS and not key.startswith("_"):
                entry[key] = val

        return json.dumps(entry, default=str)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        request_id = request_id_var.get()
        record.request_id = request_id or getattr(record, "request_id", "-")
        return True


def setup_logging(fmt: str | None = None) -> None:
    """Configurează logging-ul aplicației.

    Args:
        fmt: "json" pentru JSON structurat, "structlog" pentru structlog,
             altceva/None pentru text plain.
             Dacă nu e specificat, citește din LOG_FORMAT env var.
    """
    if fmt is None:
        fmt = os.getenv("LOG_FORMAT", "text")

    if fmt == "structlog":
        _setup_structlog()
        return

    formatter: logging.Formatter
    if fmt == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s "
            "request_id=%(request_id)s %(message)s",
        )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())

    # Root logger — prinde toți loggerii aplicației
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # uvicorn creează loggerii proprii cu propagate=False —
    # trebuie configurați explicit
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.addHandler(handler)
        uvicorn_logger.propagate = False


def _setup_structlog() -> None:
    import structlog

    timestamper = structlog.processors.TimeStamper(fmt="iso")
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.remove_processors_meta],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.addHandler(handler)
        uvicorn_logger.propagate = False


# ── DB Error Handler ──────────────────────────────────────────────────────────

_db_handler_instance: "DBErrorHandler | None" = None

DB_ERROR_LOG_DROPPED_TOTAL = Counter(
    "db_error_log_dropped_total",
    "DB error-log events that could not be persisted.",
    ("reason",),
)

_DROP_REASONS = frozenset(
    {"format_error", "queue_full", "loop_unavailable", "persist_timeout", "persist_error", "shutdown_drop"}
)
_SENSITIVE_KEY_PARTS = (
    "authorization", "cookie", "token", "secret", "password", "cnp",
    "salary_cnp", "client_secret", "refresh_token", "access_token",
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(password|token|secret|authorization|cookie|cnp)\s*=\s*([^\s,;]+)"
)
_CNP_RE = re.compile(r"\b\d{13}\b")


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _bounded_env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _redact_text(value: str, limit: int) -> str:
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    value = _KEY_VALUE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    value = _CNP_RE.sub("[REDACTED]", value)
    return value[:limit]


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).casefold()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _redact_extra(value: Any, *, depth: int = 0, seen: set[int] | None = None) -> Any:
    if depth >= 8:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return _redact_text(value, 2000)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    seen = seen if seen is not None else set()
    value_id = id(value)
    if value_id in seen:
        return "[CIRCULAR]"
    seen.add(value_id)
    try:
        if isinstance(value, dict):
            return {
                str(key)[:200]: "[REDACTED]" if _is_sensitive_key(key) else _redact_extra(item, depth=depth + 1, seen=seen)
                for key, item in list(value.items())[:64]
            }
        if isinstance(value, (list, tuple, set, frozenset)):
            return [_redact_extra(item, depth=depth + 1, seen=seen) for item in list(value)[:64]]
        return _redact_text(repr(value), 2000)
    finally:
        seen.discard(value_id)


@dataclass(frozen=True)
class DBErrorEvent:
    """Materialized, bounded data safe to retain in the async logging queue."""

    message: str
    traceback_text: str | None
    logger_path: str
    extra_json: str | None

_HANDLER_SKIP_FIELDS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "message",
    "taskName",
})


class DBErrorHandler(logging.Handler):
    """Bounded, non-blocking ERROR sink with a single PostgreSQL consumer."""

    def __init__(self, *, queue_size: int, write_timeout: float, drain_timeout: float) -> None:
        super().__init__(level=logging.ERROR)
        self._pool: object | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[DBErrorEvent] | None = None
        self._consumer: asyncio.Task[None] | None = None
        self._accepting = False
        self._pending_callbacks = 0
        self._queue_size = queue_size
        self._write_timeout = write_timeout
        self._drain_timeout = drain_timeout
        self._formatter = logging.Formatter()

    def attach(self, pool: object, loop: asyncio.AbstractEventLoop) -> None:
        self._pool = pool
        self._loop = loop
        self._accepting = True
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._queue_size)
        if self._consumer is None or self._consumer.done():
            self._consumer = loop.create_task(self._consume(), name="db-error-log-consumer")

    def _drop(self, reason: str, *, event: DBErrorEvent | None = None, exc: BaseException | None = None) -> None:
        if reason not in _DROP_REASONS:
            reason = "persist_error"
        DB_ERROR_LOG_DROPPED_TOTAL.labels(reason=reason).inc()
        if reason != "shutdown_drop":
            _stderr_fallback(
                reason,
                event or DBErrorEvent("[REDACTED]", None, "[REDACTED]", None),
                exc,
            )

    def _event_from_record(self, record: logging.LogRecord) -> DBErrorEvent:
        message = _redact_text(record.getMessage(), 2000)
        traceback_text: str | None = None
        if record.exc_info:
            traceback_text = _redact_text(self._formatter.formatException(record.exc_info), 4000)
        extra_data = {
            key: value for key, value in record.__dict__.items()
            if key not in _HANDLER_SKIP_FIELDS and not key.startswith("_")
        }
        extra_json = json.dumps(_redact_extra(extra_data), ensure_ascii=False, default=str) if extra_data else None
        if extra_json is not None:
            extra_json = _redact_text(extra_json, 8000)
        return DBErrorEvent(
            message=message,
            traceback_text=traceback_text,
            logger_path=_redact_text(record.name, 1000),
            extra_json=extra_json,
        )

    def _enqueue_event(self, event: DBErrorEvent, *, accepted_before_close: bool = False) -> None:
        try:
            if (not self._accepting and not accepted_before_close) or self._queue is None:
                self._drop("loop_unavailable", event=event)
                return
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                self._drop("queue_full", event=event)
        finally:
            if accepted_before_close:
                self._pending_callbacks -= 1

    def emit(self, record: logging.LogRecord) -> None:
        if not self._accepting or self._loop is None or self._loop.is_closed():
            return
        try:
            event = self._event_from_record(record)
        except Exception as exc:  # noqa: BLE001 - logging must not escape
            self._drop("format_error", exc=exc)
            return
        try:
            self._pending_callbacks += 1
            self._loop.call_soon_threadsafe(
                lambda: self._enqueue_event(event, accepted_before_close=True)
            )
        except RuntimeError:
            self._pending_callbacks -= 1
            self._drop("loop_unavailable", event=event)

    async def _consume(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            try:
                await self._persist(event)
            finally:
                self._queue.task_done()

    async def _persist(self, event: DBErrorEvent) -> None:
        try:
            async with asyncio.timeout(self._write_timeout):
                pool: Any = self._pool
                if pool is None:
                    raise RuntimeError("DB error sink pool unavailable")
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO error_logs
                            (source, level, message, traceback, path, extra)
                        VALUES ('backend', 'error', $1, $2, $3, $4::jsonb)
                        """,
                        event.message,
                        event.traceback_text,
                        event.logger_path,
                        event.extra_json,
                    )
        except TimeoutError as exc:
            self._drop("persist_timeout", event=event, exc=exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - persistence failure is isolated
            self._drop("persist_error", event=event, exc=exc)

    async def detach(self) -> None:
        self._accepting = False
        queue = self._queue
        consumer = self._consumer
        if self._pending_callbacks:
            try:
                async with asyncio.timeout(self._drain_timeout):
                    while self._pending_callbacks:
                        await asyncio.sleep(0)
            except TimeoutError:
                self._pending_callbacks = 0
        if queue is not None:
            try:
                async with asyncio.timeout(self._drain_timeout):
                    await queue.join()
            except TimeoutError:
                while True:
                    try:
                        dropped = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    queue.task_done()
                    self._drop("shutdown_drop", event=dropped)
        if consumer is not None and not consumer.done():
            consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consumer
        self._pool = None
        self._loop = None
        self._queue = None
        self._consumer = None
        self._pending_callbacks = 0


def _stderr_fallback(reason: str, event: DBErrorEvent, exc: BaseException | None = None) -> None:
    sink_type = type(exc).__name__ if exc is not None else ""
    line = _redact_text(
        f"DB_ERROR_LOG_DROP reason={reason} logger={event.logger_path} message={event.message} sink={sink_type}",
        1000,
    )
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def attach_db_error_handler(pool: object) -> None:
    """Attach one bounded DB sink from an active application event loop."""
    global _db_handler_instance
    loop = asyncio.get_running_loop()
    if _db_handler_instance is None:
        _db_handler_instance = DBErrorHandler(
            queue_size=_bounded_env_int("DB_ERROR_LOG_QUEUE_SIZE", 256, 1, 4096),
            write_timeout=_bounded_env_float("DB_ERROR_LOG_WRITE_TIMEOUT_SECONDS", 2.0, 0.1, 30.0),
            drain_timeout=_bounded_env_float("DB_ERROR_LOG_DRAIN_TIMEOUT_SECONDS", 2.0, 0.1, 30.0),
        )
        logging.getLogger().addHandler(_db_handler_instance)
    _db_handler_instance.attach(pool, loop)


async def detach_db_error_handler() -> None:
    """Stop accepting DB log events and detach the handler before pool close."""
    global _db_handler_instance
    handler = _db_handler_instance
    if handler is None:
        return
    await handler.detach()
    logging.getLogger().removeHandler(handler)
    _db_handler_instance = None
