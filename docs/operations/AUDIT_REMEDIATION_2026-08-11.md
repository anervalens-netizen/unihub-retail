# Audit remediation closure — 2026-08-11

## Scope and result

This handoff reconciles every finding from `AUDIT_COMPLET_UNIHUB_RETAIL_2026-08-10.md`
and every work item from `PLAN_REMEDIERE_UNIHUB_RETAIL_2026-08-10.md`. The audit
baseline was 8.1/10. Runtime remediation was delivered through PRs
[#134](https://github.com/anervalens-netizen/unihub-retail/pull/134),
[#135](https://github.com/anervalens-netizen/unihub-retail/pull/135), and
[#136](https://github.com/anervalens-netizen/unihub-retail/pull/136).

The final deployed runtime source is
`dcfaef03e197e630409541054259771c7dcbeb28`. The remaining gaps below are
explicit; this document does not claim an independently assigned score.

## Exact release evidence

- main CI: [run 31435206272](https://github.com/anervalens-netizen/unihub-retail/actions/runs/31435206272), successful for the exact runtime SHA;
- release artifact: `retail-release-dcfaef03e197e630409541054259771c7dcbeb28.tar.gz`;
- artifact SHA-256: `f7efb3ccf50d63a10b525e5dd4817fda7857cef1b2b9f6955adc1fd449b0983a`;
- `SOURCE_SHA`, every `SHA256SUMS` entry, SBOM, provenance and release manifest verified;
- formal deployment: [run 31436457892](https://github.com/anervalens-netizen/unihub-retail/actions/runs/31436457892), successful after exact one-time approval;
- migration manifest SHA-256: `1361aa960494bd06181ee3e551ed43f2c408351c0aacae144a1fe875cfc21364`;
- CI gates: runner isolation, backend, frontend, browser smoke, real full-stack E2E and release packaging all passed;
- test suites in the main candidate: 1,862 backend tests passed with 7 skipped; 340 frontend tests passed.

The real restore artifact has JSON SHA-256
`f6b874d4b2ff453020691e72b42eb6273037898f15e8b0771ea19f643b279078`.
It reports `passed`, `restored_app_ready=true`, identical business state hash
`b22f3141d6f6b20ea95edbcb65c795e7e6912cfff356f5f1a123a0550bd181d1`,
and restores 11 critical objects. The restored `schema_migrations` ledger has
64 rows; the other ten business tables each contain and hash the seeded state.

## Live production probes

After the final deploy:

- runtime Git SHA is exactly `dcfaef03e197e630409541054259771c7dcbeb28`;
- backend, operations, import, Grile and export workers are active and enabled;
- local `/livez` and `/readyz`, public `/health` and public `/readyz` pass;
- all five Retail Prometheus scrape targets are UP;
- all four HTTP/SLO recordings exist; idle Dashboard p95 is numeric `0`, not
  absent or `NaN`;
- Grile reconciliation last-success is current, consecutive failures are `0`,
  and the post-deploy duration counter is `1`;
- a public JSON body of 1 MiB + 1 byte returns HTTP 413;
- public PWA HTML and manifest use `ro`; three icons remain, none duplicated as
  a false maskable asset;
- the ASM boundary probe displays `79.0` but decides on exact `78.96`, awards
  zero target commission, and reports rule `asm-v1` with SHA-256
  `95fe70c7f9383d0176ebe8d82f7a748b33578d5219e0780226d267956b3eaa16`;
- the five runtime services emitted zero warning-or-higher log records in the
  post-deploy probe window.

Versioned pre-parser limits are 1 MiB for JSON, 33 MiB HTTP envelope for
Sales/Promo (32 MiB file plus bounded multipart overhead), and 17 MiB for ERP
(16 MiB file plus bounded multipart overhead). Both `Content-Length` and
streamed/chunked overflow paths are tested.

## Finding-by-finding reconciliation

| Finding | Status | Delivered or remaining evidence |
| --- | --- | --- |
| UR-01 Prometheus selector drift | Closed | Live web selector, static contract checker, promtool scenarios, four live recordings; the idle histogram `NaN` case is covered explicitly. |
| UR-02 ASM rounded decisions | Closed | All decisions use `Decimal` exact percentages; display rounding is separate; boundary tests cover threshold ±0.001 and 78.96/98.96/4.96. |
| UR-03 Grile reconciler can die | Closed | Supervised per-iteration recovery with exponential backoff/jitter, startup reconcile, metrics, and invariant-triggered process restart. |
| UR-04 pre-parser request limits | Partial | Pure ASGI streaming guard, per-route caps, `Content-Length` and chunked tests, and public 413 are live. A separate versioned Caddy edge cap remains outside this repository. |
| UR-05 Promo `.xls` isolation | Closed | Byte-signature broker plus spawned subprocess, memory/CPU/file/output limits, timeout and forced termination; real and malformed OLE corpus tested. |
| UR-06 ERP `.xls` blocks loop | Closed | ERP uses the same bounded broker through `asyncio.to_thread`; event loop is not used for blocking parse work. |
| UR-07 frontend lifecycle deadlines | Closed | Read/mutation/upload deadlines are 15/30/120 seconds, abort signals compose, auth bootstrap has timeout/retry, invalid session payloads fail closed, logout cleanup is unconditional. |
| UR-08 missing worker alerts | Closed | Down, backlog, queue age, failure, duration and stale-Grile rules are versioned; 24 rules and synthetic alert tests pass. |
| UR-09 session refresh herding | Open | The backend shared refresh waiter can still occupy concurrent requests for up to its existing 65-second window. Requires a bounded retry/fail-fast design. |
| UR-10 unversioned ASM rules | Closed | Immutable effective-dated registry, historical month lookup, `rule_set_id`, effective date and deterministic rule SHA-256 in results. Approved-result snapshots remain optional until ASM is promoted into official payroll. |
| UR-11 schema-only restore drill | Closed | Full restore hashes ten seeded business tables plus the migration ledger and boots the restored application through `/readyz`. |
| UR-12 complexity only frozen | Partial | `worker.py` and ERP paths were reduced while extracting the supervisor/broker. The listed top backend and frontend hotspots still require incremental extraction. |
| UR-13 architecture mismatch | Open | No broad router/service/repository rewrite was attempted; the documented hybrid exceptions still need either enforcement or explicit ADR alignment. |
| UR-14 unsigned provenance | Open | Checksums/provenance are coherent but still lack an external signing or transparency root. |
| UR-15 low-fidelity SBOM | Open | The artifact still needs an official CycloneDX generator with valid package identities, graph and runtime/dev scope. |
| UR-16 configuration drift | Open | A single typed configuration schema and one `.env` parser remain to be adopted across web, workers and operations. |
| UR-17 no global/changed-lines coverage | Open | Critical-module tests remain strong, but global baseline, changed-lines gate and selected mutation tests are not yet implemented. |
| UR-18 frontend runtime contracts | Partial | Auth/session is runtime-validated and fails closed; the other high-impact API responses still use compile-time casts. |
| UR-19 duplicate typecheck | Closed | Duplicate strict script/job removed; CI runs one authoritative typecheck. |
| UR-20 PWA language/assets | Closed | `lang=ro`, duplicate byte-identical 512 asset removed, and manifest/browser lifecycle gates pass. |

Totals: 11 closed, 3 partial, 6 open. All P0 findings are closed. P1 is closed
except the explicit external edge portion of UR-04. The audit's own projection
after P0+P1 is 8.8–9.0; a score above 9 remains unjustified until the major
complexity, supply-chain attestation/SBOM and coverage gaps are materially
closed and independently re-audited.

## Historical ASM reconciliation

The production dataset was evaluated read-only under old rounded decisions and
the new exact decisions: 511 ASM-month combinations over 36 months
(2023-09 through 2026-08). Nineteen results differ: 6 island, 13 focus, zero
zone and zero homogeneity changes. Every difference removes a false rounded
award; aggregate absolute/net impact is 2,150 RON, maximum 200 RON for one
ASM-month. No salary or production business data was written.

## Next efficient lot

Do not reopen the completed P0/P1 work. The highest score gain per unit of risk
is: UR-14 + UR-15 as one release-attestation lot, then small characterization-
test-backed extractions from UR-12, followed by UR-17. UR-09 should be handled
separately because it changes authentication concurrency behavior.
