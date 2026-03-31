# UniHub — Project Guide

## About the User

- Name: Andrei
- Role: Team manager at Mobiup
- Background: Non-technical but passionate about development
- Language: Romanian
- OS: Windows
- Tone preference: Direct, technical, no padding. Short explanations of what was done and why.

---

## Project State

- Local application, no Docker, no deployment
- Stack: React 19 + Vite + TypeScript (frontend) / FastAPI + asyncpg + PostgreSQL 18 (backend)
- All 5 modules functional: Hub, Focus, Agenti, Vizite, Setari
- 27 pytest passing, typecheck and build passing

Start:
```
npm run dev          # frontend on :3000
npm run dev:backend  # backend on :8000
```

---

## Important Structure

### Frontend — `src/components/`
| File | Role |
|------|------|
| `App.tsx` | Auth + tab routing |
| `MainLayout.tsx` | Main shell, navigation, filters |
| `Dashboard.tsx` | Hub tab |
| `Campaigns.tsx` | Focus tab |
| `Agents.tsx` | Agenti tab — includes AgentDrawer, AgentDetails |
| `SalariiSubtab.tsx` | Salarii sub-tab in Agenti |
| `Visits.tsx` | Vizite tab |
| `Settings.tsx` | Settings tab (admin) |
| `ErrorBoundary.tsx` | React error boundary |

### Backend — `backend/routers/`
| Router | Prefix |
|--------|--------|
| `auth` | `/api/auth` |
| `dashboard` | `/api/dashboard` |
| `campaigns` | `/api/campaigns` |
| `filters` | `/api/filters` |
| `imports` | `/api/imports` |
| `stores` | `/api/stores` |
| `visits` | `/api/visits` |
| `admin` | `/api/admin` |
| `agents` | `/api/agents` |
| `salarii` | `/api/salarii` |

### Database
- Single schema: `backend/db/schema_v2.sql`
- Applied hash-based at boot via `ensure_schema_current()` in `backend/db/connection.py`
- **Do NOT modify schema directly in DB** — edit `schema_v2.sql` and restart backend
- Reporting on aggregates: `reporting_agent_*`, `reporting_item_*`, `reporting_focus_*`, `reporting_category_*`

---

## Work Rules

### Do NOT read from `sales_transactions` for reporting
All reporting queries go on `reporting_*` aggregates. Exception: punctual administrative lookups.

### Pydantic Models in `backend/models.py`
Any field returned by an endpoint must be declared explicitly in the corresponding Pydantic model, otherwise Pydantic removes it from the response.

### Frontend Filters
The global filter (firma, regional, asm, magazin) from `MainLayout` is shared between Hub and Focus.
The **Agenti** module has its own independent filters.

### Roles & Access Control

| Rol | Hub | Vizite | Focus | Agenti | Salarii | AI | Settings |
|-----|-----|--------|-------|--------|---------|----|---------|
| **TL** | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | tema |
| **ASM** | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | tema |
| **Management** | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | tema |
| **Admin** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ALL |

- Roles: `admin`, `asm`, `management`, `tl`
- `tl` sees only assigned stores
- Settings: non-admin users see only theme switcher + logout
- Default dev passwords: `9999`

### ErrorBoundary
Imported as `import { ErrorBoundary } from './ErrorBoundary'` in `Agents.tsx`.
There is **no** `error-catcher.tsx` at the project root anymore.

---

## MiniMax Agent

MiniMax M2.7 is available as a coding sub-agent via MCP:

- Tool: `minimax_code(task, context, language)` — generates code
- Tool: `minimax_fix(code, error, language)` — fixes bugs
- Tool: `minimax_review(code, focus)` — code review
- Tool: `minimax_ask(question)` — technical questions

---

## Session Start Checklist

1. Read this file
2. Read `HANDOFF.md` for architectural details
3. Ask Andrei what he wants to work on today
4. Start the app if needed: `npm run dev` + `npm run dev:backend`

---

## What NOT to Do

- Do not create temporary files in the project root (`fix.py`, `patch.txt`, etc.) — clean up after
- Do not modify schema directly in DB
- Do not reset user passwords without explicit confirmation
- Do not use `../../error-catcher` as import path — it moved to `src/components/ErrorBoundary.tsx`
