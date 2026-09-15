---
title: "UniHub Retail V3 — AI Assistant durable handover"
status: active
updated: 2026-09-15
tracker: "#403"
branch: v3/ai-assistant
---

# Resume first

GitHub current state is authoritative. Re-fetch `main`, `v3/main`, `v3/ai-assistant`, open PRs and #403 before acting.
Read #403, #267 and `docs/exec-plans/active/UR-V3-AI-ASSISTANT-20260915.md` together with this file.

# Working model

ChatGPT is principal engineer/control plane and authors/reviews code directly whenever practical. Dell/DSH is only for real local execution gaps: dependency locking, Docker/runtime, actual SDK execution, browser/full-stack tests, performance evidence and exact-candidate certification. Codex is not the default V3 path. GitHub Actions/reviews are milestone gates, not iteration loops.

Every Dell prompt starts with difficulty 1–10, task type, recommended agent, whether top-tier is required, and escalation conditions. Scale: 1–3 LOW, 4–6 MEDIUM, 7–8 HIGH, 9 VERY HIGH, 10 CRITICAL.

# Owner/product policy

Capability-first, private owner-only AI: `gpt-5.6-luna`, OpenAI Agents SDK SandboxAgent beta, DockerSandboxClient, effort none/low/medium/high/xhigh/max, lean custom instructions, direct PostgreSQL through a technically read-only DSN, broad sandbox shell/filesystem/network/package-install capability, `/workspace/{knowledge,input,work,output}`, uploads, artifacts, streaming, Stop/Steer, durable conversations/artifacts, desktop sidebar/tablet drawer/mobile full-screen.

Do not add multi-agent orchestration, generic workflow/approval systems, generic MCP infrastructure, background autonomy, scheduler or voice in V1 without a concrete owner request. Hard boundaries are technical: API key server-side, no write-capable Retail DB credential in sandbox, no production/deploy credentials in sandbox, no autonomous background run.

# Repository authority

Known stable lines:
- production `main`: `8c0bcd69a61fdf26aec746da2651de4c2aa3f020`; owner froze parallel main work until V3 completes;
- `v3/main`: `d2980c4704d059e832a1a10b8f44aba60f2ed655`;
- AI execution foundation was certified at `41b731acdb7c0a6688ffb3bb27957a43244d7b8d`.

Re-fetch current `v3/ai-assistant`: runtime authoring continued beyond that foundation SHA.

No V3 work merges to main during implementation. Final path: complete #403 -> certify -> merge to `v3/main` -> freeze feature work -> one controlled `main -> V3` compatibility integration -> full final certification -> explicit owner decision for any `V3 -> main` integration.

# Completed AI foundation

- responsive owner-only shell/composer, context toggle, all Luna effort levels, uploads/artifact UI, Send/Steer/Stop;
- knowledge bundle;
- `openai-agents[docker]==0.22.2` + sandbox environment hash-locked;
- pinned Docker base and successful capable sandbox build;
- runtime package install + outbound HTTPS proven;
- XLSX/PPTX/PDF/HTML/PNG + CSV->XLSX smoke proven;
- exact installed SDK proved SandboxAgent/DockerSandboxClient, `max_turns=None`, cancel, after_turn, `to_state()` and `RunState.add_input()`.

# Current runtime slice

ChatGPT has now authored the vertical runtime on `v3/ai-assistant`:
- owner-only `/api/ai` FastAPI boundary;
- conversation/message/artifact persistence and migration `086_v3_ai_assistant.sql`;
- input/output host storage;
- loopback single-worker `unihub-ai` runtime;
- SandboxAgent/DockerSandboxClient construction;
- read-only DSN injection into sandbox;
- streaming NDJSON proxy;
- Stop + Steer run-state handling;
- current-view/upload staging;
- generated artifact discovery/download;
- frontend API/hook/container wiring replacing the old no-op shell;
- systemd/runtime env definitions;
- focused backend/frontend transport/settings tests.

This slice is NOT certified merely because it exists in Git. Next local checkpoint must compile/test it, verify manifest checksum/migration on an isolated DB, exercise Docker runtime, prove DB write rejection using a dedicated read-only login, and run a tiny live Luna end-to-end probe only if the dedicated API key is explicitly configured.

# Important repository-history note

During direct GitHub authoring, a transient manifest-only commit with message `TEMP DO NOT USE` was accidentally created and then immediately corrected by normal forward commits; no force-push was used. Current tree, not that historical intermediate commit, is authoritative. Local certification must verify the final manifest and tree only.

# Data identity

Provision the sandbox DSN using a dedicated LOGIN that has only read authority (for example membership in the existing `unihub_web_read` surface), never business-write/migration/operations authority. The application web role may write AI metadata tables; the sandbox/model may not.

# Next Dell checkpoint

Expected difficulty: 8/10 HIGH; integration/debugging/certification; strong coding agent with medium-high reasoning; top-tier not required initially. Escalate only for material SDK-beta incompatibility, Docker lifecycle/snapshot semantics contradicting the proven 0.22.2 API, migration authority conflicts, or a real Stop/Steer concurrency defect.

Dell may make only bounded mechanical corrections demonstrated by failing compile/test/runtime evidence. It must not redesign the feature or touch `main`, `v3/main`, production services/DB/Valkey, deploy, tags/releases, Codex, or unrelated code.

# Session recovery

1. Re-fetch current refs.
2. Read this file, #403, #267 and primary AI plan.
3. Inspect open PRs/issues; GitHub wins over stored SHAs.
4. Independently match any Dell report to exact head/tree/diff.
5. Continue from first unfinished item; do not repeat green evidence on unchanged trees.
6. Keep #403 and this handover current at material checkpoints.

# #403 stop condition

Do not close until exact-candidate evidence proves: live Luna SandboxAgent, real Docker workspace, technically read-only Retail DB access + failed-write proof, current-page context, uploads, streaming, Stop/Steer, durable conversation/artifact behavior, downloadable XLSX/PPTX/PDF-or-HTML/image artifacts, responsive desktop/tablet/mobile behavior, and no known Critical/High or release-blocking Medium defect.
