# P2.2 Dashboard deadline and Target forecast coverage

## Request contract

Every `/api/dashboard/*` request has one monotonic deadline. The default is
`DASHBOARD_REQUEST_DEADLINE_MS=2500`; configuration must be a positive integer.
The router maps the typed expiry to HTTP `504`. Components do not receive a new
budget: batch items and concurrent `/all` components share the originating
deadline, so cancellation stops outstanding work and no new database call may
begin after expiry.

`DeadlinePool` wraps each acquired Dashboard connection. `fetch`, `fetchrow`,
`fetchval`, and `execute` receive the positive remaining asyncpg `timeout` at
the point of each operation. Repository queries, direct Dashboard components,
premium-glass, and special-cards use this wrapper; global PostgreSQL timeout
settings remain unchanged.

## Store filter boundary

Dashboard API endpoints canonicalize `site_code` once before service logic:
split comma selections, trim, uppercase, deduplicate, and sort. Batch payloads
perform the identical canonicalization through `DashboardAllQuery` validation.
The service receives the canonical value and does not normalize `site_code`
again. Other payload fields and business calculations are unchanged.

## Forecast coverage contract

Target current forecast comes from one selected completed AI run, therefore its
coverage mode is `uniform`: `cutoff_month`, `min_cutoff_month`, and
`max_cutoff_month` are the run's `source_month`. The profitability summary adds
`forecast_coverage` with expected/covered store counts and sorted
`missing_site_codes`.

An absent run is `unavailable`; all expected stores remain missing. A NULL or
absent forecast row is never coerced to zero. Any missing store makes
`forecast_total` `null`, while the per-store row carries `FORECAST_MISSING`.
Existing frozen Target scenarios retain their saved profitability payload and
are not re-read or rewritten by this change.

## Verification

```bash
cd /opt/Mobiup/unihub-retail
env -u PYTHONHOME -u PYTHONPATH backend/scripts/run_tests_isolated.sh -q
env -u PYTHONHOME -u PYTHONPATH backend/venv/bin/mypy backend/ --ignore-missing-imports --explicit-package-bases
```

Focused evidence covers shared deadline cancellation, positive DB timeout
propagation, no post-expiry query, endpoint `504`, direct and batch store-code
canonicalization, and complete/partial uniform forecast coverage.
