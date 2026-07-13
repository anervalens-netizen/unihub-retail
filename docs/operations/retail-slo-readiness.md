# Retail readiness, liveness and SLO

## Probe contract

| Endpoint | Meaning | Dependencies | Success |
| --- | --- | --- | --- |
| `/livez` | the uvicorn process and event loop can answer | none | `200 {"status":"alive"}` |
| `/readyz` | authenticated Retail requests can be served | PostgreSQL and Valkey-backed BFF sessions | `200 {"status":"ok"}` |
| `/health` | compatibility alias for `/readyz` | same as `/readyz` | same as `/readyz` |

Readiness has one total two-second deadline. Dependency failures and timeouts
return the same bounded `503 {"status":"unhealthy"}` response; connection
strings, hosts, paths and exception details remain in server logs only.

OIDC discovery/JWKS network access is intentionally not a readiness dependency:
the verifier has a bounded stale-key policy and authenticated requests must not
be removed from service by a transient provider fetch. ARQ is also excluded
because queue availability does not prevent the read-heavy application from
serving established sessions. Valkey is checked because every authenticated
request depends on the server-side session.

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
- `ops/observability/retail-readiness-scrape.yml`: dedicated external probe;
- `ops/systemd/unihub-backend.service`: web unit source of truth;
- `unihub-worker.service`: worker unit source of truth;
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

promtool check rules ops/observability/retail-slo-rules.yml
systemd-analyze verify \
  ops/systemd/unihub-backend.service \
  unihub-worker.service \
  ops/systemd/unihub-retail-migrate.service
```

After Prometheus reload, verify `probe_success{job="blackbox_retail_readiness"}`
and all three `unihub_retail:*` recording rules through the local Prometheus
API. A normal deployment restarts only the units whose code or unit file
changed. Never run the migration service unless a reviewed migration is
actually pending.

GitHub CI repeats both `systemd-analyze verify` and `promtool check rules`, so
invalid service or alert configuration blocks the merge ref.
