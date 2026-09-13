"""Bounded generation fencing for composed sales-derived reads.

Dashboard already fences its composed response by reading the append-only sales
promotion epoch before and after the load: a moved epoch discards the whole
response, one retry rebuilds it, and a second move is a controlled availability
failure rather than a silently mixed response. Forecast and Exports compose the
same class of sales-derived reads across several statements, and PostgreSQL
READ COMMITTED gives every statement its own snapshot, so reusing one connection
is not reusing one sales generation.

This module is that accept/discard/retry semantic as a small shared primitive.
It deliberately owns no SQL and no pool: the caller supplies the epoch reader so
the repository layer stays the only layer that touches the database. A
long-lived transaction is never held - the fence covers the DB reads only, so
callers must close it before rendering or serializing an artifact.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

REPORTING_GENERATION_UNSTABLE_DETAIL = (
    "Datele de vanzari s-au modificat in timpul incarcarii. Reincercati."
)
_REPORTING_GENERATION_LOAD_ATTEMPTS = 2


class ReportingGenerationUnstable(RuntimeError):
    """Sales/reporting generation changed during every bounded load attempt."""


async def load_reporting_result_once_stable(
    *,
    read_epoch: Callable[[], Awaitable[int]],
    load: Callable[[], Awaitable[T]],
    operation: str,
) -> T:
    """Return the first composed load whose surrounding sales generation held.

    Exactly one retry is attempted. A rejected attempt is discarded whole, so
    the caller must rebuild from scratch and never merge pieces of two attempts;
    a load that raises propagates unchanged and is never retried.
    """
    for _attempt in range(_REPORTING_GENERATION_LOAD_ATTEMPTS):
        before = await read_epoch()
        result = await load()
        after = await read_epoch()
        if before == after:
            return result
    raise ReportingGenerationUnstable(
        f"Sales generation changed during every {operation} load attempt"
    )
