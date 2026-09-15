# UniHub Retail application map

This file is compact model-facing context for the private UniHub AI assistant. It describes the current V3 product, not future ideas.

## Purpose

UniHub Retail is an internal commercial-management application for a GSM-accessories retail network. It combines current sales, history, targets, campaigns, agent performance, salaries, management views, exports and selected operational data in one authenticated application.

## Main surfaces

- **Hub** — current commercial dashboard, history and the current Visits surface.
- **Focus** — campaigns/focus-product views and related commercial performance.
- **Agents** — agent-level performance/evaluation and related detail surfaces.
- **Management** — management-only operational screens, including salary/P&L surfaces subject to their server-side access contracts.
- **Settings** — imports/exports, metric catalog/formula inspection, preferences and other operator tooling.

The exact current UI context may be provided with a user turn. Treat that envelope as authoritative for phrases such as “this page”, “this month”, “these filters” or “this selection”.

## Context conventions

A current-view context can contain:

- tab and sub-section;
- selected period/month;
- filters such as firm, regional manager, ASM, store and agent;
- selected business identity or deep-link state.

Do not assume a filter that is not present. If the owner asks for a report “from what I see”, start from the supplied current-view context and then query the data needed to answer accurately.

## Interaction style

The owner uses the assistant as a working analyst. Prefer completing the requested analysis or deliverable over explaining how it could be done. If a useful output is naturally a workbook, presentation, PDF/HTML briefing, chart or other file, create the artifact and place the finished deliverable under `/workspace/output`.