# Retail readiness, liveness and SLO

## Probe contract

| Endpoint | Meaning | Dependencies | Success |
| --- | --- | --- | --- |
| `/livez` | the uvicorn process and event loop can answer | none | `200 {"status":"alive"}` |
| `/readyz` | authenticated Retail requests can be served | PostgreSQL, Valkey-backed BFF sessions and usable JWKS state | `200 {"status":"ok"}` |
| `/health` | compatibility alias for `/readyz` | same as `/readyz` | same as `/readyz` |

Readiness has one total two-second deadline. Dependency failures and timeouts
return the same bounded `503 {"status":"unhealthy"}` response; connection
strings, hosts, paths and exception details remain in server logs only.

Startup prewarms JWKS before the instance can be considered healthy. Readiness
does not require a successful live IdP request on every probe: a validated cache
inside `JWKS_MAX_STALE_SECONDS` is usable and reports `stale`; absent/expired
keys after a failed refresh return 503. The one-hot metric
`jwks_readiness_state{state="disabled|absent|fresh|stale|failed"}` distinguishes
bootstrap, healthy cache, bounded degradation and failure without high-cardinality
labels. ARQ remains excluded because queue availability does not prevent the
read-heavy application from serving established sessions. Valkey is checked
because every authenticated request depends on the server-side session.

## Service levels

The initial monthly objectives are:

- availability: at least 99.5% successful non-probe HTTP requests, where only
  5xx consumes the error budget; expected 3xx/4xx auth and validation responses
  do not;
- external readiness: at least 99.5% successful `/readyz` probes;
- latency: p95 below 2 seconds for non-probe HTTP requests;
- Dashboard component p95 below 2 seconds, investigated by the finite
  `component` labels on `dashboard_component_duration_seconds`.

The monthly 0.5% availability error budget is approximately 3 hours 39 minutes.
Current traffic is low, so alerts require both a ratio breach and at least
0.05 non-probe requests/second over five minutes. The existing any-5xx warning
remains the early low-volume signal; the SLO alert is the sustained critical
signal.

Unhandled application exceptions are explicitly counted as 5xx before they
reach FastAPI's outer exception handler. Health, readiness, liveness and metrics
traffic are excluded from the request SLI so probes cannot dilute real errors.

## Versioned operations files

- `ops/observability/retail-slo-rules.yml`: recording and alert rules;
- `ops/observability/retail-slo-rules.test.yml`: synthetic recording and alert
  contract exercised by `promtool`;
- `ops/observability/retail-readiness-scrape.yml`: dedicated external probe;
- `ops/systemd/unihub-backend.service`: web unit source of truth;
- `unihub-worker.service`, `unihub-import-worker.service`,
  `unihub-grile-worker.service`, `unihub-export-worker.service`,
  `unihub-salary-export-worker.service`: worker unit sources of truth;
- `ops/systemd/unihub-retail-migrate.service`: one-shot migration unit.

The production Prometheus rules directory is
`/opt/Mobiup/infra/observability/prometheus/rules/`. The shared scrape config is
`/opt/Mobiup/infra/observability/prometheus/prometheus.yml`. Install the app and
probe endpoint first, then load the probe and alert rules; reversing that order
would create an avoidable readiness alert during deployment.

## Validation

```bash
curl -fsS http://127.0.0.1:9898/livez
curl -fsS http://127.0.0.1:9898/readyz
curl -fsS https://retail.unihub.ro/readyz

backend/venv/bin/python scripts/check_prometheus_contract.py
promtool check rules ops/observability/retail-slo-rules.yml
promtool test rules ops/observability/retail-slo-rules.test.yml
systemd-analyze verify \
  ops/systemd/unihub-backend.service \
  unihub-worker.service \
  ops/systemd/unihub-import-worker.service \
  ops/systemd/unihub-grile-worker.service \
  ops/systemd/unihub-export-worker.service \
  ops/systemd/unihub-salary-export-worker.service \
  ops/systemd/unihub-retail-migrate.service
```

After Prometheus reload, verify `probe_success{job="blackbox_retail_readiness"}`
and `jwks_readiness_state{state="fresh"} == 1` (or bounded `stale` during an
explicit IdP incident), plus all four `unihub_retail:*` HTTP recording rules through the local
Prometheus API. The deploy gate creates one bounded Dashboard request so the
Dashboard latency recording cannot pass only by being absent. Worker alerts
cover scrape target absence/down, self-reported down, backlog/age, failure
ratio, p95 duration and stale/failing Grile reconciliation. A normal deployment
restarts only the units whose code or unit file changed. Never run the migration
service unless a reviewed migration is actually pending.

GitHub CI repeats `systemd-analyze verify`, the selector/recording semantic
checker and both `promtool` commands, so invalid or vacuous service/alert
configuration blocks the merge ref.
