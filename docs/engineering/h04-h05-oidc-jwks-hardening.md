# H-04/H-05 — Typed OIDC settings and bounded JWKS rotation

## Purpose

H-04/H-05 removes production Authentik defaults from backend code, validates the OIDC verifier configuration fail-closed, and replaces the current unsynchronised/unbounded JWKS cache with a lifecycle-managed verifier that supports safe key rotation.

This work follows H-01A on `stabilization/audit-remediation-wave2-privacy` and does not modify the H-01 CNP-retention decision.

## Confirmed current risks

- `backend/auth.py` embeds production issuer, JWKS URL and audience fallback values at import time.
- numeric JWKS settings are parsed at import time without bounded validation;
- every refresh creates a new `httpx.AsyncClient`;
- concurrent cache misses can trigger duplicate refreshes;
- an unknown `kid` is rejected without one forced refresh;
- a failed refresh may reuse cached JWKS without a maximum stale age;
- token-header `kid` and configured URLs can enter ordinary logs;
- required claims and the `groups` claim shape are not validated strictly;
- `backend/config.py` does not currently validate the OIDC verifier settings.

## Scope

### In scope

- a typed, pure backend OIDC settings model;
- strict production startup validation;
- lazy fail-closed behavior in development/test when OIDC is absent;
- reusable HTTP client lifecycle;
- bounded, single-flight JWKS cache;
- one forced refresh on unknown `kid`;
- bounded stale-key behavior only for a previously known key;
- strict token header, claims and group validation;
- finite-cardinality metrics and redacted logs;
- deterministic tests with no live Authentik traffic.

### Out of scope

- browser token storage and BFF migration (H-06);
- broad OIDC proxy redesign/allowlisting (H-06);
- trusted-proxy and distributed rate limiting (H-07);
- Authentik provider, mapping, group or user changes;
- production environment changes or service restarts;
- CNP/database changes.

## Settings contract

Create a pure module such as `backend/oidc_settings.py` with a frozen typed object and safe parser.

Required verifier variables in production:

- `OIDC_ISSUER`
- `OIDC_JWKS_URL`
- `OIDC_AUDIENCE`

Bounded runtime variables:

- `JWKS_CACHE_TTL` — default 3600 seconds, accepted range 60..86400;
- `JWKS_MAX_STALE_SECONDS` — default 86400, accepted range `JWKS_CACHE_TTL`..604800;
- `JWKS_FETCH_TIMEOUT_SECONDS` — default 5.0, accepted range 0.5..30.0;
- `OIDC_CLOCK_SKEW_SECONDS` — default 30, accepted range 0..120.

Validation requirements:

- no embedded real issuer/JWKS/audience fallback in Python;
- issuer and JWKS URL are absolute URLs;
- production requires HTTPS;
- development may use HTTP only for loopback hosts;
- issuer and JWKS URL must use the same origin unless an explicit future design approves otherwise;
- audience is a non-empty printable string without whitespace/control characters and is length-bounded;
- invalid numeric values are startup/config errors, not silently clamped;
- errors name only the environment variable and generic reason, never its value;
- no import-time environment cache that prevents deterministic tests.

Production must fail startup for missing, empty or invalid verifier settings. Development/test may boot when all three verifier settings are absent/empty, but a bearer-authenticated route must then fail with a generic 503. A partially configured or non-empty invalid set is an error in every environment.

`.env.example` must contain non-secret placeholders, not real tenant/client values.

## JWKS runtime

Introduce a lifecycle-managed verifier/cache, for example `OIDCVerifier` and `JWKSCache`.

Required lifecycle:

- initialise one reusable `httpx.AsyncClient` during app lifespan without forcing network availability;
- close it during shutdown even when another cleanup step fails;
- init/close operations are idempotent;
- tests can inject a client, clock and settings;
- no request creates its own HTTP client.

### Cache record

Store only:

- validated JWKS payload;
- successful-fetch monotonic timestamp;
- no token, claims or request object.

### Normal lookup

1. if cache age is below TTL, use it;
2. otherwise acquire one `asyncio.Lock`;
3. recheck after acquiring the lock;
4. perform one bounded fetch;
5. validate and atomically replace the cache;
6. on failure, use stale cache only when its age is at most `JWKS_MAX_STALE_SECONDS` and it contains the requested key;
7. otherwise return generic 503.

### Unknown `kid`

1. parse a bounded non-empty string `kid` from an RS256 header;
2. look up in the current cache;
3. on miss, acquire the refresh lock and force exactly one refresh, with recheck under the lock;
4. if refresh succeeds but the key is still absent, return generic 401;
5. if refresh fails and the old cache does not contain the requested key, return generic 503;
6. never log or return the `kid` value.

Concurrent misses for the same or different unknown keys must cause at most one network refresh for that generation.

### JWKS validation

A fetched payload is accepted only when:

- top-level object contains a non-empty `keys` list;
- each accepted entry is an object with bounded string `kid`;
- key type/algorithm/use are compatible with RS256 signing;
- duplicate `kid` entries are rejected;
- malformed/oversized payloads fail closed;
- response body is bounded before JSON parsing.

## Token and claim validation

Before signature verification:

- malformed header -> generic 401;
- `alg` must be exactly `RS256`;
- `kid` must be a bounded printable string without controls;
- do not log token/header data.

PyJWT verification must:

- allow only RS256;
- verify signature, expiration, issuer and audience;
- require `exp`, `iat`, `iss`, `aud` and `sub`;
- use only the bounded configured clock skew.

Post-verification:

- `sub` must be a non-empty printable string;
- `groups` must be a list of strings, never a singular string/object;
- group count and individual lengths are bounded;
- malformed claims return generic 401;
- `email` and `preferred_username` may remain optional display fields but must be strings if present;
- the configured audience may be stored in `AuthClaims.aud` after successful verification so downstream code does not depend on token payload shape;
- no full raw token is retained or logged.

The local `X-Hub-Internal` path must retain its current behavior and constant-time secret comparison, but environment lookup/config must not be frozen accidentally at import time. No new privileged groups are granted by this finding.

## Error semantics

- missing Authorization -> 401 with `WWW-Authenticate: Bearer`;
- malformed/invalid/expired token -> generic 401;
- validly structured token with unknown key after a successful refresh -> generic 401;
- verifier not configured in development -> generic 503;
- JWKS unavailable with no usable bounded-stale known key -> generic 503;
- no URL, token, `kid`, claim payload or secret in client errors.

## Observability

Finite-cardinality metrics:

- `jwks_refresh_total{outcome="success|failure"}`;
- `jwks_cache_use_total{state="fresh|stale"}`;
- `jwks_unknown_kid_total`;
- `jwks_cache_age_seconds` gauge;
- optional `oidc_validation_failure_total{reason=<small enum>}`.

No metric label may contain URL, `kid`, subject, email, group, exception message or route path.

Logs must record only fixed events/reasons and request ID context. They must not contain token, `kid`, complete issuer/JWKS URL, claims or secret values.

## Required tests

### Settings

- production missing/empty each required setting;
- partial configuration;
- invalid URL/scheme/origin/audience;
- development all absent/empty -> base startup allowed, auth request 503;
- valid production settings;
- all numeric range and relation checks;
- safe errors contain no configured value.

### Cache/rotation

- fresh cache hit performs no network request;
- TTL expiry refreshes once;
- unknown `kid` refreshes once then succeeds;
- unknown `kid` after successful refresh -> 401;
- concurrent misses -> one fetch;
- fetch timeout/HTTP error/malformed JSON/malformed keys;
- known key accepted from stale cache inside max-stale after refresh failure;
- stale cache beyond max-stale -> 503;
- unknown key plus refresh failure -> 503, never stale acceptance;
- duplicate `kid` rejected;
- client init/close idempotency and no leaked tasks/resources.

### JWT/claims

Use synthetic locally generated RSA keys and tokens only:

- valid token;
- rotation from key A to key B;
- wrong signature;
- expired token;
- invalid issuer/audience;
- missing/empty `sub`;
- missing required claims;
- invalid `alg`;
- missing/invalid `kid`;
- valid groups array;
- string/object/mixed groups rejected;
- optional email/username handling;
- logs/caplog contain no token, `kid` or claim value.

### Integration

- real ASGI protected endpoint with valid token -> 200;
- missing token -> 401;
- verifier unavailable -> 503;
- unknown rotated key is recovered without a second client request;
- current `X-Hub-Internal` loopback behavior remains tested;
- OpenAPI/auth dependencies remain unchanged.

Run the exact CI coverage gate and full frontend suite even if frontend source is unchanged.

## Deployment and rollback

No production change occurs from the implementation branch.

Before a later merge/deploy:

1. read-only inventory of existing environment key presence (never values);
2. add/verify explicit issuer, JWKS URL, audience and bounded settings;
3. validate config without restart;
4. build coherent rollback/release artifacts;
5. restart backend only when the reviewed merge commit is ready;
6. verify current and rotated synthetic/live key behavior without exposing tokens;
7. monitor refresh/failure/stale metrics.

Rollback code only; keep explicit OIDC environment settings. Never restore embedded production defaults.

## Acceptance

H-04/H-05 is technically complete only when:

- no real verifier endpoint/audience fallback remains in backend source;
- production startup is fail-closed;
- unknown-key rotation is single-flight and succeeds after one refresh;
- stale acceptance is key-specific and time-bounded;
- all claim shapes are strict;
- metrics/logs are bounded and redacted;
- focused/full tests and CI pass;
- no Authentik/environment/production modification has occurred;
- PR #32 remains draft until later Wave 2 findings and a deployment runbook are complete.

## Implementation evidence

`OIDCVerifierSettings` is now a frozen, load-on-demand model. Production
requires issuer, JWKS URL and audience; development may omit all three but
cannot accept a partial configuration. The bounded defaults are TTL 3600s,
maximum stale 86400s, fetch timeout 5s and clock skew 30s.

The verifier owns one lifecycle-managed HTTP client and an immutable cache of
validated `kid` to `PyJWK` entries. Refreshes are serialized by an event-loop
lock; known keys can use stale data only after a failed refresh and before the
configured maximum age. Header and claim failures use generic responses and
the refresh/cache metrics have finite labels only.

`httpx` moved to runtime requirements and CI now installs a separate runtime
venv from that file alone before importing `auth`, `main` and `worker`. No
Authentik, environment, production service, database, browser token storage,
OIDC proxy or rate limiter was modified.
