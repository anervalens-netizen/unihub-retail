# H-16 DB error logging reliability and bounded failure path

## Revalidated defect

`DBErrorHandler._insert()` calls `self.formatException(record.exc_info)`, but `formatException()` belongs to `logging.Formatter`, not `logging.Handler`. The resulting `AttributeError` is caught by a broad silent `except`, so the traceback-bearing event is lost without a metric or fallback signal.

The current handler also creates one independent task per ERROR record. During an error storm this is unbounded, competes for the same PostgreSQL pool that may already be failing, and has no controlled shutdown or queue-drain behavior.

## Implemented behavior

1. Tracebacks are formatted with a real `logging.Formatter` and persisted when the DB sink is healthy.
2. ERROR records are converted synchronously into an immutable, size-bounded event before asynchronous persistence. Do not retain traceback frame objects in the queue.
3. Persistence uses one bounded queue and one consumer task per process, not one task per log record.
4. Queue capacity and DB write timeout are finite and configurable with safe defaults.
5. Queue-full, formatting, loop/handler lifecycle and DB-write failures increment:

   ```text
   db_error_log_dropped_total{reason="..."}
   ```

6. A dropped event emits a short, redacted, direct stderr fallback without using the logging framework and without recursive DB-handler invocation.
7. Sensitive extras are redacted recursively. At minimum redact keys containing: `authorization`, `cookie`, `token`, `secret`, `password`, `cnp`, `salary_cnp`, `client_secret`, `refresh_token`, `access_token`.
8. Message, traceback and JSON extra sizes remain bounded before insertion.
9. Handler attachment is idempotent. Shutdown detaches/drains or cancels the consumer with a bounded timeout before the DB pool is closed.
10. The application remains available if the DB logging sink fails; the primary stream/Sentry logging path remains independent.

## Bounds, metric and redaction

- `DB_ERROR_LOG_QUEUE_SIZE=256`, clamped to `1..4096`.
- `DB_ERROR_LOG_WRITE_TIMEOUT_SECONDS=2.0`, clamped to `0.1..30` seconds for
  the whole acquire plus INSERT operation.
- `DB_ERROR_LOG_DRAIN_TIMEOUT_SECONDS=2.0`, clamped to `0.1..30` seconds.
- event limits: message 2,000 characters, traceback 4,000, extra JSON 8,000,
  stderr fallback 1,000.

`db_error_log_dropped_total{reason}` uses only the stable reasons
`format_error`, `queue_full`, `loop_unavailable`, `persist_timeout`,
`persist_error` and `shutdown_drop`.

Extra values are recursively materialized with depth and collection bounds.
Keys are case-insensitively redacted when they contain `authorization`,
`cookie`, `token`, `secret`, `password`, `cnp`, `salary_cnp`,
`client_secret`, `refresh_token` or `access_token`. Bearer credentials,
password/token/secret key-value text and 13-digit CNP-like values are also
replaced with `[REDACTED]` in message, traceback, path and stderr output.

`DBErrorEvent` is frozen and contains only materialized `message`,
`traceback_text`, `logger_path` and `extra_json`; it never retains a
`LogRecord`, traceback frames, request object or `exc_info`.

`extra_json` is always valid JSON or `None`. If the redacted full payload is
larger than 8,000 characters it is replaced by the valid JSON envelope
`{"_truncated":true,"preview":"..."}`; the final JSON text is never sliced.
Traversal is bounded to 64 items with iterator slicing (and direct slicing for
lists/tuples), so large mappings, sets and generators are not materialized.

## Suggested state/lifecycle

```text
detached -> attached/running -> closing -> detached
```

- `attach_db_error_handler(pool)` captures the running event loop, creates the bounded queue and starts one consumer task.
- `emit(record)` prepares a safe event and schedules only a non-blocking queue insertion on that loop.
- queue insertion from another thread uses `loop.call_soon_threadsafe`.
- `detach_db_error_handler()` is async, stops accepting new records, waits only for a bounded drain interval, cancels the worker if required, removes the handler from the root logger and clears references.

## Failure rules

- Never call `logger.*` from inside the handler failure path.
- Never retry indefinitely.
- Never block the request thread/event loop while waiting for PostgreSQL.
- Never write credentials, tokens, CNP or complete request payloads to stderr or `error_logs`.
- If persistence times out or fails, increment the drop metric once and use direct stderr fallback once.
- If the queue is full, drop the new event rather than evicting or blocking.

The fallback uses only direct bounded `sys.stderr` output. It never calls a
logger or any logging-framework API, so a database sink failure cannot recurse
into this handler.

## Lifecycle and shutdown

`attach_db_error_handler(pool)` runs in an active event loop. It captures that
loop, creates one queue and one consumer, and repeated calls reuse the same
handler/consumer while updating the pool reference deterministically. `emit()`
creates an event synchronously and uses `call_soon_threadsafe` for a
non-blocking `put_nowait`; it never awaits PostgreSQL.

`detach_db_error_handler()` stops new accepts, drains events accepted before
closing up to the configured timeout, counts remaining queue items as
`shutdown_drop`, cancels/awaits the consumer, removes the root handler and
clears all references. Backend shutdown order is: `close_arq_pool`,
`detach_db_error_handler`, then `close_db_pool`.

Callback state (`accepting`, loop/generation and pending callbacks) is guarded
by a lock. Timed-out callbacks are invalidated by generation and counted once;
late callbacks are ignored without decrementing a reset counter. Queued and
in-flight events are identity-counted once as `shutdown_drop`, while an idle
consumer adds no drop. Shutdown emits a single bounded aggregate stderr line:
`DB_ERROR_LOG_DROP reason=shutdown_drop count=N`.

The lifespan cleanup chain is protected by nested `finally` blocks, so all
three shutdown steps are attempted after a startup or prior-cleanup failure.

## Required tests

- `logger.exception()` produces a persisted traceback containing the exception type/message.
- extra fields are serialized and sensitive nested values are redacted.
- queue capacity is bounded and queue overflow increments the drop path without creating extra workers/tasks.
- DB acquire/execute failure uses direct stderr fallback and does not recurse.
- DB write timeout uses the same bounded failure path.
- records emitted before attach and after detach are safely ignored.
- repeated attach does not add duplicate handlers or workers.
- detach completes within a bounded timeout when the DB sink is blocked.
- normal JSON/text logging behavior remains unchanged.

The focused H-16 suite covers the above plus an isolated PostgreSQL
`logger.exception()` round trip, bounded queue overflow, acquire/execute
failure fallback, timeout, repeated attach/detach and the generic FastAPI 500
handler. Google and Sentry are not called by these tests.

Review-hardening tests additionally cover valid truncated JSONB persistence,
bounded iterable traversal, broken `repr`, all textual secret variants,
explicit acquire failure with consumer continuation, in-flight cancellation,
idle detach and startup/cleanup failure ordering.

## Rollback

Revert the H-16 commits and restore the previous handler attachment call. No schema or data migration is required. Existing rows in `error_logs` remain valid.

## Production verification

After an approved Wave 1 deployment:

1. verify the backend starts with one DB error consumer;
2. generate one controlled synthetic ERROR with a harmless exception and a unique test marker;
3. confirm the primary log contains the event;
4. confirm one corresponding `error_logs` row contains the traceback and no sensitive values;
5. confirm `db_error_log_dropped_total` does not increase;
6. remove the synthetic row if operational policy requires it.

Do not simulate a database outage in production.
