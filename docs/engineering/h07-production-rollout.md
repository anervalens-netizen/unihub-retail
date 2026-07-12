# H-07 — controlled production rollout

This runbook is a review artifact. It does not authorize changes by itself.
Never print environment values, the HMAC secret, Valkey credentials, raw
client addresses or forwarded header contents.

## Execution record — 2026-07-12

Wave 2 was merged as `eb8618a22cc5a53708f0a5a866b81cdde1b20c31`
and activated through this runbook. Production now has:

- Caddy fixed at `172.23.0.2` on `unihub-net`;
- Retail ingress restricted to the local Cloudflare Tunnel origin;
- forwarded headers stripped and `CF-Connecting-IP` explicitly propagated;
- port 9898 allowed only from Caddy and the Prometheus scraper;
- Uvicorn proxy-header rewriting disabled;
- OIDC/JWKS, salary identity and rate-limit secrets provisioned without values
  being stored in Git;
- backend restarted successfully while the worker PID remained unchanged.

Local/public health, Caddy validation, direct non-tunnel rejection, Valkey
decisions and finite Prometheus labels were verified. A live verification also
identified and fixed the loss of successful `RateLimit-*` headers when an
endpoint returned an explicit response object; the regression is covered by an
ASGI test.

## Required infrastructure state

Before activating distributed enforcement:

1. keep Uvicorn's `request.client` as the direct socket peer by explicitly
   disabling Uvicorn proxy-header rewriting;
2. assign Caddy a stable address on `unihub-net` and approve only that exact
   `/32` as `TRUSTED_PROXY_CIDRS`;
3. restrict host port 9898 from the current broad Docker private range to the
   exact Caddy peer, plus separately documented health/metrics consumers;
4. restrict the Retail Caddy ingress so only the local Cloudflare Tunnel path
   can supply the client identity header;
5. remove incoming `X-Forwarded-For`, `X-Real-IP` and `Forwarded` for Retail;
6. explicitly overwrite the single selected outbound client identity header
   after the tunnel source has been verified.

Do not enable `cloudflare` or `x-forwarded-for` mode while a direct client can
reach the Retail Caddy virtual host and supply the chosen header.

## Environment provisioning

Provision without displaying values:

```text
TRUSTED_PROXY_CIDRS=<stable exact Caddy peer /32>
RATE_LIMIT_CLIENT_IP_HEADER=cloudflare
RATE_LIMIT_VALKEY_URL=<reuse validated VALKEY_URL or dedicated URL>
RATE_LIMIT_KEY_HMAC_SECRET=<new 43..256 character secret>
RATE_LIMIT_FAILURE_MODE=closed
```

The six policy limits and windows default to their pre-H-07 business values.
Set them explicitly during provisioning so production intent is auditable.

## Pre-deploy gates

1. validate presence and file permissions without printing values;
2. validate Caddy configuration without reload;
3. verify the exact firewall diff without applying it;
4. validate application settings from the reviewed merge commit without
   starting a second production listener;
5. prepare rollback artifacts for systemd, Caddy, firewall and application
   commit;
6. obtain explicit approval for the combined infrastructure and backend
   activation.

## Activation and verification

Apply the approved proxy/firewall/environment changes as one controlled
maintenance operation, deploy the reviewed merge commit and restart only the
backend. Do not restart the worker.

Verify metadata-only:

- health and metrics are available;
- a direct untrusted request cannot reach port 9898;
- spoofed forwarded headers from an untrusted path do not change identity;
- anonymous auth proxy requests receive RateLimit headers;
- authenticated mutations share quota across two backend processes in a
  temporary controlled check;
- Valkey failures produce 503, quota exhaustion produces 429;
- metrics contain finite labels only and logs contain no identities or secrets.

## Rollback

Restore the previous application commit, systemd arguments, Caddy config and
firewall snapshot as one coherent rollback. Retain explicit secrets securely,
but do not restore unconditional forwarded-header trust or the old unbounded
process-local limiter. Confirm backend health and frontend/backend contract
coherence after rollback.
