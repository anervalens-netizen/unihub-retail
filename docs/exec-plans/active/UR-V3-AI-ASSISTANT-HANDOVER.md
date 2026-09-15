---
title: "UniHub Retail V3 — AI Assistant durable handover"
status: active
updated: 2026-09-15
tracker: "#403"
branch: v3/ai-assistant
---

# Purpose

This file is the durable handover for the V3 AI Assistant work while the implementation is active. It exists specifically so a new ChatGPT session can recover the working method, current state, boundaries and next step without relying on chat history.

GitHub current state remains the source of truth. Re-fetch refs before acting if this file and GitHub disagree.

# Working model

ChatGPT is the control plane / principal engineer for this feature.

Preferred workflow:

1. ChatGPT inspects GitHub directly and performs design, review, issue/tracker maintenance and code authoring through repository tooling whenever practical.
2. Do not use Codex as the default development path for this feature.
3. Dell/DSH is used only when real local execution is needed: dependency resolution/locking, Docker build/runtime, shell-level integration, browser/full-stack execution, local performance/capacity evidence, or exact-candidate certification.
4. Dell/DSH should not redesign the feature or expand scope unless explicitly instructed. It executes bounded prompts and returns evidence.
5. After each Dell report, ChatGPT reviews the evidence and GitHub diff independently before deciding the next change.
6. GitHub Actions and external AI reviews are milestone gates, not iteration loops.
7. Production `main` remains read-only during AI implementation. Final `main -> V3` compatibility integration is done once, after #403 is complete and V3 is otherwise ready.

# Dell prompt difficulty convention

Every future Dell/DSH prompt must start with an explicit difficulty header so the owner can select the most efficient agent/model.

Use this scale:

- 1–3 / 10 — LOW: mechanical/simple execution; fast inexpensive agent is sufficient.
- 4–6 / 10 — MEDIUM: normal coding/integration work; standard coding agent.
- 7–8 / 10 — HIGH: multi-surface execution/debugging; strong coding agent with medium-high reasoning.
- 9 / 10 — VERY HIGH: difficult architecture/concurrency/debugging; one of the strongest available agents.
- 10 / 10 — CRITICAL: highest-risk/most ambiguous technical work; strongest available agent and normally an independent review.

Difficulty is about reasoning/integration risk, not prompt length. A long deterministic certification prompt can be easier than a short concurrency/debugging task.

Each Dell prompt should include, near the top:

```text
DIFFICULTY: N/10 — <LOW|MEDIUM|HIGH|VERY HIGH|CRITICAL>
TYPE: <execution|integration|debugging|certification|migration|...>
RECOMMENDED AGENT: <brief recommendation>
TOP-TIER REQUIRED: YES/NO
ESCALATE IF: <specific conditions>
```

# Capability-first product policy

The owner explicitly prefers a capability-first implementation.

- OpenAI Sandbox Agents beta is accepted for this private owner-only feature.
- Avoid speculative harness restrictions that reduce capability or consume tokens without protecting a real irreversible boundary.
- Real boundaries are technical: dedicated server-side API key, Retail business DB role is read-only, no write-capable production credentials in the sandbox, sandbox workspace separated from application source/runtime, no autonomous background execution in V1.
- Inside those boundaries, the agent should have broad shell/filesystem/network/package-install/data-analysis/artifact-generation capability.
- The agent should do the work when it can, not merely explain how to do it.

# Chosen V1 architecture

- model: `gpt-5.6-luna`;
- OpenAI Agents SDK SandboxAgent beta path;
- `DockerSandboxClient`;
- reasoning effort selectable in UI: none/low/medium/high/xhigh/max;
- lean custom base instructions;
- persistent/resumable workspace per conversation where practical;
- workspace layout: `/workspace/knowledge`, `/workspace/input`, `/workspace/work`, `/workspace/output`;
- direct PostgreSQL access using a dedicated read-only Retail DSN;
- capable Docker image with Python/data/Office/PDF/HTML/browser/shell tooling and normal outbound network access;
- streaming chat with Stop and Steer;
- file/image upload and generated artifact attachments;
- desktop right sidebar, tablet drawer, mobile full-screen chat;
- minimal conversation/message/artifact persistence owned by UniHub.

Do not add multi-agent orchestration, generic workflow engines, approval frameworks, MCP infrastructure, autonomous scheduling or voice to V1 unless a concrete requirement appears.

# Current GitHub checkpoint (2026-09-15)

Reverify before use.

- `v3/main`: `d2980c4704d059e832a1a10b8f44aba60f2ed655`
- `v3/ai-assistant`: `1490393091a0d8b2fcb189e9322f0216c1f366e5`
- active tracker: #403
- parent V3 tracker: #267
- previous V3 finalization tracker #391: closed/completed
- stale Dependabot PR #398: closed/not planned
- open PR count after cleanup: zero at the time of this handover
- production `main` last observed: `8c0bcd69a61fdf26aec746da2651de4c2aa3f020`; do not rely on this SHA without re-fetching

The AI branch already contains the directly authored UI shell, tests, design/exec-plan documentation, knowledge bundle, sandbox Dockerfile/tooling definition and pinned direct dependency declaration for the Agents SDK.

# Current external execution task

Status at this checkpoint: WAITING FOR DELL/DSH REPORT.

The active Dell task is named:

`UniHub Retail V3 — AI ASSISTANT FIRST EXECUTION CHECKPOINT`

Difficulty:

- DIFFICULTY: 8/10 — HIGH
- TYPE: execution / integration / certification
- RECOMMENDED AGENT: strong coding/execution agent with medium-high reasoning
- TOP-TIER REQUIRED: NO for the first attempt
- ESCALATE IF: dependency resolution conflicts, Sandbox Agents beta API differs materially from documented expectations, Docker build/runtime fails non-mechanically, or steering/run-state APIs require architectural reinterpretation

The Dell task must only:

1. validate the authored frontend AI shell;
2. generate canonical backend dependency lock including `openai-agents[docker]==0.22.2`;
3. generate the sandbox Python requirements lock;
4. resolve/pin the Docker base image digest and build the sandbox image;
5. prove the sandbox toolchain, writable workspace, package install capability and outbound network;
6. generate XLSX/PPTX/PDF/HTML/PNG smoke artifacts;
7. inspect the installed Agents SDK 0.22.2 API exactly, including SandboxAgent, DockerSandboxClient, effort=max, max_turns=None, cancel/after_turn/to_state and RunState steering semantics;
8. optionally run one tiny live Luna sandbox probe only if an API key is already explicitly configured in the isolated test environment;
9. safely delete only stale branches proven redundant;
10. push only mechanical lock/digest/test corrections to `v3/ai-assistant`.

Dell must NOT implement the FastAPI AI runtime, persistence or migrations in this checkpoint.

# Next step after the Dell report

If the execution foundation is green:

1. ChatGPT independently verifies the resulting `v3/ai-assistant` head/diff.
2. ChatGPT authors the runtime layer directly where practical:
   - owner-only FastAPI AI boundary;
   - SandboxAgent/DockerSandboxClient construction;
   - model settings/effort mapping;
   - streaming transport;
   - Stop/Steer run-state handling;
   - upload/input workspace mapping;
   - output/artifact discovery;
   - current-view context injection.
3. Then add the smallest persistence/files layer required for durable conversations and artifacts.
4. Dell returns only when real local Docker/live API/browser execution is again required.
5. Once #403 is functionally complete: exact-candidate certification, merge AI work into `v3/main`, then one controlled `main -> V3` compatibility integration, resolve/test once, final candidate certification, and only then discuss production merge/deploy.

# Safety / branch boundaries

Until explicitly changed:

- write only to `v3/ai-assistant` for this feature;
- merge target is `v3/main` only;
- never merge V3 into production `main` during feature development;
- no production DB/Valkey/service/deploy/tag/release changes;
- no production secrets in the sandbox;
- no force-push/rebase/squash unless explicitly authorized;
- preserve exact-head evidence before calling a candidate clean.

# Session recovery checklist

A fresh ChatGPT session should do this before continuing:

1. Read this file.
2. Read #403 and the main exec plan `docs/exec-plans/active/UR-V3-AI-ASSISTANT-20260915.md`.
3. Re-fetch `main`, `v3/main`, `v3/ai-assistant`, open PRs and open V3-relevant issues.
4. Compare actual GitHub state to the checkpoint above; GitHub wins on drift.
5. If a Dell report is supplied, verify its claimed SHA/tree/diff before acting.
6. Continue from the first unfinished step; do not rebuild already completed slices from memory.
7. Every new Dell prompt must include the difficulty metadata convention above.

# Stop condition for this feature

#403 is ready to close only when the owner-facing AI assistant works end-to-end on the exact V3 candidate with:

- live Luna SandboxAgent;
- real Docker workspace;
- read-only Retail data access;
- current-page context;
- uploads;
- streaming;
- Stop and Steer;
- durable conversation/artifact behavior;
- XLSX/PPTX/PDF-or-HTML/image artifact proof;
- responsive desktop/tablet/mobile UI;
- no known Critical/High or release-blocking Medium defect.

After that, freeze the AI feature, merge it into `v3/main`, perform the one controlled production-main compatibility sync into V3, and certify the final V3 candidate.