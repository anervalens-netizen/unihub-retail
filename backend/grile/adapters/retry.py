from __future__ import annotations

import random
import threading
import time
from typing import Callable, TypeVar


T = TypeVar("T")
_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def is_transient_google_error(exc: Exception) -> bool:
    return getattr(getattr(exc, "resp", None), "status", None) in _TRANSIENT_STATUS_CODES


def retry_google_call(
    call: Callable[[], T],
    *,
    attempts: int,
    base_delay: float,
    stop_event: threading.Event | None = None,
    jitter_seconds: float = 0.25,
) -> T:
    if attempts < 1 or base_delay < 0 or jitter_seconds < 0:
        raise ValueError("Invalid Google retry policy")
    for attempt in range(attempts):
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("Grile Google work cancelled")
        try:
            return call()
        except Exception as exc:
            if attempt >= attempts - 1 or not is_transient_google_error(exc):
                raise
            delay = base_delay * (2**attempt)
            if jitter_seconds:
                delay += random.uniform(0, jitter_seconds)
            if stop_event is not None:
                if stop_event.wait(delay):
                    raise RuntimeError("Grile Google work cancelled") from exc
            else:
                time.sleep(delay)
    raise AssertionError("unreachable")
