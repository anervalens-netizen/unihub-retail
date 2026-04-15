# Graph Report - .  (2026-04-15)

## Corpus Check
- Large corpus: 524 files · ~2,221,490 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder, or use --no-semantic to run AST-only.

## Summary
- 851 nodes · 1620 edges · 79 communities detected
- Extraction: 63% EXTRACTED · 37% INFERRED · 0% AMBIGUOUS · INFERRED: 603 edges (avg confidence: 0.75)
- Token cost: 18,500 input · 4,200 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Admin & User Management|Admin & User Management]]
- [[_COMMUNITY_Core Data Models & API|Core Data Models & API]]
- [[_COMMUNITY_Backend Infrastructure & Scripts|Backend Infrastructure & Scripts]]
- [[_COMMUNITY_CRM & HR Frontend API|CRM & HR Frontend API]]
- [[_COMMUNITY_Campaigns & Dashboard Filters|Campaigns & Dashboard Filters]]
- [[_COMMUNITY_App Auth & Navigation|App Auth & Navigation]]
- [[_COMMUNITY_Dashboard Specials & Promotions|Dashboard Specials & Promotions]]
- [[_COMMUNITY_Agent Analytics & UniAI Reports|Agent Analytics & UniAI Reports]]
- [[_COMMUNITY_UniAI WebSocket Layer|UniAI WebSocket Layer]]
- [[_COMMUNITY_CRM Frontend Component|CRM Frontend Component]]
- [[_COMMUNITY_AI Chat UI|AI Chat UI]]
- [[_COMMUNITY_Tasks Backend|Tasks Backend]]
- [[_COMMUNITY_Admin Users & Imports|Admin Users & Imports]]
- [[_COMMUNITY_AI Sessions API|AI Sessions API]]
- [[_COMMUNITY_ASM Performance Subtab|ASM Performance Subtab]]
- [[_COMMUNITY_Documentation & Data Architecture|Documentation & Data Architecture]]
- [[_COMMUNITY_Salary Filter Tests|Salary Filter Tests]]
- [[_COMMUNITY_Agents Frontend API|Agents Frontend API]]
- [[_COMMUNITY_Module Documentation|Module Documentation]]
- [[_COMMUNITY_Frontend TypeScript Types|Frontend TypeScript Types]]
- [[_COMMUNITY_Salary Frontend API|Salary Frontend API]]
- [[_COMMUNITY_Campaign Test Models|Campaign Test Models]]
- [[_COMMUNITY_Campaigns Redesign|Campaigns Redesign]]
- [[_COMMUNITY_Visits Report API|Visits Report API]]
- [[_COMMUNITY_Salary Drawer Component|Salary Drawer Component]]
- [[_COMMUNITY_Error Boundary|Error Boundary]]
- [[_COMMUNITY_Agent Plan & Specs|Agent Plan & Specs]]
- [[_COMMUNITY_StoreStats Historic Breakdown|StoreStats Historic Breakdown]]
- [[_COMMUNITY_SalariiSubtab Component|SalariiSubtab Component]]
- [[_COMMUNITY_Frontend View Cache|Frontend View Cache]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]

## God Nodes (most connected - your core abstractions)
1. `get_pool()` - 79 edges
2. `scoped_clauses()` - 22 edges
3. `Returns (multipliers, achievements) keyed by site_code.     multipliers: {site_c` - 20 edges
4. `Attach promo_qty and incentive_qty to each store stats row.` - 20 edges
5. `Returns all dashboard data except history in a single response.      Runs agents` - 20 edges
6. `Internal helper to build special cards data without HTTP dependencies.` - 20 edges
7. `normalize_filter()` - 17 edges
8. `Design: Tab Management (HR + CRM + Tasks) (2026-04-09)` - 17 edges
9. `parse_promotion_definition()` - 15 edges
10. `_build_scoped_params()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Rationale: schema reapplied only when hash changes` --semantically_similar_to--> `Rationale: hash-based schema reapplication for fast/safe startup`  [INFERRED] [semantically similar]
  LOCAL_SETUP.md → README.md
- `CLAUDE.md - Project guide for Claude sessions` --conceptually_related_to--> `README.md - UniHub Project Overview`  [INFERRED]
  CLAUDE.md → README.md
- `Rationale: verify DB->API->Frontend after backend changes` --rationale_for--> `Import flow (Excel -> snapshot -> raw -> reporting -> completed)`  [INFERRED]
  CLAUDE.md → README.md
- `Import flow (Excel -> snapshot -> raw -> reporting -> completed)` --shares_data_with--> `pandas - Excel data processing`  [INFERRED]
  README.md → backend/requirements.txt
- `Import flow (Excel -> snapshot -> raw -> reporting -> completed)` --shares_data_with--> `openpyxl - .xlsx reader`  [INFERRED]
  README.md → backend/requirements.txt

## Hyperedges (group relationships)
- **UniHub three-tier data architecture** — data_layer_raw, data_layer_reporting, data_layer_historical [EXTRACTED 0.95]
- **Agents tab redesign coordination (spec + plan tasks)** — spec_agents_chart_flux, plan_agents_task1_models, plan_agents_task3_query_ctes, plan_agents_task5_frontend [EXTRACTED 0.90]
- **UniHub PWA branding asset set** — favicon_svg, pwa_192_svg, pwa_512_svg, unihub_brand_identity [EXTRACTED 0.95]
- **CRM Store Score Calculation Pipeline** — backend_crm_get_forecast_factor, backend_crm_calculate_scores, backend_crm_upsert_scores, db_store_scores, db_reporting_agent_month, db_visits_sqlite [EXTRACTED 1.00]
- **ASM Performance Combined Data (PG + SQLite)** — backend_hr_get_asm_performance, backend_hr_get_asm_performance_history, db_reporting_agent_month, db_store_targets, db_stores, db_visits_sqlite, backend_crm_get_forecast_factor [EXTRACTED 1.00]
- **Management Tab Subtabs** — components_asmsubtab, components_taskssubtab, components_hrsubtab, components_crmsubtab [INFERRED 0.85]
- **CRM Alert → Task Creation Flow** — components_crmsubtab, apicrm_fetchalerts, apitasks_createtask, backend_crm_get_store_alerts, backend_router_crm [EXTRACTED 1.00]
- **HR Leave Request Lifecycle** — components_hrsubtab, apihr_fetchleaverequests, apihr_createleaverequest, apihr_updateleavestatus, backend_hr_create_leave_request, backend_hr_update_leave_status, backend_hr_list_leave_requests, db_leave_requests [EXTRACTED 1.00]
- **Weakest Agents Analysis Pipeline (query → data → chart)** — query_weakest_agents_script, weakest_agents_data_json, generate_pie_charts_script, weakest_agents_pie_charts_image [EXTRACTED 1.00]
- **Management Tab Feature (spec + plan + frontend shell + 4 subtabs)** — spec_management_tab_design, plan_management_tab, management_tsx, asm_subtab_tsx, crm_subtab_tsx, tasks_subtab_tsx, hr_subtab_tsx [EXTRACTED 1.00]
- **Management Tab Backend (3 routers + 4 tables + schema)** — tasks_router, hr_router, crm_router, schema_v2_sql, table_tasks, table_leave_requests, table_attendance_records, table_store_scores [EXTRACTED 1.00]
- **Incentive Cards Redesign Feature (spec + plan + campaigns components)** — spec_incentive_cards_redesign, plan_incentive_cards_redesign, campaigns_tsx, campaigns_router, backend_models_incentivetopagent, backend_models_promotostore, sortable_table_component [EXTRACTED 1.00]
- **Istoric Breakdowns Feature (spec + plan + dashboard + StoreStats model)** — spec_istoric_breakdowns, plan_istoric_breakdowns, dashboard_tsx, backend_models_storestats [EXTRACTED 1.00]
- **Andrei Stancu Regional Team (RSM + 5 ASMs)** — andrei_stancu_rsm, asm_mihai_condorateanu, asm_aldea_valentin, asm_andreea_vladascau, asm_sergiu_tiron, asm_sorin_matei [EXTRACTED 1.00]
- **UniAI Workspace Analyses (agents Q1 + salaries ASM)** — analiza_agenti_q1_2026, analiza_salarii_asm, uniai_memory [INFERRED 0.85]

## Communities

### Community 0 - "Admin & User Management"
Cohesion: 0.04
Nodes (79): create_focus_product(), create_user(), delete_focus_product(), delete_user(), list_focus_products(), list_users(), update_tl_assignments(), update_user() (+71 more)

### Community 1 - "Core Data Models & API"
Cohesion: 0.07
Nodes (81): BaseModel, get_campaign_overview(), Returns all dashboard data except history in a single response.      Runs agents, Internal helper to build special cards data without HTTP dependencies., Attach promo_qty and incentive_qty to each store stats row., Returns (multipliers, achievements) keyed by site_code.     multipliers: {site_c, AdminUserCreate, AdminUserUpdate (+73 more)

### Community 2 - "Backend Infrastructure & Scripts"
Cohesion: 0.05
Nodes (62): ensure_core_users(), ensure_tl_users(), ensure_tl_users_and_assignments(), get_core_user_bootstrap_status(), get_default_core_credentials(), reset_default_core_users(), should_reset_default_users_on_boot(), should_sync_tl_assignments_on_boot() (+54 more)

### Community 3 - "CRM & HR Frontend API"
Cohesion: 0.05
Nodes (56): fetchAlerts(), fetchScores(), recalculateScores(), StoreAlert (interface), StoreScore (interface), AsmHistoryPoint (interface), AsmPerformance (interface), AssignableUser (interface) (+48 more)

### Community 4 - "Campaigns & Dashboard Filters"
Cohesion: 0.1
Nodes (44): _campaign_clauses(), get_promotions_incentives(), _build_scoped_params(), _enrich_store_stats_with_campaign(), _fetch_agent_stats_rows(), _fetch_asm_stats(), _fetch_brand_mix(), _fetch_category_mix() (+36 more)

### Community 5 - "App Auth & Navigation"
Cohesion: 0.08
Nodes (25): bootstrap(), handleAuthenticated(), handleLogout(), getCurrentUser(), login(), logout(), me(), create_access_token() (+17 more)

### Community 6 - "Dashboard Specials & Promotions"
Cohesion: 0.1
Nodes (33): build_incentive_card(), build_promotion_card(), format_currency(), format_int(), incentive_multiplier(), load_incentive_codes(), load_incentive_reward_map(), month_overlaps_period() (+25 more)

### Community 7 - "Agent Analytics & UniAI Reports"
Cohesion: 0.11
Nodes (34): Agent BULAIA (weakest, Mihai Condorateanu zone 2026-04), Agent OLTEANUR (weakest, Mihai Condorateanu zone 2026-04), Agent SERBANGEO (weakest, Mihai Condorateanu zone 2026-04), Analiză Agenți Regiunea Andrei Stancu Q1 2026, Analiză Salarii & Efective Regiunea Andrei Stancu (Ian 2025 - Feb 2026), Andrei Stancu (RSM — Regional Sales Manager), ASM Aldea Valentin, ASM Andreea Vladascau (+26 more)

### Community 8 - "UniAI WebSocket Layer"
Cohesion: 0.09
Nodes (22): AiWebSocket, resolveWsUrl(), build_site_code_map(), fetch_q4_2023(), load_summary(), main(), Returnează totalurile Sep-Dec 2023 din sales_transactions per (site_code, firma), Returnează: {(firma, locatie_upper): {2022: {value, qty}, 2023: {value, qty}}} (+14 more)

### Community 9 - "CRM Frontend Component"
Cohesion: 0.1
Nodes (22): fetchAlerts(), fetchScores(), recalculateScores(), handleCreateTaskFromAlert(), handleRecalculate(), load(), defaultAppFilters(), load() (+14 more)

### Community 10 - "AI Chat UI"
Cohesion: 0.11
Nodes (9): handleActivateSession(), handleDeleteSession(), handleKeyDown(), handleNewSession(), normalizeMessages(), sendMessage(), activateAiSession(), createAiSession() (+1 more)

### Community 11 - "Tasks Backend"
Cohesion: 0.14
Nodes (19): create_task(), delete_task(), get_my_pending_count(), get_my_tasks(), get_tasks(), list_tasks(), patch_my_task(), patch_task() (+11 more)

### Community 12 - "Admin Users & Imports"
Cohesion: 0.15
Nodes (12): createAdminUser(), deleteAdminUser(), updateAdminUser(), updateTlAssignments(), uploadSalesFile(), handleCancelCreate(), handleCancelEdit(), handleCreateOrUpdateUser() (+4 more)

### Community 13 - "AI Sessions API"
Cohesion: 0.19
Nodes (11): ai_health(), ai_websocket(), _bridge_healthy(), AI Router — WebSocket + HTTP proxy to Hermes Bridge (localhost:7777).  Endpoints, Check if the AI bridge is online., Validate JWT token for WebSocket (no Bearer header available in WS)., WebSocket chat endpoint.      Protocol:       Client → Server: {"type": "message, _validate_ws_token() (+3 more)

### Community 14 - "ASM Performance Subtab"
Cohesion: 0.13
Nodes (4): handleExpand(), load(), fetchAsmHistory(), fetchAsmPerformance()

### Community 15 - "Documentation & Data Architecture"
Cohesion: 0.15
Nodes (16): backend/requirements.txt - runtime deps, Rationale: verify DB->API->Frontend after backend changes, Rationale: do not query sales_transactions for reporting (use aggregates), VIEW compatibility for Platforma-Mobiup, Historical data layer (pre-2023-Sep), Raw operational data layer, Aggregated reporting layer, asyncpg - async PostgreSQL driver (+8 more)

### Community 16 - "Salary Filter Tests"
Cohesion: 0.22
Nodes (11): _get_token(), GET /salarii/evolution with regional+asm returns 200 (list response)., GET /salarii/overview with regional+asm returns 200 with correct shape., GET /salarii/agents/summary with regional+asm returns 200 with items+total shape, GET /salarii/summary with regional+asm returns 200 with month+items shape., GET /salarii/trend with regional+asm returns 200 (list response)., test_salarii_agents_summary_accepts_regional_asm(), test_salarii_evolution_accepts_regional_asm() (+3 more)

### Community 17 - "Agents Frontend API"
Cohesion: 0.25
Nodes (3): fetchAgentHistory(), fetchAgentProfile(), load()

### Community 18 - "Module Documentation"
Cohesion: 0.22
Nodes (9): CLAUDE.md - Project guide for Claude sessions, Gotcha: AI tab uses overflow-hidden to prevent mobile address bar jump, LOCAL_SETUP.md - UniHub Local Development Setup, Module Focus - campaigns and focus products, Module Hub - sales analytics, Module Setari - admin zone, Module UniAI - Hermes-powered analytics assistant, Module Fisa de vizita - store visits with photos (+1 more)

### Community 19 - "Frontend TypeScript Types"
Cohesion: 0.33
Nodes (9): AgentStat (type), AsmStat (type), AuthUser (type), DashboardAllResponse (type), DashboardSummary (type), RegionalStat (type), StoreStat (type), App (Root Component) (+1 more)

### Community 20 - "Salary Frontend API"
Cohesion: 0.25
Nodes (0): 

### Community 21 - "Campaign Test Models"
Cohesion: 0.39
Nodes (7): IncentiveTopAgent, PromoTopStore, Unit tests for campaigns models., test_incentive_top_agent_full_fields(), test_incentive_top_agent_no_target(), test_promo_top_store_firma_default_empty(), test_promo_top_store_has_firma()

### Community 22 - "Campaigns Redesign"
Cohesion: 0.52
Nodes (7): IncentiveTopAgent Pydantic Model (backend/models.py), PromoTopStore Pydantic Model (backend/models.py), backend/routers/campaigns.py, Campaigns.tsx (Frontend Component), Incentive Cards Redesign Implementation Plan (2026-04-06), SortableTable (local React component in Campaigns.tsx), Spec: Incentive Cards Redesign — Top Agenti + Top Magazine (2026-04-06)

### Community 23 - "Visits Report API"
Cohesion: 0.47
Nodes (3): buildParams(), getVisitsReport(), getVisitsTree()

### Community 24 - "Salary Drawer Component"
Cohesion: 0.33
Nodes (0): 

### Community 25 - "Error Boundary"
Cohesion: 0.33
Nodes (1): ErrorBoundary

### Community 26 - "Agent Plan & Specs"
Cohesion: 0.33
Nodes (6): Rationale: declare Pydantic fields explicitly to avoid silent drop, Task 1: Add has_changes + modified_stores_count to backend models, Task 3: Extend stores-coverage query with curr_agents/prev_agents CTEs, Rationale: keep uncovered_stores_count for backward compatibility, Concept: 'Cu Modificari' = stores where agent set changed vs prev month, Rationale: Active and Cu Modificari are orthogonal counts (overlap intentional)

### Community 27 - "StoreStats Historic Breakdown"
Cohesion: 0.47
Nodes (6): StoreStats Pydantic Model (backend/models.py), Dashboard.tsx (Frontend Component), Istoric Breakdowns + Incentive Magazine Implementation Plan (2026-04-06), Rationale: History tables need no new backend routes (data already returned), Rationale: StoreStats incentive_qty silently dropped by Pydantic, Spec: Tabele Breakdowns în Istoric + Incentive la Magazine (2026-04-06)

### Community 28 - "SalariiSubtab Component"
Cohesion: 0.4
Nodes (0): 

### Community 29 - "Frontend View Cache"
Cohesion: 0.5
Nodes (0): 

### Community 30 - "Community 30"
Cohesion: 0.5
Nodes (0): 

### Community 31 - "Community 31"
Cohesion: 0.5
Nodes (0): 

### Community 32 - "Community 32"
Cohesion: 0.5
Nodes (0): 

### Community 33 - "Community 33"
Cohesion: 0.5
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 0.5
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 0.5
Nodes (2): Reset the asyncpg pool before each test so async tests get a fresh pool     boun, reset_db_pool()

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (3): main(), request_delete(), request_json()

### Community 37 - "Community 37"
Cohesion: 0.83
Nodes (4): Favicon - Blue rounded square with white 'U', PWA 192x192 icon - Blue rounded square with 'U', PWA 512x512 icon - Blue rounded square with 'U', UniHub brand identity (blue #1e40af + white U glyph)

### Community 38 - "Community 38"
Cohesion: 0.67
Nodes (0): 

### Community 39 - "Community 39"
Cohesion: 0.67
Nodes (3): Filter scoping rules (Hub/Focus shared vs Agenti independent), Plan: Salarii global filter integration implementation, Spec: Salarii tab - Global filter integration (2026-04-10)

### Community 40 - "Community 40"
Cohesion: 0.67
Nodes (3): Rationale: case-insensitive firma comparison for salary records, Task 2: Update /overview and /evolution endpoints with regional/asm, Common JOIN with stores when regional/asm provided

### Community 41 - "Community 41"
Cohesion: 0.67
Nodes (3): PostgreSQL local setup steps, Rationale: schema reapplied only when hash changes, Rationale: hash-based schema reapplication for fast/safe startup

### Community 42 - "Community 42"
Cohesion: 0.67
Nodes (3): Task 5: Frontend - chart filter, renamed labels, clickable sections, Requirement: chart Miscare Personal limited to 2025-01+, Requirement: Clickable Active/Modified/Inactive boxes (one open at a time)

### Community 43 - "Community 43"
Cohesion: 0.67
Nodes (3): get_pool() — asyncpg connection pool singleton, Graph Report (2026-04-15, 730 nodes 1420 edges), Graphify Query: Why does get_pool() connect so many communities?

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (0): 

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (0): 

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (0): 

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (0): 

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (0): 

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (0): 

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (2): backend/requirements-dev.txt - test deps (pytest), pytest - test framework

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (2): Task 1: Integration tests for new salarii params, 5 Salarii cards filtered by global filter

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (2): Plan: Agents tab - Chart range and Flux redesign implementation, Spec: Agents tab - Chart range and Magazine Flux redesign (2026-04-10)

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (2): Remove internal firma/store selects from Agenti card, Rationale: keep /salarii/stores backend endpoint (no breaking change)

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (0): 

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (0): 

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (0): 

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (0): 

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (0): 

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (0): 

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (0): 

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (0): 

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): .env configuration

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): Rationale: Why dashboards read aggregated reporting tables

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): Reference to seed.py script

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): Reference to import_incentive_campaign.py

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): Daily 02:00 backup pipeline (PostgreSQL + visits SQLite)

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): FilterOptions (type)

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): CampaignSnapshot (type)

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): ImportResponse (type)

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): TaskCreate (interface)

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): TaskUpdate (interface)

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **100 isolated node(s):** `Per-agent stats for a specific store — used for Card D auto-population.`, `GET /salarii/overview with regional+asm returns 200 with correct shape.`, `GET /salarii/agents/summary with regional+asm returns 200 with items+total shape`, `GET /salarii/summary with regional+asm returns 200 with month+items shape.`, `GET /salarii/trend with regional+asm returns 200 (list response).` (+95 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 44`** (2 nodes): `manualChunks()`, `vite.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (2 nodes): `buildScopedMonthQuery()`, `filterQueries.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (2 nodes): `utils.ts`, `cn()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (2 nodes): `resolveApiBaseUrl()`, `client.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (2 nodes): `stores.ts`, `getStores()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (2 nodes): `formatCurrency()`, `SalaryAreaChart.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (2 nodes): `setTab()`, `Management.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (2 nodes): `backend/requirements-dev.txt - test deps (pytest)`, `pytest - test framework`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (2 nodes): `Task 1: Integration tests for new salarii params`, `5 Salarii cards filtered by global filter`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (2 nodes): `Plan: Agents tab - Chart range and Flux redesign implementation`, `Spec: Agents tab - Chart range and Magazine Flux redesign (2026-04-10)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (2 nodes): `Remove internal firma/store selects from Agenti card`, `Rationale: keep /salarii/stores backend endpoint (no breaking change)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `vite-env.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `tabs.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `types.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `Campaigns.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `Dashboard.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `DesktopTopBar.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `HRSubtab.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `DesktopSidebar.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `ThemeSwitcher.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `generate_pie_charts.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `.env configuration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `Rationale: Why dashboards read aggregated reporting tables`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `Reference to seed.py script`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `Reference to import_incentive_campaign.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `Daily 02:00 backup pipeline (PostgreSQL + visits SQLite)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `FilterOptions (type)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `CampaignSnapshot (type)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `ImportResponse (type)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `TaskCreate (interface)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `TaskUpdate (interface)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `fetchMyPendingCount()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_pool()` connect `Admin & User Management` to `Core Data Models & API`, `Backend Infrastructure & Scripts`, `CRM & HR Frontend API`, `Campaigns & Dashboard Filters`, `App Auth & Navigation`, `UniAI WebSocket Layer`, `Tasks Backend`, `AI Sessions API`?**
  _High betweenness centrality (0.194) - this node is a cross-community bridge._
- **Why does `test_hub_specials_json_exists()` connect `CRM Frontend Component` to `Campaigns & Dashboard Filters`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Why does `AiWebSocket` connect `UniAI WebSocket Layer` to `AI Chat UI`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 76 inferred relationships involving `get_pool()` (e.g. with `get_current_user()` and `ensure_default_users()`) actually correct?**
  _`get_pool()` has 76 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `scoped_clauses()` (e.g. with `test_dashboard_scoped_clauses_builds_agent_filter()` and `build_scope_filter()`) actually correct?**
  _`scoped_clauses()` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Returns (multipliers, achievements) keyed by site_code.     multipliers: {site_c` (e.g. with `AgentStats` and `AsmStats`) actually correct?**
  _`Returns (multipliers, achievements) keyed by site_code.     multipliers: {site_c` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Attach promo_qty and incentive_qty to each store stats row.` (e.g. with `AgentStats` and `AsmStats`) actually correct?**
  _`Attach promo_qty and incentive_qty to each store stats row.` has 19 INFERRED edges - model-reasoned connections that need verification._