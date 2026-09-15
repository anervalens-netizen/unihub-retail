---
title: "UniHub Retail V3 — AI Assistant durable handover"
status: active
updated: 2026-09-15
tracker: "#403"
branch: v3/ai-assistant
---

# Resume first

This file exists so a fresh ChatGPT session can continue without relying on chat history.
GitHub current state is authoritative: always re-fetch `main`, `v3/main`, `v3/ai-assistant`, open PRs and #403 before acting.

Read together:
- #403 — active AI feature tracker;
- #267 — current V3 master authority;
- `docs/exec-plans/active/UR-V3-AI-ASSISTANT-20260915.md` — product/architecture plan.

# Working model

ChatGPT is principal engineer/control plane and should author/review code directly through GitHub tooling whenever practical.
Dell/DSH is only for real local execution gaps: dependency locking, Docker/runtime, actual SDK execution, browser/full-stack tests, performance evidence and exact-candidate certification.
Codex is not the default V3 development path.
GitHub Actions/reviews are milestone gates, not iteration loops.

Every Dell prompt must start with:

```text
DIFFICULTY: N/10 — LOW|MEDIUM|HIGH|VERY HIGH|CRITICAL
TYPE: ...
RECOMMENDED AGENT: ...
TOP-TIER REQUIRED: YES|NO
ESCALATE IF: ...
```

Scale: 1–3 LOW, 4–6 MEDIUM, 7–8 HIGH, 9 VERY HIGH, 10 CRITICAL. Difficulty measures reasoning/integration risk, not prompt length.

# Owner/product policy

Capability-first, private owner-only AI:
- `gpt-5.6-luna`;
- OpenAI Agents SDK `SandboxAgent` beta accepted;
- `DockerSandboxClient`;
- effort `none|low|medium|high|xhigh|max`;
- lean custom base instructions;
- direct PostgreSQL through a dedicated technically read-only DSN;
- broad sandbox shell/filesystem/network/package-install capability;
- `/workspace/{knowledge,input,work,output}`;
- uploads, generated artifacts, streaming, Stop and Steer;
- persistent conversations/artifacts;
- desktop sidebar, tablet drawer, mobile full-screen chat.

Do not add multi-agent orchestration, generic workflow/approval systems, generic MCP infrastructure, background autonomy, scheduler or voice in V1 without a concrete owner request.

Hard boundaries are technical only: API key server-side, no write-capable Retail DB credential in the sandbox, no production/deploy credentials in the sandbox, no autonomous background run.

# Repository authority

At the latest known stable checkpoint before the current direct runtime slice:
- production `main`: `8c0bcd69a61fdf26aec746da2651de4c2aa3f020` — owner has frozen parallel main work until V3 is complete;
- `v3/main`: `d2980c4704d059e832a1a10b8f44aba60f2ed655`;
- sandbox execution foundation: `v3/ai-assistant@41b731acdb7c0a6688ffb3bb27957a43244d7b8d`, tree `5f6ec5d4d4ea498d1eed72708af11ff48fa52fbb`.

Re-fetch because the current runtime authoring commit may be newer than the SHA above.

No V3 work merges to `main` during implementation. Final flow is: complete #403 -> certify -> merge to `v3/main` -> freeze feature work -> one controlled `main -> V3` compatibility integration -> full final certification -> explicit owner decision for any `V3 -> main` production integration.

# Completed AI foundation

- responsive owner-only UI shell/composer;
- context toggle and all Luna effort levels;
- uploads + artifact UI;
- Send/Steer/Stop controls;
- knowledge bundle;
- `openai-agents[docker]==0.22.2` hash-locked;
- hash-locked sandbox Python environment;
- pinned Docker base and successful sandbox build;
- sandbox toolchain + runtime package install + outbound HTTPS proven;
- XLSX/PPTX/PDF/HTML/PNG and CSV->XLSX artifact smoke proven;
- installed SDK 0.22.2 directly proved SandboxAgent/DockerSandboxClient, `max_turns=None`, cancel, after_turn, `to_state()` and `RunState.add_input()`;
- stale AI temporary branch deleted.

# Current direct-authoring slice

ChatGPT is wiring the actual vertical runtime on `v3/ai-assistant`:
- owner-only `/api/ai` FastAPI boundary;
- conversation/message/artifact persistence;
- input/output host storage;
- loopback single-worker `unihub-ai` runtime;
- live SandboxAgent/DockerSandboxClient construction;
- read-only DSN injection into sandbox;
- streaming NDJSON proxy;
- Stop + Steer run-state handling;
- current-view and uploaded-file staging;
- generated artifact discovery/download;
- frontend hook/API transport replacing the previous no-op shell wiring;
- migration `086_v3_ai_assistant.sql`;
- systemd/runtime env definitions.

This slice is not certified merely because it exists in Git. The immediate next local checkpoint must compile/test it, update the immutable migration manifest mechanically for 086, run the migration on an isolated database, exercise the runtime with Docker, and run a tiny live Luna end-to-end probe only if the dedicated API key is explicitly configured.

# Data identity

The sandbox read-only login should be provisioned as a dedicated LOGIN with only read authority (for example membership in the existing `unihub_web_read` surface), not a business-write/migration/operations role. The model may query directly with `psql`/Python/pandas, but the database itself must reject writes.

The application's normal web role may write only AI conversation/message/artifact metadata through the new AI tables; that does not grant the sandbox write authority.

# Dell/local execution rule for the next checkpoint

Expected difficulty: 8/10 HIGH; integration/debugging/certification; strong coding agent with medium-high reasoning; top-tier not required initially.
Escalate only for material SDK-beta incompatibility, Docker lifecycle/snapshot semantics that contradict the proven 0.22.2 API, migration authority conflicts, or a real Stop/Steer concurrency defect.

Dell may make only bounded mechanical corrections demonstrated by failing compile/test/runtime evidence. It must not redesign the AI feature or touch `main`, `v3/main`, production services/DB/Valkey, deployment, tags/releases, Codex, or unrelated code.

# Session recovery

1. Re-fetch current refs.
2. Read this file, #403, #267 and the primary AI plan.
3. Inspect open PRs/issues; current GitHub wins over stored SHAs.
4. If a Dell report exists, independently match its claimed head/tree/diff.
5. Continue from the first unfinished item; do not repeat green evidence on unchanged trees.
6. Keep #403 and this handover current at material checkpoints.

# #403 stop condition

Do not close #403 until exact-candidate evidence proves end-to-end:
- live Luna SandboxAgent;
- real Docker workspace;
- technically read-only Retail DB access and failed-write proof;
- current page context;
- uploads;
- streaming;
- Stop and Steer;
- durable conversation/artifact behavior;
- downloadable XLSX/PPTX/PDF-or-HTML/image artifacts;
- responsive desktop/tablet/mobile behavior;
- no known Critical/High or release-blocking Medium defect.
