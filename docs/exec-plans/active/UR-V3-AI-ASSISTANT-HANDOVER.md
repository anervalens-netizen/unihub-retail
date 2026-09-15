---
title: "UniHub Retail V3 — AI Assistant durable handover"
status: active
updated: 2026-09-15
tracker: "#403"
branch: v3/ai-assistant
---

# Resume first

GitHub current state is authoritative. Re-fetch `main`, `v3/main`, `v3/ai-assistant`, open PRs and #403 before acting. Read #403, #267 and `docs/exec-plans/active/UR-V3-AI-ASSISTANT-20260915.md` together with this file.

# Working model

ChatGPT is principal engineer/control plane and authors/reviews code directly whenever practical. Dell/DSH is only for real local execution gaps: dependency locking, Docker/runtime, actual SDK execution, browser/full-stack tests, performance evidence and exact-candidate certification. Codex is not the default V3 path. GitHub Actions/reviews are milestone gates, not iteration loops.

Every Dell prompt starts with difficulty 1–10, task type, recommended agent, whether top-tier is required, and escalation conditions. Scale: 1–3 LOW, 4–6 MEDIUM, 7–8 HIGH, 9 VERY HIGH, 10 CRITICAL.

# Owner/product policy

Capability-first, private owner-only AI: `gpt-5.6-luna`, OpenAI Agents SDK SandboxAgent beta, DockerSandboxClient, effort none/low/medium/high/xhigh/max, lean custom instructions, direct PostgreSQL through a technically read-only DSN, broad sandbox shell/filesystem/network/package-install capability, `/workspace/{knowledge,input,work,output}`, uploads, artifacts, streaming, Stop/Steer, durable conversations/artifacts, desktop sidebar/tablet drawer/mobile full-screen.

Do not add multi-agent orchestration, generic workflow/approval systems, generic MCP infrastructure, background autonomy, scheduler or voice in V1 without a concrete owner request. Hard boundaries are technical: API key server-side, no write-capable Retail DB credential in sandbox, no production/deploy credentials in sandbox, no autonomous background run.

No generic AI quota/workflow/approval layer exists or is planned. The boundary is authenticated owner-only access, CSRF/body limits, one active run per conversation and a narrow technical admission bound added by the PR #409 review: at most two concurrent runs per authenticated owner plus a ten-run-starts-per-minute owner rate limit. Both exist only to make Docker/model spend finite; an accepted run keeps unlimited internal turns and tool calls.

# Repository authority

Stable lines at this checkpoint:
- production `main`: `8c0bcd69a61fdf26aec746da2651de4c2aa3f020`; owner froze parallel main work until V3 completes;
- `v3/main`: `d2980c4704d059e832a1a10b8f44aba60f2ed655`;
- AI execution foundation was certified at `41b731acdb7c0a6688ffb3bb27957a43244d7b8d`;
- `v3/ai-assistant` PR #409 head before review remediation: `9a95ac872d041aa7867fd7907d5935d5a6fc5858`;
- final pushed candidate after review closure: `86719765b3baa21785e95ca77cb81673c1562d88` (tree `16b65930a1f8fb666661dcb3d03d8a192c0361c8`).

Re-fetch before use; GitHub wins over these stored SHAs.

No V3 work merges to main during implementation. Final path: complete #403 -> certify -> merge to `v3/main` -> freeze feature work -> one controlled `main -> V3` compatibility integration -> full final certification -> explicit owner decision for any `V3 -> main` integration.

# Completed AI foundation

- responsive owner-only shell/composer, context toggle, all Luna effort levels, uploads/artifact UI, Send/Steer/Stop;
- knowledge bundle;
- `openai-agents[docker]==0.22.2` + sandbox environment hash-locked;
- pinned Docker base and successful capable sandbox build;
- runtime package install + outbound HTTPS proven;
- XLSX/PPTX/PDF/HTML/PNG + CSV->XLSX smoke proven;
- exact installed SDK proved SandboxAgent/DockerSandboxClient, `max_turns=None`, cancel, after_turn, `to_state()` and `RunState.add_input()`.

# Runtime certification finding and decision

The first runtime integration checkpoint reproduced a real concurrency bug: two simultaneous runs could both pass the old active check, overwrite `_active`, Stop could cancel only the newer result, and old cleanup could remove the newer reservation. Stop also could not see setup before `_active` registration, and Stop-vs-Steer had a resume gap.

The architecture has now been corrected directly on the AI branch:

- reserve a per-conversation ActiveRun before Docker setup;
- identity token + phase + owner task + sandbox + current result;
- only one reservation may exist per conversation;
- setup is bounded by `AI_ASSISTANT_SETUP_TIMEOUT_SECONDS` and is stoppable before model execution;
- Steer uses SDK `cancel(mode="after_turn")`, queued inputs and `RunState.add_input()`;
- a stopped run cannot install a resumed result;
- pending Steers carry durable DB ordering and are sorted before resume;
- cleanup is identity-checked and Docker cleanup explicitly calls both sandbox close and `DockerSandboxClient.delete(session)`;
- runtime proxy uses bounded connect/write/pool timeouts while retaining an unbounded streaming read.

Focused state-machine tests were added, but this exact branch has not yet been locally compiled/executed after the redesign.

# Persistence decisions

- User submissions are durable user actions even when a model/runtime attempt fails. Do not silently erase them.
- Runtime failures are recorded as assistant error messages so history remains truthful.
- Input files are prepared before one transactional metadata operation; written files are removed if DB metadata commit fails.
- Assistant message + output artifact metadata + continuation ID update are one DB transaction; host-side generated files are removed if that metadata transaction fails.
- `ai_assistant_messages` now uses a deterministic BIGSERIAL `ordinal` so concurrent Steer HTTP responses cannot reorder durable chat history.
- File-only Turn and file-only Steer are valid.
- Special/empty filenames are normalized to a safe non-empty name.

# Docker/PostgreSQL network decision

The sandbox uses normal Docker networking. `127.0.0.1` or `localhost` in `AI_ASSISTANT_READONLY_DSN` points to the sandbox container and is invalid. Runtime configuration now rejects loopback/unspecified database hosts.

The DSN must name one explicitly reviewed PostgreSQL endpoint reachable from the Docker sandbox. For isolated certification, use the disposable database's bridge-reachable address. Production will select/configure the corresponding bridge-reachable endpoint during deployment. Do not fork/subclass the OpenAI Docker sandbox client solely to make localhost work.

# Migration 086

Migration source content is authoritative; the old requested/manifest checksum `939b1a…` was stale. The migration has since intentionally changed again to add deterministic message ordinals and sequence authority.

**Current known gate:** `backend/db/migrations/manifest.json` is intentionally stale until the next local checkpoint computes SHA-256 from the exact current `086_v3_ai_assistant.sql` bytes and updates the manifest. Do not merge/certify with manifest drift. The main agent's locally calculated expected hash for the current intended SQL text was `0f2d4db3c5de689ad08e289435bb87b332f4039443d3dafd2ea601676ff881ce`, but Dell must calculate it independently from Git bytes and Git wins if it differs.

# Generated contracts

The generated Retail OpenAPI/contracts may and should be regenerated once the public AI routes stabilize. Their old 110-operation snapshot is not authoritative. Contract regeneration is explicitly allowed as a mechanical generated-artifact update.

# Frontend race decisions

The AI container now remains mounted across transient P&L capability refetches, while the panel still hides when access is false. The hook preserves an active stream rather than losing it during a temporary permission fetch.

Bootstrap/new-conversation updates use a selection epoch so a late bootstrap cannot overwrite a newer owner choice. Steer responses refresh persisted messages from the server rather than append in HTTP response order, preserving DB ordering.

# PR #409 review remediation

Six Codex findings were remediated on this branch without redesigning any
certified execution path:

- the nested AI state path is provisioned by systemd `StateDirectory` in both
  `unihub-ai.service` and `unihub-backend.service`, so a first deployment no
  longer depends on an administrator creating it before `ReadWritePaths` is
  evaluated;
- `AI_ASSISTANT_READONLY_DSN` is no longer accepted on syntax alone: the
  runtime connects with that exact credential at startup and fails closed
  unless the login is a direct member of exactly `unihub_web_read`, has no
  elevated role attribute, holds no effective INSERT/UPDATE/DELETE/TRUNCATE on
  application tables or CREATE on application schemas/databases, and inherits
  bounded `statement_timeout`/`lock_timeout`/`idle_in_transaction_session_timeout`
  defaults. `/health` stays 503 until the preflight passes;
- run creation is bounded per owner (runtime concurrent ceiling, default 2, plus
  the `ai_turn` rate policy) before upload staging, sandbox creation or any model
  call, while internal turns stay unlimited;
- Steer is only submitted while a run is genuinely `running`; a `stopping` run
  is never steerable and the draft is never queued;
- host-side artifact collection validates every candidate before writing and
  rolls the whole call back on failure, so a failed run leaves no invisible
  files and earlier artifacts are untouched;
- `backend/requirements-dev.lock` was regenerated with hashes.

`ops/ai-sandbox/runtime.env.example` documents the required role, the SQL that
provisions it and the mandatory bounded session defaults. The repository still
carries no automated provisioning step for that login, so it must exist before
the runtime can become healthy; the runtime now refuses to serve a run until it
does. Production database state was not inspected or modified by this change.

# PR #409 final review closure

This section supersedes the older checkpoint instructions below. Start for this
closure was `a5fbe4359321c1343863cc56508ac5b710400b5c`, integration base remains
`d2980c4704d059e832a1a10b8f44aba60f2ed655`; production was not accessed and main
was not modified.

- Changed artifacts now have sandbox-side path/hash/size metadata. All metadata
  is checked before payload transfer: 256 MiB individual, 1 GiB aggregate default
  (`AI_ASSISTANT_MAX_TOTAL_ARTIFACT_BYTES`, never below the individual limit).
  Payloads are fetched/written/released sequentially with an actual-byte counter;
  failures and cancellation roll back only this attempt, preserving prior output.
- The single AI runtime process owns its raw Docker client and reconciles **both
  exact** AI labels across all container states before accepting runs. Removal
  is forceful with volumes; enumeration/removal failure leaves readiness closed.
  Do not run two AI runtime processes against the same labeled container pool.
- `db_guard.py` uses the same verified dedicated read-only login, with no extra
  signaling role/credential and no application query proxy. Same-role cancel and
  terminate permissions were proven on disposable PostgreSQL. Server timestamps
  enforce active >300s / Lock-wait query >5s / idle transaction >60s, including
  aborted idle transactions, independently of sandbox `SET ... = 0`. Lock age is
  conservatively measured from query_start; ceilings include polling/scan latency.
  A spoofed guard application_name does not exempt a sandbox session.
- Readiness requires orphan cleanup + authority/default timeout verification + a
  successful guard scan. Connection loss/stale scans reject new runs (503), not
  existing model tasks; bounded reconnect backoff is 1..5s, readiness recovers on
  a successful scan. Shutdown closes the guard task/connection and Docker client.
- The local sales-promotion source-artifact verification extraction preserves
  ordering/transaction/fence semantics and reduces 124 to 107 lines. Live exact
  production-function invariants are 3047 -> 3151; counting/gates are unchanged.
- Bundle baseline was regenerated canonically after identical-toolchain builds
  of exact V3 base and candidate. Raw/gzip base -> candidate: entry 44443/13678 ->
  44912/13821; CSS 129120/18878 -> 133255/19352; vendor 261463/80716 ->
  261463/80715; UI 144694/47120 -> 146148/47552; charts 428671/118602 unchanged;
  precache 1371511/951287 -> 1377645/952346. AI remains a separate dynamic chunk
  (17523/5838), absent from static entry/preload/precache; it mounts with the shell,
  not only on first click. The authorized feature baseline refresh retains the
  4096-byte tolerance. No dependencies or bundler configuration changed.

Deterministic isolated proofs cover timeout overrides, other-role noninterference,
reconnect, and artifact limits/rollback. Real local Docker proof covers stale
running/exited/created/paused containers, unrelated preservation, and normal/Stop/
setup-failure cleanup. The automatic V3 backend lane now includes artifact,
authority, watchdog, admission, health and startup regressions alongside existing
Stop/Steer tests. Local closure: full isolated backend **3372 passed / 11 skipped /
0 failed**, focused AI **115 passed / 2 skipped**, full frontend **118 files / 907
tests**, exact complexity suites **80 passed**, full mypy **646 files**. The
opt-in real-Docker test passed separately (it is skipped in the ordinary suite).
The first full attempt was stopped after finding a stale race fake returning
empty bytes instead of metadata `[]`; only that fake was corrected, with no race
assertions removed. Global/changed complexity, architecture, env/OpenAPI/migration
contracts, Bandit, systemd verification and bundle budget pass. Live Luna smoke
was not run: `OPENAI_API_KEY` was absent from the task environment. Review-thread
resolution and merge remain owner-controlled.

# Earlier Dell checkpoint (historical)

Difficulty: **8/10 HIGH**.
Type: integration/debugging/certification.
Recommended agent: strong coding/execution agent with medium-high reasoning.
Top-tier required: NO initially.
Escalate only if the revised state machine still demonstrates an architectural race, SDK 0.22.2 materially contradicts the current design, or the isolated DB/network authority cannot satisfy the documented read-only contract.

The next local checkpoint must:

1. recreate a clean worktree from the current AI head; do not reuse old uncommitted patches as source of truth;
2. compute/fix migration 086 manifest hash from current bytes;
3. compile/typecheck/lint/build frontend and run focused AI tests;
4. run focused backend tests, mypy, architecture/complexity/migration gates;
5. re-run the previous Stop/Steer race reproducer plus the new reservation tests;
6. prove stop during setup and stop during Steer staging/resume cannot produce an uncancellable second run;
7. prove explicit Docker deletion leaves no sandbox container;
8. apply migration 086 to an isolated DB and prove deterministic message order + metadata transactions;
9. prove the dedicated AI DB login reads representative Retail data and PostgreSQL rejects all writes;
10. use a bridge-reachable isolated DSN, not loopback;
11. regenerate public OpenAPI/contracts;
12. run public API and responsive browser smoke;
13. run bounded live Luna E2E only if `OPENAI_API_KEY` is explicitly present in the isolated task environment.

Dell may make bounded mechanical corrections demonstrated by failing compile/test/runtime evidence. It must not redesign the feature or touch `main`, `v3/main`, production services/DB/Valkey, deploy, tags/releases, Codex, or unrelated code.

# Important repository-history note

A transient historical commit with message `TEMP DO NOT USE` was accidentally created during earlier direct authoring and then corrected through normal forward commits; no force-push was used. Never reset to or cherry-pick that intermediate commit. Current branch tree is authoritative.

# PR #409 final exact-head remediation

The `fee4fac19` review baseline required a separate host-only guard login, hard
container ceilings, restart-on-initial-preflight failure, Markdown-only CI
exclusion and definitive Steer-rejection compensation. The reviewed storage
architecture uses exactly two root-provisioned, physically allocated 8 GiB
ext4 loop filesystems. `unihub-ai-storage.service` mounts them before the AI
runtime; containers use a read-only root filesystem, one `/workspace` bind,
bounded tmpfs mounts, 2 GiB memory, 3 GiB memory+swap, 2 CPUs, 512 PIDs and
bounded local Docker logs. The unprivileged runtime can verify, allocate,
clean and quarantine slots but cannot mount, format or modify image files.

SDK 0.22.2's default workspace persistence copies bind contents through
container `/tmp`; the narrow Docker adapter instead archives the bind in a
drained worker, validates the exact restore policy, persists atomically under
a serialized 16 GiB aggregate snapshot-store ceiling, and restores after
stale-slot cleanup. A start that fails before hydration finishes
never replaces the last good snapshot. The runtime globally admits at most two
sandboxes, because allocation of conversation, owner capacity and a storage
slot occurs under one lock. Cleanup failure quarantines the slot.

The database guard authenticates only through `AI_ASSISTANT_GUARD_DSN` as
`unihub_ai_guard`, verifies the actual same PostgreSQL/database identity and
exact directional role graph on every connection, and signals only
`unihub_ai_readonly`. The sandbox login is fixed at `CONNECTION LIMIT 4` and
inherits no access to owner-private AI conversation, message or artifact rows. Initial preflight/first-scan failure propagates out of the
FastAPI lifespan so systemd retries; later disconnects remain recoverable in
process. A definite Steer HTTP 409 or exact runtime Turn admission rejection
transactionally removes only that persisted submission before deleting its
files; ambiguous transport/runtime failures preserve history. Final certification evidence and exact pushed SHA belong in the task
report; no production unit installation/restart or review-thread resolution is
part of this checkpoint.

# Final exact-head evidence

- Local isolated backend suite: **3438 passed, 13 skipped** after the final
  ordering/quota/cleanup closure; focused closure suite: **121 passed, 1 skipped**.
- Backend mypy: **656 source files, no issues**. Architecture: **400 modules,
  acyclic, direct DB exceptions 55/55**. Complexity: changed-function gate
  passed (maximum 20), ratchet passed, final production count **3192**.
- Migration manifest, Retail contract, environment contract, Bandit baseline and
  systemd/provisioner syntax all pass. Real disposable Docker proof: **2 passed**
  with cgroup/rootfs/tmpfs/log/workspace limits and snapshot resume. Root proof
  confirmed each 8 GiB image is physically allocated and unprivileged ENOSPC is
  enforced. Disposable images, mounts and containers were removed afterward.
- Automatic V3 CI run `35022127660` passed backend and frontend on the preceding
  code-only equivalent candidate. The next final push must be observed again;
  no manual Actions run or review-thread resolution is permitted. `OPENAI_API_KEY`
  is absent in this environment, so no live provider call was attempted.

# Session recovery

1. Re-fetch current refs.
2. Read this file, #403, #267 and primary AI plan.
3. Inspect open PRs/issues; GitHub wins over stored SHAs.
4. Independently match any Dell report to exact head/tree/diff.
5. Continue from first unfinished item; do not repeat green evidence on unchanged trees.
6. Keep #403 and this handover current at material checkpoints.

# #403 stop condition

Do not close until exact-candidate evidence proves: live Luna SandboxAgent, real Docker workspace, technically read-only Retail DB access + failed-write proof, current-page context, uploads, streaming, Stop/Steer, durable conversation/artifact behavior, downloadable XLSX/PPTX/PDF-or-HTML/image artifacts, responsive desktop/tablet/mobile behavior, and no known Critical/High or release-blocking Medium defect.
