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

- **GitHub:** https://github.com/anervalens-netizen/unihub (initial commit `6ac4c06`, 98 files)
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
| `Campaigns.tsx` | Focus tab (Campanii) — redesigned 2026-03-31 with promo/incentive cards |
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

## Session Log — 2026-03-31

### param_floor fix (TL/ASM 500 errors)
Multiple 500 errors on `/api/dashboard/all` and `/api/agents/overview` for TL/ASM were caused by `scope_params` (containing `user_id` for TL) being **prepended** before other params, shifting `$N` positions.

**Root fix:** Added `param_floor=len(params)` to ALL `scoped_clauses()` calls across `dashboard.py`, `dashboard_filters.py`, and `agents.py`. This ensures `scope_params` are always appended at the **end** of the param list, leaving hardcoded positions ($1, $2, $3) untouched.

Files changed:
- `backend/routers/dashboard_filters.py`: `where_clauses()` and `transaction_filter_parts()` now pass `param_floor=len(params)`
- `backend/routers/agents.py`: overview query fixed: `*params[1:]` → `*params, prev_month`
- `backend/routers/shared.py`: `build_scope_filter` uses `param_start` for TL scope params

Also cleaned up duplicate `_get_special_cards_data` query block (lines ~1894-1932).

### TL tab IDs unified
`App.tsx` and `MainLayout.tsx` tab IDs unified to `hub`/`focus`/`agents`/`ai`/`settings`.

### Focus tab added to TL role
`src/lib/roles.ts` updated to include `'focus'` in TL role tabs array.

### Campanii — new endpoint + redesigned UI

**New endpoint:** `GET /api/campaigns/promotions-incentives`
- Params: `start_date`, `end_date`, `zone`
- Returns: `promo_title`, `promo_description`, `promo_qty`, `promo_total_qty`, `promo_impact` (20% × sales), `incentive_title`, `incentive_description`, `incentive_qty`, `incentive_value` (qty × reward_per_unit), `top_stores[]`, `top_agents[]`

**Tables used:**
- Promo data: `reporting_item_day` (has `positive_quantity`, `net_quantity`, `total_sales` — NO `total_quantity` column)
- Incentive data: `reporting_item_month`
- `reporting_item_day` has NO `category` column — category filters use `reporting_category_month` instead

**Important column notes:**
- `reporting_item_day`: `positive_quantity`, `net_quantity` (= positive - return), `total_sales` — NO `total_quantity`
- `reporting_focus_item_month`, `reporting_agent_month`: have `total_quantity`
- `reporting_item_day`: NO `category` column (unlike `reporting_category_month`)

**Bug fixes during implementation:**
- `total_quantity` → `net_quantity` in promo queries (reporting_item_day doesn't have total_quantity)
- `agg.category` removed from category queries (column doesn't exist in reporting_item_day)
- Date params must be Python `date` objects, not strings (asyncpg binding error)
- Category subquery param positions: site_code pos = 4 + zona_count (dynamic, not hardcoded $4)
- `IncentiveTopAgent` uses `agent_name` (not `agent`), `PromoTopStore` uses `store_name` (not `site_code`+`locatie` separate)

**Frontend redesign (`Campaigns.tsx`):**
- Header card ("Campanii in curs") with month
- **Card Promotii**: title, description, qty (big number), progress bar (qty/total_qty), impact (20% × sales), embedded Top 10 Magazine table
- **Card Incentive**: title, description, qty (big number), incentive value (qty × 5 RON), embedded Top 10 Agenti table
- Tables embedded inside each card, amber/indigo alternating row styling

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
