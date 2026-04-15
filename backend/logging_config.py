"""Structured JSON logging configuration.

Activat cu LOG_FORMAT=json în environment.
Fără această variabilă, comportamentul e identic cu stdlib default (text plain).

Usage în main.py (top-level, înainte de FastAPI()):
    from logging_config import setup_logging
    setup_logging()
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

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


def setup_logging(fmt: str | None = None) -> None:
    """Configurează logging-ul aplicației.

    Args:
        fmt: "json" pentru JSON structurat, altceva/None pentru text plain.
             Dacă nu e specificat, citește din LOG_FORMAT env var.
    """
    if fmt is None:
        fmt = os.getenv("LOG_FORMAT", "text")

    if fmt != "json":
        # Comportament default — nu modificăm nimic
        return

    formatter = JSONFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

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
