"""Structured JSON/structlog logging configuration.

Activat cu LOG_FORMAT=json sau LOG_FORMAT=structlog în environment.
Fără această variabilă, comportamentul e identic cu stdlib default (text plain).

Usage în main.py (top-level, înainte de FastAPI()):
    from logging_config import setup_logging
    setup_logging()
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

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
        if request_id is not None:
            record.request_id = request_id
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

    if fmt != "json":
        # Comportament default — nu modificăm nimic
        return

    formatter = JSONFormatter()
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

_HANDLER_SKIP_FIELDS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "message",
    "taskName",
})


class DBErrorHandler(logging.Handler):
    """Handler async non-blocking — inserează ERROR+ în tabelul error_logs.

    Activat prin attach_db_error_handler(pool) după init_db_pool().
    Înainte de attach sau dacă event loop-ul nu rulează, emit() e no-op.
    Niciodată nu ridică excepții — erorile de scriere în DB sunt silențioase.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._pool: object | None = None

    def attach(self, pool: object) -> None:
        self._pool = pool

    def emit(self, record: logging.LogRecord) -> None:
        if self._pool is None:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._insert(record))
        except Exception:
            pass

    async def _insert(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            traceback_text: str | None = None
            if record.exc_info:
                traceback_text = self.formatException(record.exc_info)  # type: ignore[attr-defined]

            extra_data = {
                k: v for k, v in record.__dict__.items()
                if k not in _HANDLER_SKIP_FIELDS and not k.startswith("_")
            }
            extra_json = json.dumps(extra_data, default=str) if extra_data else None

            async with self._pool.acquire() as conn:  # type: ignore[union-attr]
                await conn.execute(
                    """
                    INSERT INTO error_logs
                        (source, level, message, traceback, path, extra)
                    VALUES ('backend', 'error', $1, $2, $3, $4)
                    """,
                    message[:2000],
                    (traceback_text or "")[:4000] or None,
                    record.name,
                    extra_json,
                )
        except Exception:
            pass  # Niciodată nu crăpa din cauza logging-ului


def attach_db_error_handler(pool: object) -> None:
    """Activează DBErrorHandler pe root logger. Apelat după init_db_pool."""
    global _db_handler_instance
    if _db_handler_instance is None:
        _db_handler_instance = DBErrorHandler()
        logging.getLogger().addHandler(_db_handler_instance)
    _db_handler_instance.attach(pool)
