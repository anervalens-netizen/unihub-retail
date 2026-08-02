# P2.2 Dashboard deadline and Target forecast coverage

## Request contract

Every `/api/dashboard/*` request creates one absolute monotonic deadline before
pool/dependency resolution. `DASHBOARD_REQUEST_DEADLINE_MS` is a validated web
`RuntimeConfig` value (default `2500`, positive, max `3000`); it is never read
from the environment per request. The router maps only typed deadline expiry to
HTTP `504`; `CancelledError` / client disconnect propagates.

All Dashboard children share this same deadline: batch items, `/all` loaders,
campaign and promo tasks are cancelled and awaited before the endpoint exits.
`DeadlinePool` bounds both `pool.acquire()` and every `fetch`, `fetchrow`,
`fetchval`, and `execute` with the positive remaining asyncpg budget, reserving
a small cleanup interval. No new DB operation starts once the deadline is
expired; no pooled session setting is changed.

`DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY` is also parsed once at web startup.
It must be no greater than `DB_POOL_MAX_SIZE - 2`; the two connections remain
reserved for the request path. The injected web runtime config creates the
per-event-loop global semaphore; `dashboard_service` has no import-time
Dashboard environment parsing.

## Store filter boundary

Dashboard API boundaries canonicalize `site_code` exactly once: CSV tokens are
trimmed, empty/UI-sentinel values dropped, and duplicate *exact* codes removed
while preserving first order and case. Thus `" S1,S1, S2 "` is `"S1,S2"`; an
empty/sentinel-only scope is `null`. This applies to GET endpoints, both batch
routes through `DashboardAllQuery`, and the store key of `performance-detail`.
Services/repositories receive this immutable scope; unknown codes retain the
existing empty-result behavior.

## Forecast coverage contract

The current AI run is checked per expected cohort store. A row is covered only
when both the forecast and realized reporting source exist, the forecast value
is non-NULL (a real numeric zero is valid), and the store's realized cutoff is
present. Coverage is deterministic:

- `uniform`: every cohort store is covered and all cutoffs match;
- `nonuniform`: different cutoffs, a missing source/forecast, or no rows;
- `cutoff` is present only for `uniform`; `cutoff_min`, `cutoff_max`, expected /
  covered counts, and sorted `missing_site_codes` are always explicit.

The existing v2 calculation refuses `nonuniform` coverage with HTTP `409`
before any scenario/revision write. The coverage contract is included in the
new scenario's profitability input hash and frozen snapshot. Frozen and legacy
scenarios are not backfilled, re-read from live P&L/forecast, or changed.

## Verification

```bash
cd /opt/Mobiup/unihub-retail
env -u PYTHONHOME -u PYTHONPATH backend/scripts/run_tests_isolated.sh -q
env -u PYTHONHOME -u PYTHONPATH backend/venv/bin/mypy backend/ --ignore-missing-imports --explicit-package-bases
```

Focused tests cover pool acquire starvation/recovery and `pg_sleep`, shared
12-item batch budget, child reaping, client cancellation, API filter boundary,
web startup config limits, and uniform/nonuniform/missing/zero forecast cases
with zero writes for every v2 refusal.
