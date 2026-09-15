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

No extra AI-specific rate/quota layer is required in V1. The current boundary is authenticated owner-only access, CSRF/body limits and one active run per conversation. Add admission/quota only if measured usage or abuse evidence justifies it.

# Repository authority

Stable lines at this checkpoint:
- production `main`: `8c0bcd69a61fdf26aec746da2651de4c2aa3f020`; owner froze parallel main work until V3 completes;
- `v3/main`: `d2980c4704d059e832a1a10b8f44aba60f2ed655`;
- AI execution foundation was certified at `41b731acdb7c0a6688ffb3bb27957a43244d7b8d`;
- current AI branch after concurrency redesign: `03e04d5d31624a00bfaa28d1c67d3f9d29395619`, tree `058c22cb4629634d34670273044eaefd79d9a517`.

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

# Current next Dell checkpoint

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

# Session recovery

1. Re-fetch current refs.
2. Read this file, #403, #267 and primary AI plan.
3. Inspect open PRs/issues; GitHub wins over stored SHAs.
4. Independently match any Dell report to exact head/tree/diff.
5. Continue from first unfinished item; do not repeat green evidence on unchanged trees.
6. Keep #403 and this handover current at material checkpoints.

# #403 stop condition

Do not close until exact-candidate evidence proves: live Luna SandboxAgent, real Docker workspace, technically read-only Retail DB access + failed-write proof, current-page context, uploads, streaming, Stop/Steer, durable conversation/artifact behavior, downloadable XLSX/PPTX/PDF-or-HTML/image artifacts, responsive desktop/tablet/mobile behavior, and no known Critical/High or release-blocking Medium defect.
