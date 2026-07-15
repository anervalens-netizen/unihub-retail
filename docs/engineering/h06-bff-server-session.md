# H-06 — BFF and server-side OIDC sessions

Last updated: 2026-07-13

## Outcome

The Retail SPA no longer receives, parses, persists or sends OIDC access,
refresh or ID tokens. Authentication is terminated by the FastAPI backend:

- `/auth/session/login` creates a one-time state, nonce and PKCE verifier;
- `/auth/callback` consumes that state, performs the confidential token
  exchange and validates the signed access and ID tokens;
- `/auth/session` returns only the verified public profile and an in-memory
  CSRF token;
- `/auth/session/logout` destroys the server session and expires the cookie;
- API requests use the `__Host-unihub_session` HttpOnly, Secure, SameSite=Lax
  cookie;
- unsafe authenticated requests also require `X-CSRF-Token`;
- refresh tokens and session claims are encrypted with Fernet before storage in
  Valkey; the browser-visible session ID is random and opaque;
- near-expiry requests use a token-owned distributed refresh lock, so
  concurrent requests produce one refresh exchange; waiters follow the full
  bounded refresh window instead of treating a normal slow provider response
  as logout.

The PWA navigation fallback explicitly excludes backend-owned routes,
including `/auth/*`. Auth navigations must always reach FastAPI so
`/auth/session/login` can return the Authentik redirect. Serving the cached SPA
for that URL would remount the auth context and create a repeated
`401 -> login navigation` loop. The development proxy mirrors the same route
ownership.

The former generic `/auth/proxy/{path}` endpoint and its browser-side client
secret injection have been removed. A Bearer token remains accepted by the
backend dependency only as a temporary non-browser compatibility path for
controlled integrations and smoke tooling.

## Security properties

- OAuth authorization code flow uses PKCE S256, state and nonce, all bounded
  and single-use with a 10-minute TTL.
- The production cookie uses the `__Host-` prefix, no Domain attribute, Path
  `/`, Secure, HttpOnly and SameSite=Lax.
- Session records have a bounded configurable lifetime (15 minutes to 90 days,
  default 30 days) and are deleted on logout or failed refresh.
- Token endpoint URLs are derived only from the validated OIDC issuer origin;
  redirects are disabled and responses are size-bounded.
- JWT signature, issuer, audience, algorithm, registered claims, groups and
  nonce use the existing hardened verifier. Access tokens are validated
  against `OIDC_AUDIENCE`; ID tokens are validated against the confidential
  client's `OIDC_CLIENT_ID`, as required when those identifiers differ.
- Authentication and CSRF failures return generic bounded errors without
  tokens, cookies, secrets or provider responses.
- Configuration fails closed in production if the encryption key, client
  credentials, issuer, public origin or Valkey URL is missing or invalid.
- Refresh lock release uses compare-and-delete, so an expired owner cannot
  delete a newer request's lock. A waiter never deletes the session while the
  lock owner is still inside the bounded token/verification window and re-reads
  the session after observing lock release to cover the store/release boundary.
  The 60-second lock lease covers the 15-second token exchange, the configured
  maximum 30-second JWKS fetch and a 15-second processing margin; waiters use a
  65-second window and return a non-destructive 503 if contention outlives it.

## Configuration

The backend environment requires:

```text
SESSION_ENCRYPTION_KEY=<Fernet key>
SESSION_PUBLIC_ORIGIN=https://retail.unihub.ro
SESSION_VALKEY_URL=<private Valkey URL>
SESSION_TTL_SECONDS=2592000
OIDC_CLIENT_ID=<Authentik provider client ID>
OIDC_CLIENT_SECRET=<existing confidential client secret>
```

`SESSION_ENCRYPTION_KEY` is independent from the OIDC client secret and from
the salary HMAC key. Rotation requires draining existing sessions (users log in
again); never reuse another application secret. `OIDC_CLIENT_ID` is mandatory
when the BFF session is enabled and never falls back to `OIDC_AUDIENCE`.

In `.env.example` this entire optional browser-session group is empty so the
documented development startup remains valid. To enable it locally, configure
the complete group; partial configuration is rejected.

## Verification and rollout

Automated tests cover encrypted PKCE state, exact provider endpoints, callback
state consumption, Secure/HttpOnly cookie attributes, CSRF enforcement,
encrypted token storage, refresh-token rotation, 20-request refresh
single-flight and a provider response longer than the former two-second waiter
window. Static frontend tests reject token libraries, token fields, localStorage
auth and Bearer injection.

Production rollout order:

1. generate and install the session encryption key;
2. confirm the existing Authentik redirect URI remains
   `https://retail.unihub.ro/auth/callback`;
3. deploy backend and frontend together, then restart backend;
4. verify unauthenticated login redirect, callback cookie, session profile,
   authenticated read, CSRF rejection/acceptance and logout;
5. inspect logs and metrics for generic failures only.

Rollback restores the previous backend and frontend build together and leaves
the new key configured. Existing BFF sessions become unused and expire in
Valkey. Do not restore only the frontend because the old SPA expects the
removed proxy contract.

## Production acceptance

Activated on 2026-07-13 from merge commit
`d323ae16fa398dc6b98d883ad59a5e1e1aa3f8fb` after GitHub Actions run
`29211586704` passed both backend and frontend checks. The production
environment contains a dedicated Fernet key, the explicit Retail public
origin, the private Valkey endpoint, the 30-day bounded session TTL and the
existing confidential OIDC client identifier; the environment file remains
mode `0600`.

Post-deploy checks confirmed:

- local and public `/health` return 200 after session-runtime readiness;
- unauthenticated `/auth/session` returns 401 without setting a cookie;
- `/auth/session/login` returns 302 to the validated Authentik authorization
  endpoint with state, nonce, PKCE S256, client ID and the exact
  `https://retail.unihub.ro/auth/callback` redirect URI;
- the authorization redirect contains no client secret;
- the removed generic token proxy no longer accepts POST requests;
- startup and request logs contain no H-06 errors, exceptions or credentials.

The signed callback, cookie, authenticated profile, CSRF and logout paths are
covered by the real ASGI/JWT test suite. A user-interactive browser login is
the remaining observational smoke check; it does not require another deploy.
