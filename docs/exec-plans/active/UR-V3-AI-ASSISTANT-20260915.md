---
title: "UniHub Retail V3 — AI Sandbox Assistant"
status: active
created: 2026-09-15
tracker: "#403"
branch: v3/ai-assistant
pre_ai_candidate: 8d3dbea4b2c63a7351e957894c750f7ea1dc1590
production_changes_authorized: false
---

# 1. Product decision

V3 includes a private owner-facing AI work surface before final freeze.

The implementation is deliberately capability-first. The owner accepts the OpenAI Sandbox Agents beta status because the feature is private, request-driven and intended for learning/advanced personal use rather than general customer exposure.

The objective is not a chatbot that merely explains what could be done. It is a working analyst with a real sandbox that can inspect Retail data, inspect uploaded files, write code/scripts, manipulate files and return finished artifacts.

# 2. Architecture

```text
React application
  └─ AI panel / mobile full-screen chat
       ├─ current-view context
       ├─ file uploads
       ├─ effort selector
       ├─ streaming messages
       ├─ Stop / Steer
       └─ artifact attachments
              │
              ▼
FastAPI AI boundary
  ├─ authenticated owner-only session
  ├─ conversation/message/artifact metadata
  ├─ upload/download lifecycle
  └─ streaming run control
              │
              ▼
OpenAI Agents SDK
  └─ SandboxAgent(model=gpt-5.6-luna)
       ├─ lean custom instructions
       ├─ DockerSandboxClient
       ├─ filesystem capability
       ├─ shell capability
       ├─ compaction/session resume
       └─ ordinary agent tools if later justified
              │
              ▼
Docker workspace
  /workspace/knowledge
  /workspace/input
  /workspace/work
  /workspace/output
       ├─ psql / read-only Retail DSN
       ├─ Python/pandas/openpyxl/xlsxwriter
       ├─ python-pptx
       ├─ matplotlib/Pillow
       ├─ PDF/HTML tooling
       ├─ LibreOffice/Pandoc/Chromium where useful
       ├─ Node/git/curl/jq/ripgrep/zip
       └─ normal network access
```

No multi-agent graph, approval engine, workflow engine, scheduler, customer permission platform or generic MCP infrastructure is part of V1.

# 3. Technical boundaries

The few hard boundaries are architectural rather than prompt-heavy:

1. OpenAI API key is server-side only and dedicated to the feature.
2. Sandbox receives a dedicated PostgreSQL identity that is technically read-only for Retail business data.
3. Sandbox does not receive write-capable Retail DB credentials, session secrets or application deployment credentials.
4. Sandbox workspace is separate from application source/runtime paths; `/workspace` is the agent's computer.
5. V1 runs only in direct response to an authenticated owner request. No autonomous background execution.

Inside those boundaries the sandbox should remain broadly capable: direct SQL, Python, shell, file editing, package installation, network use and artifact generation are expected capabilities.

# 4. Harness

Keep the model-facing harness short. Long stable knowledge belongs in workspace files.

Target base intent:

```text
You are the private AI analyst and working agent inside UniHub Retail.
Work only when the owner sends a request.
Use the sandbox freely to inspect data, write code, manipulate files,
perform analysis and produce finished artifacts.
Do the work instead of merely describing how it could be done.
Query Retail through the provided read-only data boundary when data is needed.
Use the current UI context when the owner refers to the current page/card/selection.
Owner uploads are under /workspace/input.
Use /workspace/work for intermediate work and /workspace/output for final deliverables.
Do not ask unnecessary confirmation questions.
```

The implementation may use `base_instructions` because the owner explicitly prefers a lean custom harness over a larger default sandbox wrapper. Since Sandbox Agents are beta, exact SDK APIs must be revalidated against current official OpenAI documentation immediately before implementation/certification.

# 5. Knowledge bundle

Initial files under `/workspace/knowledge` should be concise and versioned from repository truth where possible:

- `APP.md` — navigation, major screens, current-view semantics;
- `BUSINESS.md` — firm/store/manager/agent vocabulary and owner-specific analysis conventions;
- `METRICS.md` — KPI names, formulas, units, sources, cutoff/freshness;
- `DATA.md` — important read models/tables, identity conventions, recommended query paths;
- `ARTIFACTS.md` — file/output conventions and expected deliverable quality.

Do not dump the whole schema/system prompt into every turn. The model can inspect these files when relevant.

# 6. UI behavior

## Desktop

A right-side panel, default width around 460 px, bounded and resizable. It can remain pinned while the application stays usable. Collapsing it leaves a subtle AI affordance.

## Tablet

Open as a right-side overlay/drawer occupying a large fraction of the viewport. Do not permanently compress primary Retail surfaces.

## Mobile

Open a full-screen chat surface rather than a miniature sidebar.

## Composer

Minimal controls:

- attach/upload;
- include current-page context toggle;
- reasoning effort selector;
- send;
- Stop while running;
- Steer when a new message is submitted during an active run.

Messages support copy, retry where useful, compact activity states and artifact attachments. Never expose hidden chain-of-thought.

# 7. Current-view context

Reuse the existing safe Retail context projection instead of inventing a second navigation state model. Each turn may include a compact envelope derived from current application state:

- tab/section/subtab;
- period/month;
- active filters;
- selected business identity when available;
- current deep-link/saved-view context;
- later: explicit visible card IDs where useful.

The context toggle controls whether that envelope is attached to the turn.

# 8. Persistence model

Keep persistence small:

- conversation: owner subject, title, created/updated, effort, sandbox resume state;
- message: conversation, role, text/status/timestamps;
- attachment/artifact: message/conversation, safe filename, MIME, size, storage path, kind=input/output.

The host application can write this metadata using its own application DB role. This does not grant the sandbox/model a write-capable business connection.

# 9. Streaming / Stop / Steer

The UI must stream model output/tool activity through the normal Agent Runner streaming APIs.

- Stop: cancel the active run.
- Steer: while the run is active, accept a new owner message and redirect the next model step using resumable run state rather than throwing away the conversation/workspace.

The exact beta API is verified at implementation time; no custom orchestration framework is introduced merely to emulate SDK functionality already available.

# 10. Artifact contract

Uploads are copied into `input/` for the conversation workspace. Finished files under `output/` are copied/registered into Retail-owned artifact storage and rendered as downloadable chat attachments.

V1 certification must demonstrate at least:

- XLSX;
- PPTX;
- PDF or print-quality HTML;
- image/chart;
- inspection of an owner-uploaded image/file.

# 11. Implementation slices

## Slice A — UI shell and transport contracts

- responsive assistant shell;
- open/collapse/resize state;
- message list/composer;
- attachments affordance;
- effort selector;
- current-view context toggle;
- Stop/Steer UI state;
- typed transport interfaces;
- owner-only visibility using the existing owner capability boundary rather than a new permissions framework.

## Slice B — SDK runtime

- normal locked dependency update for `openai-agents`;
- `SandboxAgent` + `DockerSandboxClient`;
- custom instructions + manifest/workspace layout;
- streaming and run cancellation/resume;
- server-side dedicated API-key configuration.

## Slice C — persistence/files

- minimal migrations/repositories for conversations/messages/artifacts if repository evidence confirms DB persistence is preferable to an existing suitable store;
- upload/download;
- workspace/sandbox resume state;
- artifact discovery.

## Slice D — Retail knowledge/data

- dedicated database read-only role/config;
- knowledge bundle;
- current-view context envelope;
- direct SQL/Python workflow proof.

## Slice E — certification

- focused tests during iteration;
- real isolated Docker sandbox integration on Dell only where execution capability is required;
- artifact smoke;
- read-only DB proof;
- responsive browser smoke;
- full exact-candidate V3 certification;
- controlled `main -> V3` compatibility integration after the feature is complete;
- final V3 candidate certification before any production merge decision.

# 12. Repository policy during this feature

- active source branch: `v3/ai-assistant`;
- V3 merge target: `v3/main` only;
- `main` is read-only until the later explicit compatibility integration into V3;
- no deployment/tag/release/production DB mutation is implied;
- GitHub actions/reviews are milestone gates, not iteration loops;
- Dell is used for real execution gaps (dependency lock generation, Docker/sandbox runtime, browser/full-stack certification), not routine code authoring that can be performed directly through repository tooling.
