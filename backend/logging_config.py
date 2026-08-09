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
import copy
import json
import logging
import math
import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from prometheus_client import Counter

from request_context import request_id_var
from observability.redaction import (
    is_sensitive_key as _is_sensitive_key,
    redact_observability_payload,
    redact_text as _redact_text,
    redact_value as _redact_extra,
    safe_key_text as _safe_key_text,
)

_REDACTION_NODE_BUDGET = 512


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _bounded_env_float(
    name: str, default: float, minimum: float, maximum: float
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    return max(minimum, min(maximum, value))

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

_HANDLER_SKIP_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)

_STREAM_MESSAGE_LIMIT = 20_000
_STREAM_TRACEBACK_LIMIT = 20_000
_STREAM_JSON_LIMIT = 32_000
_EXTRA_JSON_LIMIT = 8_000

def _json_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        default=str,
        separators=(",", ":"),
    )


def _bounded_json_dumps(value: Any, limit: int) -> str:
    encoded = _json_dumps(value)
    if len(encoded) <= limit:
        return encoded

    # Preserve syntactically valid JSON even when the original structure is
    # larger than the DB/log-line budget. A character slice of JSON is invalid.
    low = 0
    high = min(len(encoded), limit)
    best = _json_dumps({"_truncated": True})
    while low <= high:
        middle = (low + high) // 2
        candidate = _json_dumps(
            {
                "_truncated": True,
                "preview": encoded[:middle],
            }
        )
        if len(candidate) <= limit:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


def serialize_bounded_extra_json(value: Any, limit: int = _EXTRA_JSON_LIMIT) -> str:
    """Redact and encode extra data as valid JSON within the JSONB budget."""

    safe_value = _redact_extra(value)
    encoded = _json_dumps(safe_value)
    if len(encoded) <= limit:
        return encoded
    preview_source = _redact_text(encoded, limit)
    return _bounded_json_dumps(
        {"_truncated": True, "preview": preview_source},
        limit,
    )


class JSONFormatter(logging.Formatter):
    """Formatează fiecare LogRecord ca un obiect JSON redactat."""

    def format(self, record: logging.LogRecord) -> str:
        message = _redact_text(record.getMessage(), _STREAM_MESSAGE_LIMIT)
        traceback_text: str | None = None
        if record.exc_info:
            traceback_text = _redact_text(
                self.formatException(record.exc_info),
                _STREAM_TRACEBACK_LIMIT,
            )
        elif record.exc_text:
            traceback_text = _redact_text(
                str(record.exc_text),
                _STREAM_TRACEBACK_LIMIT,
            )

        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": _redact_text(record.name, 1000),
            "message": message,
        }
        if traceback_text:
            entry["exc"] = traceback_text

        extra_data = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _SKIP_FIELDS and not key.startswith("_")
        }
        if extra_data:
            safe_extra = _redact_extra(extra_data)
            if isinstance(safe_extra, dict):
                for key, value in safe_extra.items():
                    target_key = key if key not in entry else f"extra_{key}"
                    entry[target_key] = value
            else:
                entry["extra"] = safe_extra

        return _bounded_json_dumps(entry, _STREAM_JSON_LIMIT)


class RedactingTextFormatter(logging.Formatter):
    """Stdlib text formatter that never emits known secrets or CNP-like values."""

    def format(self, record: logging.LogRecord) -> str:
        safe_record = copy.copy(record)
        safe_record.msg = _redact_text(
            record.getMessage(),
            _STREAM_MESSAGE_LIMIT,
        )
        safe_record.args = ()
        if record.exc_info:
            safe_record.exc_text = _redact_text(
                self.formatException(record.exc_info),
                _STREAM_TRACEBACK_LIMIT,
            )
        elif record.exc_text:
            safe_record.exc_text = _redact_text(
                str(record.exc_text),
                _STREAM_TRACEBACK_LIMIT,
            )
        return super().format(safe_record)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        request_id = request_id_var.get()
        record.request_id = request_id or getattr(record, "request_id", "-")
        return True


def _redact_structlog_event(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    budget = [_REDACTION_NODE_BUDGET]
    output: dict[str, Any] = {}
    for key, value in event_dict.items():
        if _safe_key_text(key).startswith("_"):
            # ProcessorFormatter relies on its internal metadata objects.
            output[key] = value
            continue
        output[key] = (
            "[REDACTED]"
            if _is_sensitive_key(key)
            else _redact_extra(value, budget=budget)
        )
    return output


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
        formatter = RedactingTextFormatter(
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
        _redact_structlog_event,
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
    {
        "format_error",
        "queue_full",
        "loop_unavailable",
        "persist_timeout",
        "persist_error",
        "shutdown_drop",
    }
)


@dataclass(frozen=True)
class DBErrorEvent:
    """Materialized, bounded data safe to retain in the async logging queue."""

    message: str
    traceback_text: str | None
    logger_path: str
    extra_json: str | None


class DBErrorHandler(logging.Handler):
    """Bounded, non-blocking ERROR sink with one PostgreSQL consumer."""

    def __init__(
        self,
        *,
        queue_size: int,
        write_timeout: float,
        drain_timeout: float,
    ) -> None:
        super().__init__(level=logging.ERROR)
        self._pool: object | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[DBErrorEvent] | None = None
        self._consumer: asyncio.Task[None] | None = None
        self._accepting = False
        self._closing = False
        self._pending_callbacks = 0
        self._callback_generation = 0
        self._inflight_event: DBErrorEvent | None = None
        self._shutdown_counted_event_ids: set[int] = set()
        self._queue_size = queue_size
        self._write_timeout = write_timeout
        self._drain_timeout = drain_timeout
        self._formatter = logging.Formatter()
        self._state_lock = threading.Lock()

    def attach(
        self,
        pool: object,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        with self._state_lock:
            if (
                self._consumer is not None
                and not self._consumer.done()
                and self._loop is not None
                and self._loop is not loop
            ):
                raise RuntimeError(
                    "DBErrorHandler is already attached to another event loop"
                )
            self._pool = pool
            self._loop = loop
            self._accepting = True
            self._closing = False
            if self._queue is None:
                self._callback_generation += 1
                self._queue = asyncio.Queue(maxsize=self._queue_size)
            if self._consumer is None or self._consumer.done():
                self._consumer = loop.create_task(
                    self._consume(),
                    name="db-error-log-consumer",
                )

    def _drop(
        self,
        reason: str,
        *,
        event: DBErrorEvent | None = None,
        exc: BaseException | None = None,
    ) -> None:
        if reason not in _DROP_REASONS:
            reason = "persist_error"
        DB_ERROR_LOG_DROPPED_TOTAL.labels(reason=reason).inc()
        if reason != "shutdown_drop":
            _stderr_fallback(
                reason,
                event
                or DBErrorEvent(
                    "[REDACTED]",
                    None,
                    "[REDACTED]",
                    None,
                ),
                exc,
            )

    def _event_from_record(
        self,
        record: logging.LogRecord,
    ) -> DBErrorEvent:
        message = _redact_text(record.getMessage(), 2000)
        traceback_text: str | None = None
        if record.exc_info:
            traceback_text = _redact_text(
                self._formatter.formatException(record.exc_info),
                4000,
            )
        elif record.exc_text:
            traceback_text = _redact_text(str(record.exc_text), 4000)

        extra_data = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _HANDLER_SKIP_FIELDS
            and not key.startswith("_")
        }
        extra_json = serialize_bounded_extra_json(extra_data) if extra_data else None
        return DBErrorEvent(
            message=message,
            traceback_text=traceback_text,
            logger_path=_redact_text(record.name, 1000),
            extra_json=extra_json,
        )

    def _enqueue_event(
        self,
        event: DBErrorEvent,
        *,
        accepted_before_close: bool = False,
    ) -> None:
        with self._state_lock:
            queue = self._queue
            accepting = self._accepting
        if queue is None:
            self._drop(
                "shutdown_drop" if accepted_before_close else "loop_unavailable",
                event=event,
            )
            return
        if not accepting and not accepted_before_close:
            self._drop("loop_unavailable", event=event)
            return
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            self._drop("queue_full", event=event)

    def _enqueue_scheduled_event(
        self,
        event: DBErrorEvent,
        generation: int,
    ) -> None:
        with self._state_lock:
            if generation != self._callback_generation:
                return
            if self._pending_callbacks > 0:
                self._pending_callbacks -= 1
        self._enqueue_event(event, accepted_before_close=True)

    def emit(self, record: logging.LogRecord) -> None:
        with self._state_lock:
            loop = self._loop
            generation = self._callback_generation
            accepting = self._accepting
        if not accepting or loop is None or loop.is_closed():
            return

        try:
            event = self._event_from_record(record)
        except Exception as exc:  # noqa: BLE001 - logging must not escape
            self._drop("format_error", exc=exc)
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is loop:
            self._enqueue_event(event)
            return

        drop_reason: str | None = None
        with self._state_lock:
            if (
                not self._accepting
                or self._loop is not loop
                or loop.is_closed()
                or generation != self._callback_generation
            ):
                drop_reason = "loop_unavailable"
            elif self._pending_callbacks >= self._queue_size:
                drop_reason = "queue_full"
            else:
                self._pending_callbacks += 1

        if drop_reason is not None:
            self._drop(drop_reason, event=event)
            return

        try:
            loop.call_soon_threadsafe(
                self._enqueue_scheduled_event,
                event,
                generation,
            )
        except RuntimeError:
            with self._state_lock:
                if (
                    generation == self._callback_generation
                    and self._pending_callbacks > 0
                ):
                    self._pending_callbacks -= 1
            self._drop("loop_unavailable", event=event)

    async def _consume(self) -> None:
        queue = self._queue
        assert queue is not None
        while True:
            event = await queue.get()
            with self._state_lock:
                self._inflight_event = event
            try:
                await self._persist(event)
            except asyncio.CancelledError:
                if self._closing:
                    self._count_shutdown_events([event])
                raise
            finally:
                with self._state_lock:
                    self._inflight_event = None
                queue.task_done()

    def _count_shutdown_events(self, events: list[DBErrorEvent]) -> None:
        with self._state_lock:
            new_events = [event for event in events if id(event) not in self._shutdown_counted_event_ids]
            self._shutdown_counted_event_ids.update(id(event) for event in new_events)
        if new_events:
            DB_ERROR_LOG_DROPPED_TOTAL.labels(reason="shutdown_drop").inc(len(new_events))
            _stderr_shutdown_fallback(len(new_events))

    def _count_shutdown_callbacks(self, count: int) -> None:
        if count > 0:
            DB_ERROR_LOG_DROPPED_TOTAL.labels(reason="shutdown_drop").inc(count)
            _stderr_shutdown_fallback(count)

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

    async def _wait_for_pending_callbacks(self) -> None:
        while True:
            with self._state_lock:
                pending = self._pending_callbacks
            if pending == 0:
                return
            await asyncio.sleep(0)

    async def detach(self) -> None:
        running_loop = asyncio.get_running_loop()
        deadline = running_loop.time() + self._drain_timeout

        with self._state_lock:
            self._accepting = False
            self._closing = True
            queue = self._queue
            consumer = self._consumer
            callback_generation = self._callback_generation

        def remaining() -> float:
            return max(0.0, deadline - running_loop.time())

        pending_timed_out = False
        with self._state_lock:
            has_pending_callbacks = self._pending_callbacks > 0
        if has_pending_callbacks:
            try:
                async with asyncio.timeout(remaining()):
                    await self._wait_for_pending_callbacks()
            except TimeoutError:
                pending_timed_out = True

        if pending_timed_out:
            with self._state_lock:
                stale_callbacks = self._pending_callbacks
                self._pending_callbacks = 0
                if callback_generation == self._callback_generation:
                    self._callback_generation += 1
            self._count_shutdown_callbacks(stale_callbacks)

        if queue is not None:
            try:
                async with asyncio.timeout(remaining()):
                    await queue.join()
            except TimeoutError:
                while True:
                    try:
                        dropped = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    queue.task_done()
                    self._count_shutdown_events([dropped])

        if consumer is not None and not consumer.done():
            consumer.cancel()
            done, _pending = await asyncio.wait(
                {consumer},
                timeout=max(0.05, remaining()),
            )
            if not done:
                # Cancellation is already requested. Avoid blocking shutdown
                # indefinitely; count the uncertain in-flight event once and
                # consume any eventual task exception.
                with self._state_lock:
                    inflight_event = self._inflight_event
                if inflight_event is not None:
                    self._count_shutdown_events([inflight_event])
                consumer.add_done_callback(_consume_task_result)

        with self._state_lock:
            self._pool = None
            self._loop = None
            self._queue = None
            self._consumer = None
            self._accepting = False
            self._closing = False
            # Late callbacks see the new generation and never decrement this
            # counter or re-count the callbacks already accounted above.
            self._pending_callbacks = 0
            self._callback_generation += 1
            self._inflight_event = None


def _consume_task_result(task: asyncio.Task[Any]) -> None:
    with contextlib.suppress(asyncio.CancelledError, Exception):
        task.result()


def _stderr_fallback(
    reason: str,
    event: DBErrorEvent,
    exc: BaseException | None = None,
) -> None:
    sink_type = type(exc).__name__ if exc is not None else ""
    line = _redact_text(
        "DB_ERROR_LOG_DROP "
        f"reason={reason} "
        f"logger={event.logger_path} "
        f"message={event.message} "
        f"sink={sink_type}",
        1000,
    )
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _stderr_shutdown_fallback(count: int) -> None:
    try:
        sys.stderr.write(f"DB_ERROR_LOG_DROP reason=shutdown_drop count={count}\n"[:1000])
        sys.stderr.flush()
    except Exception:
        pass


def attach_db_error_handler(pool: object) -> None:
    """Attach one bounded DB sink from an active application event loop."""
    global _db_handler_instance
    loop = asyncio.get_running_loop()
    if _db_handler_instance is None:
        _db_handler_instance = DBErrorHandler(
            queue_size=_bounded_env_int(
                "DB_ERROR_LOG_QUEUE_SIZE",
                256,
                1,
                4096,
            ),
            write_timeout=_bounded_env_float(
                "DB_ERROR_LOG_WRITE_TIMEOUT_SECONDS",
                2.0,
                0.1,
                30.0,
            ),
            drain_timeout=_bounded_env_float(
                "DB_ERROR_LOG_DRAIN_TIMEOUT_SECONDS",
                2.0,
                0.1,
                30.0,
            ),
        )
        logging.getLogger().addHandler(_db_handler_instance)
    _db_handler_instance.attach(pool, loop)


async def detach_db_error_handler() -> None:
    """Stop accepting DB log events and detach the handler before pool close."""
    global _db_handler_instance
    handler = _db_handler_instance
    if handler is None:
        return
    try:
        await handler.detach()
    finally:
        logging.getLogger().removeHandler(handler)
        _db_handler_instance = None
