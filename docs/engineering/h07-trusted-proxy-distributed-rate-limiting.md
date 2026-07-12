# H-07 — Trusted proxy identity and distributed rate limiting

## Purpose

H-07 replaces the current process-local, spoofable and unbounded request limiter with a fail-closed, Valkey-backed control whose client identity is derived only from a verified peer/proxy chain.

This work follows the technically completed H-01A and H-04/H-05 changes on `stabilization/audit-remediation-wave2-privacy`. It does not modify browser token storage, the OIDC proxy contract, Authentik, PostgreSQL, CNP storage or application business rules.

## Confirmed current risks

`backend/rate_limits.py` currently:

- trusts `cf-connecting-ip` from any peer;
- trusts the first `x-forwarded-for` entry from any peer;
- combines authenticated subject and client IP, allowing an authenticated caller to multiply the effective quota by changing networks;
- stores buckets in a process-local dictionary with no global key eviction;
- resets all limits on restart;
- multiplies the effective quota when more than one web process is used;
- parses policy environment values at import time and silently replaces invalid values with defaults;
- returns only `Retry-After`, without a consistent limit/remaining/reset contract.

These properties permit forwarded-header spoofing, inconsistent enforcement, memory growth and bypass across processes.

## Scope

### In scope

- read-only inventory of the real reverse-proxy chain before implementation;
- typed, fail-closed trusted-proxy and rate-limit settings;
- canonical client-IP resolution using `request.client` as the trust root;
- verified use of Cloudflare or X-Forwarded-For headers only from trusted direct peers;
- stable privacy-preserving keys for authenticated subjects and anonymous IPs;
- one atomic Valkey-backed limiter shared by all web processes;
- bounded and explicit behavior when Valkey is unavailable;
- rate-limit response headers and finite-cardinality observability;
- deterministic unit, integration, concurrency and ASGI tests;
- lifecycle-managed backend resources with no production changes from the branch.

### Out of scope

- browser/BFF session migration (H-06);
- changing the OIDC proxy allowlist or token flow;
- Authentik provider/group/user changes;
- worker queue separation;
- PostgreSQL or CNP changes;
- changing business endpoint permissions;
- deploying or restarting services.

## Mandatory infrastructure preflight

Before choosing trusted CIDRs or header mode, inventory read-only:

- the externally reachable edge and whether Cloudflare proxying is enabled;
- every reverse proxy between the client and Uvicorn;
- the direct peer IP/CIDR seen by Uvicorn;
- whether the final reverse proxy removes client-supplied `CF-Connecting-IP`, `X-Forwarded-For`, `Forwarded` and `X-Real-IP` before adding trusted values;
- whether port `9898` is reachable from any untrusted network;
- the exact systemd `ExecStart` proxy-header options, if any;
- whether more than one backend process or instance can serve requests;
- the Valkey endpoint used by the Retail backend and whether a dedicated logical namespace/database is available.

Do not configure trusted networks from assumptions. The implementation must remain safe when the trusted-proxy list is empty: forwarded headers are ignored and `request.client.host` is used.

## Settings contract

Create a pure typed module, for example `backend/rate_limit_settings.py`, with a frozen settings object and safe parser.

Recommended fields:

- `trusted_proxy_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]`
- `client_ip_header_mode: Literal["none", "cloudflare", "x-forwarded-for"]`
- `valkey_url: str`
- `key_hmac_secret: str`
- `failure_mode: Literal["closed"]`
- bounded policy definitions for each existing policy.

Environment variables:

- `TRUSTED_PROXY_CIDRS` — comma-separated IPv4/IPv6 CIDRs; empty means no forwarded header is trusted;
- `RATE_LIMIT_CLIENT_IP_HEADER` — `none`, `cloudflare` or `x-forwarded-for`;
- `RATE_LIMIT_VALKEY_URL` — may deliberately reuse `VALKEY_URL`, but the resolved value must be explicit and validated in production;
- `RATE_LIMIT_KEY_HMAC_SECRET` — required in production, 43..256 printable non-whitespace characters;
- `RATE_LIMIT_FAILURE_MODE=closed` in production;
- existing policy limit/window variables, parsed lazily and validated with explicit ranges.

Validation requirements:

- production rejects missing, empty, partial or invalid distributed-limiter configuration;
- development/test may use an injected in-memory test store, never an unbounded global fallback;
- CIDRs must parse through `ipaddress.ip_network(..., strict=False)` and duplicate networks are deduplicated;
- `cloudflare` or `x-forwarded-for` mode requires at least one trusted direct-peer network;
- URL errors name only the environment variable, never the configured value;
- limits and windows are positive bounded integers and invalid values are errors, not silent defaults;
- no import-time environment cache that prevents deterministic tests or controlled reloads.

Suggested policy bounds:

- limit: 1..100000;
- window: 1..86400 seconds.

## Trusted client-IP resolution

Use `request.client.host` as the only initial trust anchor.

### Direct peer

- parse the peer with `ipaddress.ip_address`;
- an invalid or missing peer resolves to a fixed unknown identity and emits a finite metric;
- never trust a forwarded header when the peer is not in `TRUSTED_PROXY_CIDRS`.

### Cloudflare mode

- only read `CF-Connecting-IP` when the direct peer is trusted;
- require exactly one valid IP value;
- reject commas, whitespace-separated lists or malformed values;
- otherwise fall back to the direct peer.

### X-Forwarded-For mode

- only read the header when the direct peer is trusted;
- parse every comma-separated element as one IP;
- append the direct peer conceptually to the chain;
- walk the header from right to left, skipping configured trusted proxy hops;
- the first non-trusted valid address is the client;
- malformed elements invalidate the entire header and fall back to the direct peer;
- cap the number of hops, for example at 16, to avoid parser abuse.

All returned addresses must use `ipaddress` canonical string form. Do not accept `Forwarded` or `X-Real-IP` implicitly.

## Rate-limit identity keys

### Authenticated requests

Primary identity is the verified OIDC `claims.sub` only. Do not combine it with IP for the main authenticated policy.

### Anonymous requests

Identity is the verified canonical client IP.

### Privacy

Raw subject, email and client IP must not appear in Valkey keys, metrics or ordinary logs. Derive a stable key with HMAC-SHA256 using `RATE_LIMIT_KEY_HMAC_SECRET` and a namespace:

- `user:<sub>`
- `ip:<canonical_ip>`

Store only the HMAC digest plus finite policy name under a versioned prefix such as:

`unihub:retail:ratelimit:v1:<policy>:<digest>`

Never log the digest as an identity surrogate.

## Distributed atomic limiter

Introduce a store protocol and a Valkey implementation. The algorithm must be atomic across processes and hosts.

A Lua token-bucket or GCRA implementation is preferred. Required properties:

- server-side atomic decision;
- uses Valkey server time or a deterministic injected clock in tests;
- supports configured `limit` and `window_seconds`;
- bounded key TTL with automatic deletion;
- returns `allowed`, `remaining`, `retry_after_seconds` and `reset_after_seconds`;
- no sorted-set/list growth proportional to all requests;
- script content/version is stable and testable;
- script loading handles `NOSCRIPT` safely or uses `EVAL` with bounded script size;
- keys are namespaced and contain no raw identity.

If the implementation imports `redis.asyncio` directly, declare `redis` explicitly in runtime requirements rather than relying on a transitive ARQ dependency.

## Failure behavior

Production failure mode is closed for endpoints protected by H-07:

- Valkey timeout/unavailable/script failure -> generic HTTP 503;
- do not silently bypass the control;
- do not misreport backend failure as HTTP 429;
- reads without a rate-limit dependency remain available;
- no unbounded process-local dictionary fallback.

Development/test may use an explicitly injected bounded fake store. It must not be selected automatically in production.

Timeouts must be short and bounded. Cancellation must propagate without being converted into an allowed request.

## HTTP response contract

On allowed requests, attach where practical:

- `RateLimit-Limit`;
- `RateLimit-Remaining`;
- `RateLimit-Reset`.

On rejection:

- status 429;
- generic Romanian/English detail consistent with the API;
- `Retry-After` rounded up to at least one second;
- the same RateLimit headers.

On limiter backend failure:

- status 503;
- generic detail;
- no Retry-After unless a bounded operational retry interval is deliberately defined.

Do not expose key, subject, IP, Valkey URL or exception text.

## Policy behavior

Preserve the existing named policies and current business limits unless an explicit change is approved:

- `auth_proxy`;
- `sales_import_upload`;
- `report_export`;
- `business_write`;
- `grile_job`;
- `target_mutation`.

Requirements:

- policy names are a finite enum/registry;
- authenticated policies key by `sub`;
- anonymous auth proxy keys by trusted client IP;
- separate policy namespaces prevent one route class consuming another route class's quota;
- dependency wiring remains visible in OpenAPI/router tests;
- no endpoint permission is weakened.

## Lifecycle

Create one reusable Valkey limiter client/store during FastAPI lifespan and close it during shutdown.

- init does not mutate production data beyond ephemeral rate-limit keys;
- init/close are idempotent and atomic;
- cleanup occurs even if DB/ARQ/OIDC cleanup fails;
- no client is created per request;
- tests can inject a store and clock;
- worker services do not initialize the web limiter unless they use it.

## Observability

Finite-cardinality metrics:

- `rate_limit_decisions_total{policy,outcome="allowed|rejected|error"}`;
- `rate_limit_backend_duration_seconds{operation="eval"}`;
- `rate_limit_client_ip_resolution_total{mode="peer|cloudflare|xff",outcome="accepted|fallback|invalid"}`;
- optional gauge for backend availability with fixed labels only.

Forbidden metric labels:

- subject;
- email;
- IP;
- digest;
- route path;
- exception text;
- Valkey URL.

Logs use fixed events/reasons and request-ID context only. No raw forwarded header, peer IP, subject, digest or secret is logged.

## Required tests

### Settings

- production required values missing/empty;
- malformed CIDRs, duplicate CIDRs and IPv4/IPv6;
- header mode without trusted proxies;
- invalid Valkey URL;
- secret length/whitespace/control;
- every policy numeric boundary;
- safe errors contain no configured values;
- no import-time freezing.

### Client-IP trust

- untrusted direct peer with spoofed CF/XFF -> peer used;
- trusted peer with valid Cloudflare header -> header IP used;
- invalid/multiple Cloudflare values -> fallback;
- XFF right-to-left trusted-hop removal;
- malformed XFF invalidates the complete header;
- hop-count bound;
- IPv4 and IPv6 canonicalization;
- missing/invalid `request.client`.

### Identity

- authenticated key depends on `sub`, not email or IP;
- same subject across two IPs shares quota;
- different subjects are independent;
- anonymous IPs are independent;
- raw subject/IP never appears in generated key/log/metric;
- deterministic HMAC and versioned namespace.

### Atomic/distributed behavior

- two independent limiter instances sharing one store enforce one quota;
- 100 concurrent calls with limit 10 allow exactly 10;
- rejection retry/reset values are deterministic;
- window refill/token refill behavior;
- TTL is set and keys expire;
- no per-request history growth;
- script reload/NOSCRIPT behavior;
- cancellation does not count as allowed accidentally.

### Failure behavior

- Valkey timeout, connection error, script error -> 503;
- no silent allow;
- no 429 on backend error;
- client closes on lifecycle failures;
- no leaked tasks/connections.

### ASGI/integration

- anonymous auth proxy receives IP-based distributed limit;
- authenticated protected mutation receives subject-based limit;
- exact 429/503 and headers;
- two app instances share enforcement;
- existing route permissions remain intact;
- OpenAPI remains stable;
- no identity/secret in response or caplog.

Run the exact CI coverage gate and full frontend suite even if frontend source is unchanged. Add critical coverage floors for the new settings/client-IP/store/limiter modules.

## Deployment and rollback

No production change occurs from the implementation branch.

Before later merge/deploy:

1. complete the read-only proxy-chain inventory;
2. approve the exact trusted direct-peer CIDRs and header mode;
3. generate/provision the HMAC secret securely;
4. provision/validate the Valkey URL and ACL without exposing values;
5. validate settings from the merged code without restart;
6. deploy code with coherent rollback artifacts;
7. restart backend only;
8. verify spoofed headers are ignored from an untrusted test path;
9. verify two backend processes share the same quota;
10. monitor reject/error/latency metrics.

Rollback code while retaining explicit trusted-proxy and Valkey settings. Do not re-enable unconditional forwarded-header trust or an unbounded local dictionary.

## Acceptance

H-07 is technically complete only when:

- forwarded headers are ignored for untrusted peers;
- production settings are typed and fail closed;
- authenticated quota keys use verified subject only;
- raw identities do not enter Valkey keys/logs/metrics;
- enforcement is atomic and shared across independent limiter instances;
- backend failure is explicit and fail closed;
- memory and key retention are bounded;
- 429/503 response contracts and finite metrics are tested;
- focused/full tests and CI are green;
- no production, Authentik, proxy, environment, PostgreSQL or CNP modification has occurred;
- PR #32 remains draft until H-07 engineering review and the remaining Wave 2 release plan are complete.

## Implementation evidence

The branch implementation now provides four separately tested boundaries:

- `rate_limit_settings.py` parses trusted proxy CIDRs, header mode, the resolved
  Valkey URL, the HMAC secret, closed failure mode and every existing policy
  lazily and fail-closed;
- `client_ip.py` anchors trust in the direct socket peer, canonicalizes IPv4
  and IPv6, rejects malformed Cloudflare/XFF values and bounds XFF hops;
- `rate_limit_store.py` executes one atomic Valkey script using Valkey `TIME`,
  one bounded two-field hash and an automatic key TTL;
- `rate_limits.py` derives versioned HMAC-SHA256 keys, uses only verified `sub`
  for authenticated quotas, emits finite metrics and returns consistent
  RateLimit headers, 429 rejection and generic 503 backend failure.

The isolated test runner creates a dedicated ephemeral Valkey container. Two
independent clients sharing that store receive exactly 10 allowed decisions
from 100 concurrent calls at a limit of 10; the test also proves TTL expiry and
constant per-key storage. No production Valkey key is used.

Local gates on 2026-07-12 are green: mypy, `pip check`, 1,027 backend tests
with 7 skips, frontend 177 tests, typecheck and production build. Critical
coverage is 100% for `client_ip.py`, `rate_limit_settings.py`,
`rate_limit_store.py` and `rate_limits.py`. GitHub Actions run `29193554547`
is green on the PR merge ref, so the application implementation is accepted
technically. Production activation remains pending the separately approved
proxy, firewall and environment rollout.
