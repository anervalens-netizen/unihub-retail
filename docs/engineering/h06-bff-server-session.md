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
- near-expiry requests use a distributed refresh lock, so concurrent requests
  produce one refresh exchange.

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
  nonce use the existing hardened verifier.
- Authentication and CSRF failures return generic bounded errors without
  tokens, cookies, secrets or provider responses.
- Configuration fails closed in production if the encryption key, client
  credentials, issuer, public origin or Valkey URL is missing or invalid.

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
again); never reuse another application secret.

## Verification and rollout

Automated tests cover encrypted PKCE state, exact provider endpoints, callback
state consumption, Secure/HttpOnly cookie attributes, CSRF enforcement,
encrypted token storage, refresh-token rotation and 20-request refresh
single-flight. Static frontend tests reject token libraries, token fields,
localStorage auth and Bearer injection.

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
