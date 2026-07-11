# H-08 — Privileged access must fail closed

## Revalidated defect

Two high-impact operations currently authorize by email address and include a real
production identity as a code fallback:

- Target Calculator calculation, edits and final publication use
  `TARGET_CALCULATOR_FINALIZER_EMAILS`, defaulting to a real address;
- Grile monthly finalize/archive/reset, job status and downloads use
  `GRILE_FINALIZER_EMAILS`, also defaulting to a real address.

If either environment variable is absent, the application silently grants the
privilege to that hard-coded identity.  Email is also a mutable personal
attribute rather than a stable authorization role.

## Security decision

Authorization moves to dedicated OIDC group claims:

```text
TARGET_CALCULATOR_FINALIZER_GROUPS=unihub-target-finalizer
GRILE_FINALIZER_GROUPS=unihub-grile-admin
```

These names are deployment recommendations, not hidden code fallbacks.  The
application reads the configured comma-separated group lists and compares them
case-insensitively with the verified `groups` claim.

Rules:

1. no email address participates in authorization;
2. no real identity is stored in source, `.env.example`, tests or docs;
3. missing/empty group configuration grants nobody;
4. production startup refuses to continue when either group list is missing or
   invalid;
5. development/test may start without the variables, but all privileged checks
   return false;
6. `unihub-admin`, `authentik Admins`, `unihub-manager` and the internal
   `hub-service` identity are not implicit bypasses;
7. only explicitly configured groups authorize the corresponding capability;
8. group names are stripped, case-folded and deduplicated;
9. values containing `@`, control characters or empty entries are rejected by
   configuration validation;
10. deprecated email variables are rejected in production so operators cannot
    assume they are still effective.

## Central policy boundary

Introduce a lightweight pure module, for example:

```text
backend/privileged_access.py
```

It should own:

- environment variable names;
- safe parsing and normalization;
- validation errors;
- group intersection checks.

`config.py` and both routers consume this module.  The module must not import
FastAPI or depend on request state, avoiding configuration/import cycles.

Router functions such as `can_finalize_targets()` and `can_grile_admin()` may
remain as compatibility wrappers, but they must delegate to the central group
policy and must not read email allowlists.

## Startup validation

For `UNIHUB_ENV=production`, `validate_required_env_vars()` must report clear,
non-secret errors when:

- `TARGET_CALCULATOR_FINALIZER_GROUPS` is missing/empty;
- `GRILE_FINALIZER_GROUPS` is missing/empty;
- a group item resembles an email address;
- a group contains control characters or exceeds a reasonable length;
- deprecated `TARGET_CALCULATOR_FINALIZER_EMAILS` or
  `GRILE_FINALIZER_EMAILS` is still set.

The error must identify only the environment variable and validation reason; it
must not echo all configured identities or token claims.

## Authorization and audit behavior

The user-facing permission endpoints remain compatible:

- Target Calculator context returns `can_finalize`;
- Grile monthly permissions returns `can_run`.

Sensitive dependencies return HTTP 403 when the claim lacks the configured
role.  Authorization decisions for actual privileged routes should emit a
structured event containing only:

- resource/capability;
- action or route template;
- verified OIDC subject;
- result (`allowed`/`denied`);
- request ID when available.

Do not log email, raw groups, token data, request payloads or financial values.
Permission-display checks should not create noisy audit events.

## Required tests

1. the historical real email receives no privilege when it has no configured
   group;
2. the recommended Target group grants only Target capability;
3. the recommended Grile group grants only Grile capability;
4. matching is case-insensitive and trims whitespace;
5. missing and empty environment variables fail closed;
6. multiple configured groups work and duplicate entries are deduplicated;
7. broad admin/manager groups do not bypass the dedicated policy;
8. the internal hub-service claim does not bypass it;
9. production startup rejects missing configuration;
10. production startup rejects email-like group values and deprecated email
    variables;
11. `.env.example` contains placeholders/group names only and no personal
    address;
12. Target calculate/update/finalize dependencies enforce the policy;
13. Grile monthly run/job/download dependencies enforce the policy;
14. permission endpoints report false/true consistently;
15. denied/allowed audit events contain subject/resource/result but no email or
    raw group list.

Add a focused static regression check for the removed constants/environment
names in the two routers and `.env.example`; avoid scanning third-party or Git
history in the unit test.

## Deployment prerequisite

Before this wave is deployed:

1. create the two dedicated groups in Authentik;
2. assign the application owner/operators according to least privilege;
3. ensure the UniHub Retail OIDC provider includes the groups claim;
4. set both group environment variables in the backend service environment;
5. confirm the current owner token contains the expected group names;
6. restart only after configuration validation succeeds.

Do not deploy the group-only code before these prerequisites are complete, or
privileged UI actions will correctly become unavailable.

## Production verification

After the approved Wave 1 deployment, without executing destructive operations:

- an authorized owner sees `can_finalize=true` and `can_run=true` only for the
  groups assigned;
- a management user without the dedicated groups receives false/403;
- backend startup contains no configuration warning;
- audit logs identify subject/resource/result without email;
- the deprecated email variables are absent from the service environment.

A Grile reset or Target publication is not required merely to verify H-08.

## Rollback

No database migration is involved.  Reverting the code restores the old
behavior but also reopens the security finding and is therefore an emergency
rollback only.  The preferred recovery for access problems is to correct the
Authentik group assignment or service environment and restart the backend.
