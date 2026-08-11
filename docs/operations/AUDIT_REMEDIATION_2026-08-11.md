# Audit remediation closure — 2026-08-11

## Scope and result

This handoff reconciles every finding in
`AUDIT_COMPLET_UNIHUB_RETAIL_2026-08-10.md` and every work item in
`PLAN_REMEDIERE_UNIHUB_RETAIL_2026-08-10.md`. The independent baseline was
8.1/10. All 20 findings now have an implemented control, regression evidence,
an exact-SHA release and proportionate post-deploy verification. This document
does not assign a replacement independent score.

Runtime remediation was delivered through reviewed PRs #134–#142. The final
runtime source is `2cb2785c2340b901e07af7fcf40241e5bfd3555e`.

## Exact release evidence

- final PR gate: [run 31482819627](https://github.com/anervalens-netizen/unihub-retail/actions/runs/31482819627), including changed-function complexity, backend/frontend changed-line coverage and 6/6 mutation probes;
- exact-main CI: [run 31484028843](https://github.com/anervalens-netizen/unihub-retail/actions/runs/31484028843), successful for `2cb2785c2340b901e07af7fcf40241e5bfd3555e`;
- release archive: `retail-release-2cb2785c2340b901e07af7fcf40241e5bfd3555e.tar.gz`;
- release archive SHA-256: `aec301e2c82084de526f8e334d8d38c7ef3633544b0f22a84e356e0d54db4dcd`;
- GitHub artifact ZIP digest: `65c381602dbeda5358fa077ebe097e9d28801f221996c7c41a3fee225754e2cc`;
- `SOURCE_SHA` and every `SHA256SUMS` entry verified;
- migration manifest SHA-256: `1361aa960494bd06181ee3e551ed43f2c408351c0aacae144a1fe875cfc21364`;
- release manifest verified through Sigstore keyless against the GitHub OIDC issuer, repository, `ci.yml@refs/heads/main` identity and transparency-log entry;
- formal deployment: [run 31485385533](https://github.com/anervalens-netizen/unihub-retail/actions/runs/31485385533), successful after exact one-time approval;
- rollback handle: `/opt/Mobiup/ops/backups/retail-deploy/20260811T111002Z-397731e32c13-to-2cb2785c2340-f59b54973630e293`.

The release aggregate CycloneDX document has serial
`urn:uuid:7c273e5f-caf6-5ea0-9fa3-e421423ec656`, 215 canonical components, 216
dependency graph nodes, complete composition, explicit runtime scopes, hash
evidence for every non-root ecosystem component and zero `node_modules` PURLs.
It aggregates the official npm and Python runtime SBOMs. Missing upstream
license metadata is preserved as missing rather than invented.

The exact-main restore artifact has JSON SHA-256
`48aa0db8d8ca33268214d208088e70599e0b93be4d8dd7e23a98972436c29009`.
It reports `passed`, `restored_app_ready=true`, business-state SHA-256
`2ad8a32ac489d9381942613681ffd8583a11ce525c8db75550e10373e287455b`
and deterministic row counts/hashes for 11 critical objects. The restored
`schema_migrations` ledger has 64 rows.

## Live production probes

After the formal deploy:

- runtime Git SHA is exactly `2cb2785c2340b901e07af7fcf40241e5bfd3555e`;
- backend, operations, import, Grile and export services are active and enabled;
- local `/livez` and `/readyz`, public `/health` and public `/readyz` return 200;
- all five Retail Prometheus targets are UP;
- all four workers report `up=1`, backlog `0` and oldest queued age `0`;
- Grile success exists on `service_role="grile"`, consecutive failures are `0`, and cross-role zero gauges no longer trigger false stale/failure alerts;
- no Retail SLO/worker alert is firing and all five services emitted zero warning-or-higher records after deploy;
- the only active Retail-wide GlitchTip warning was one event at
  `2026-08-11T11:07:26.599Z`, before deploy; there were zero events after deploy;
- public `/metrics`, `/docs`, `/redoc` and `/openapi.json` remain 404;
- both content-length and chunked JSON bodies of 1 MiB + 1 byte return 413.

The versioned Caddy block has repository/live SHA-256
`b78a457b014da31d2a2960a6e1c0109473d9dfad0eb28cd48fe98cabc3b256bf`
and a valid live Caddy configuration. Edge limits are 1 MiB for regular bodies,
33 MiB for Sales/Promo envelopes and 17 MiB for ERP. The pure ASGI guard applies
the same route-aware pre-parser policy and counts streamed bodies.

## Finding-by-finding reconciliation

| Finding | Status | Closure evidence |
| --- | --- | --- |
| UR-01 Prometheus selector drift | Closed | Live job labels, semantic scrape/rule checker, promtool recording/alert scenarios, four live recording series. |
| UR-02 ASM rounded decisions | Closed | `Decimal` exact decisions, separate display rounding, every threshold ±0.001, historical read-only comparison. |
| UR-03 Grile reconciler can die | Closed | Supervised per-iteration recovery, backoff/jitter, done callback, metrics, fail-once/recover regression. |
| UR-04 pre-parser request limits | Closed | Versioned Caddy caps plus ASGI streaming guard; content-length/chunked tests and public 413 evidence. |
| UR-05 Promo `.xls` isolation | Closed | Shared spawned parser broker with signature checks, RLIMIT CPU/memory/file, timeout, output cap and malformed corpus. |
| UR-06 ERP `.xls` blocks loop | Closed | Same bounded broker invoked off-loop; ERP reconciliation helpers are pure and characterized. |
| UR-07 frontend lifecycle deadlines | Closed | Composed abort signals, 15/30/120-second budgets, bounded auth bootstrap, invalid-response failure and unconditional logout cleanup. |
| UR-08 missing worker alerts | Closed | Target absent/down, worker down, backlog, oldest age, failure ratio, duration and Grile stale/failure alerts; 24 rules and synthetic tests. |
| UR-09 session refresh herding | Closed | Process-local single-flight plus distributed fence; waiters fail within 1 second with 503/`Retry-After: 2`; owner is bounded to 10 seconds; contention/waiter/timeout metrics and concurrency tests. |
| UR-10 unversioned ASM rules | Closed | Immutable effective-dated registry, historical lookup, rule ID/hash/effective date in results; approved snapshots remain intentionally optional until this surface becomes official payroll. |
| UR-11 schema-only restore drill | Closed | Exact-main restore reconstructs and hashes ten business tables plus migration ledger and boots the restored app through `/readyz`. |
| UR-12 complexity only frozen | Closed | Remediation is now progressive and measured: >400-line Python functions 5→1, >200 18→13, >100 100→95, complexity >20 83→77. The remaining 405-line function has complexity 1. Changed-function ratchet and characterization tests prevent regression. Residual module-size debt remains normal backlog, not a claim of zero debt. |
| UR-13 architecture mismatch | Closed | The actual hybrid model is explicit in `APP_ARCHITECTURE.md` and machine-readable allowlist; routers cannot access DB, service SQL requires a reasoned category, import cycles/SQL locations fail CI. |
| UR-14 unsigned provenance | Closed | Sigstore keyless external root, GitHub OIDC identity/ref verification and transparency proof are mandatory in build and deploy. |
| UR-15 low-fidelity SBOM | Closed | Official npm/Python generators, valid canonical PURLs, graph, scopes, hashes, serial number, complete composition and fail-closed aggregate validation. |
| UR-16 configuration drift | Closed | One typed runtime loader/schema, six process templates, documented precedence, one `python-dotenv` parser semantics and CI unknown/missing/stale checks. |
| UR-17 no global/changed-lines coverage | Closed | Backend global 80%; frontend statements/branches/functions/lines 46/36/34/47%; changed executable lines 80%; strict critical floors retained; 6/6 business mutations. |
| UR-18 frontend runtime contracts | Closed | Runtime schema decoding covers session, imports/promotion, export operations, Target finalization, salary responses and Grile boundaries; malformed payloads fail closed. |
| UR-19 duplicate typecheck | Closed | Duplicate strict alias/job removed; one authoritative frontend typecheck remains. |
| UR-20 PWA language/assets | Closed | Romanian document/manifest language, false duplicate maskable icon removed and real Workbox N→N+1→N lifecycle gate. |

Totals: **20 closed, 0 partial, 0 open** against the supplied finding list.
Independent rescoring remains an auditor decision; the previously named
technical blockers for a 9+ reassessment are no longer open.

## Complexity detail

Measured against audit snapshot `f84d5c7645d1457ba3822e1d74c0e5928352f243`:

| Hotspot | Before | After |
| --- | ---: | ---: |
| `calculate_proposal` | 437 lines / complexity 96 | 16 / 1 |
| `fetch_promo_incentive_summary` | 383 / 71 | 42 / 7 |
| `ExportsRepository.fetch_report_rows` | 476 / 45 | 26 / 2 |
| `load_dashboard_all` | 444 / 34 | 20 / 1 |
| `reconcile_erp_report` | 407 / 41 | 79 / 12 |

The Grile UI has begun bounded extraction into focused components and worker
lifecycle responsibilities are separated by role. Further reductions must use
the same characterization-first approach; a big-bang rewrite is not part of
this audit closure.

## Historical ASM reconciliation

The production dataset was compared read-only under the old rounded and new
exact decisions: 511 ASM-month combinations across 36 months (2023-09 through
2026-08). Nineteen results differ: 6 island and 13 focus awards, with zero zone
or homogeneity changes. Every difference removes a false rounded award;
aggregate absolute/net impact is 2,150 RON and maximum impact is 200 RON for
one ASM-month. No salary or other production business data was written.
