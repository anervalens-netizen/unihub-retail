# Graph Report - .  (2026-04-15)

## Corpus Check
- 113 files · ~79,841 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 730 nodes · 1420 edges · 69 communities detected
- Extraction: 59% EXTRACTED · 41% INFERRED · 0% AMBIGUOUS · INFERRED: 583 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Pydantic Models & Tests|Pydantic Models & Tests]]
- [[_COMMUNITY_Admin CRUD & Agents API|Admin CRUD & Agents API]]
- [[_COMMUNITY_Dashboard Backend Logic|Dashboard Backend Logic]]
- [[_COMMUNITY_Auth & Bootstrap|Auth & Bootstrap]]
- [[_COMMUNITY_Historical Import Pipeline|Historical Import Pipeline]]
- [[_COMMUNITY_Incentive & Promo Cards|Incentive & Promo Cards]]
- [[_COMMUNITY_AI WebSocket & Backend Imports|AI WebSocket & Backend Imports]]
- [[_COMMUNITY_Auth Flow (Frontend + JWT)|Auth Flow (Frontend + JWT)]]
- [[_COMMUNITY_CRM Alerts & Scores|CRM Alerts & Scores]]
- [[_COMMUNITY_AI Chat UI|AI Chat UI]]
- [[_COMMUNITY_Tasks Module|Tasks Module]]
- [[_COMMUNITY_AI Bridge Router|AI Bridge Router]]
- [[_COMMUNITY_Admin User UI|Admin User UI]]
- [[_COMMUNITY_Backend Deps & Rationale|Backend Deps & Rationale]]
- [[_COMMUNITY_CRM Scoring Logic|CRM Scoring Logic]]
- [[_COMMUNITY_Salarii Filter Tests|Salarii Filter Tests]]
- [[_COMMUNITY_HR  Leave Requests|HR / Leave Requests]]
- [[_COMMUNITY_Agents API Frontend|Agents API Frontend]]
- [[_COMMUNITY_Project Overview Docs|Project Overview Docs]]
- [[_COMMUNITY_Store Coverage Tests|Store Coverage Tests]]
- [[_COMMUNITY_Campaign Model Tests|Campaign Model Tests]]
- [[_COMMUNITY_Salarii API Frontend|Salarii API Frontend]]
- [[_COMMUNITY_Visits Report Frontend|Visits Report Frontend]]
- [[_COMMUNITY_Salary Drawer UI|Salary Drawer UI]]
- [[_COMMUNITY_Error Boundary|Error Boundary]]
- [[_COMMUNITY_Stores Coverage Spec|Stores Coverage Spec]]
- [[_COMMUNITY_Salarii Subtab Helpers|Salarii Subtab Helpers]]
- [[_COMMUNITY_conftest.py|conftest.py]]
- [[_COMMUNITY_smoke_api.py|smoke_api.py]]
- [[_COMMUNITY_getDashboardAll|getDashboardAll]]
- [[_COMMUNITY_getCampaignSnapshot|getCampaignSnapshot]]
- [[_COMMUNITY_VisiteSubtab.tsx|VisiteSubtab.tsx]]
- [[_COMMUNITY_viewCache.ts|viewCache.ts]]
- [[_COMMUNITY_canAccessTab|canAccessTab]]
- [[_COMMUNITY_formatCurrency|formatCurrency]]
- [[_COMMUNITY_Favicon|Favicon]]
- [[_COMMUNITY_Misc formatCurrency|Misc: formatCurrency]]
- [[_COMMUNITY_Misc PostgreSQL local setup steps|Misc: PostgreSQL local setup steps]]
- [[_COMMUNITY_Misc Filter scoping rules (HubFocus shared v|Misc: Filter scoping rules (Hub/Focus shared v]]
- [[_COMMUNITY_Misc Rationale case-insensitive firma compar|Misc: Rationale: case-insensitive firma compar]]
- [[_COMMUNITY_Misc Task 5 Frontend|Misc: Task 5: Frontend]]
- [[_COMMUNITY_Misc manualChunks|Misc: manualChunks]]
- [[_COMMUNITY_Misc stores.ts|Misc: stores.ts]]
- [[_COMMUNITY_Misc resolveApiBaseUrl|Misc: resolveApiBaseUrl]]
- [[_COMMUNITY_Misc setTab|Misc: setTab]]
- [[_COMMUNITY_Misc formatPercent|Misc: formatPercent]]
- [[_COMMUNITY_Misc formatCurrency|Misc: formatCurrency]]
- [[_COMMUNITY_Misc buildScopedMonthQuery|Misc: buildScopedMonthQuery]]
- [[_COMMUNITY_Misc utils.ts|Misc: utils.ts]]
- [[_COMMUNITY_Misc Task 1 Integration tests for new salari|Misc: Task 1: Integration tests for new salari]]
- [[_COMMUNITY_Misc Remove internal firmastore selects from|Misc: Remove internal firma/store selects from]]
- [[_COMMUNITY_Misc Plan Agents tab|Misc: Plan: Agents tab]]
- [[_COMMUNITY_Misc backendrequirements-dev.txt|Misc: backend/requirements-dev.txt]]
- [[_COMMUNITY_Misc __init__.py|Misc: __init__.py]]
- [[_COMMUNITY_Misc __init__.py|Misc: __init__.py]]
- [[_COMMUNITY_Misc __init__.py|Misc: __init__.py]]
- [[_COMMUNITY_Misc vite-env.d.ts|Misc: vite-env.d.ts]]
- [[_COMMUNITY_Misc types.ts|Misc: types.ts]]
- [[_COMMUNITY_Misc DesktopSidebar.tsx|Misc: DesktopSidebar.tsx]]
- [[_COMMUNITY_Misc DesktopTopBar.tsx|Misc: DesktopTopBar.tsx]]
- [[_COMMUNITY_Misc HRSubtab.tsx|Misc: HRSubtab.tsx]]
- [[_COMMUNITY_Misc Campaigns.tsx|Misc: Campaigns.tsx]]
- [[_COMMUNITY_Misc ThemeSwitcher.tsx|Misc: ThemeSwitcher.tsx]]
- [[_COMMUNITY_Misc tabs.ts|Misc: tabs.ts]]
- [[_COMMUNITY_Misc .env configuration|Misc: .env configuration]]
- [[_COMMUNITY_Misc Rationale Why dashboards read aggregate|Misc: Rationale: Why dashboards read aggregate]]
- [[_COMMUNITY_Misc Reference to seed.py script|Misc: Reference to seed.py script]]
- [[_COMMUNITY_Misc Reference to import_incentive_campaign.p|Misc: Reference to import_incentive_campaign.p]]
- [[_COMMUNITY_Misc Daily 0200 backup pipeline (PostgreSQL|Misc: Daily 02:00 backup pipeline (PostgreSQL ]]

## God Nodes (most connected - your core abstractions)
1. `get_pool()` - 79 edges
2. `scoped_clauses()` - 22 edges
3. `Returns (multipliers, achievements) keyed by site_code.     multipliers: {site_c` - 20 edges
4. `Attach promo_qty and incentive_qty to each store stats row.` - 20 edges
5. `Returns all dashboard data except history in a single response.      Runs agents` - 20 edges
6. `Internal helper to build special cards data without HTTP dependencies.` - 20 edges
7. `normalize_filter()` - 17 edges
8. `parse_promotion_definition()` - 15 edges
9. `main()` - 15 edges
10. `_build_scoped_params()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Rationale: schema reapplied only when hash changes` --semantically_similar_to--> `Rationale: hash-based schema reapplication for fast/safe startup`  [INFERRED] [semantically similar]
  LOCAL_SETUP.md → README.md
- `login()` --calls--> `LoginResponse`  [INFERRED]
  src/api/auth.ts → backend/models.py
- `login()` --calls--> `get_pool()`  [INFERRED]
  src/api/auth.ts → backend/db/connection.py
- `LOCAL_SETUP.md - UniHub Local Development Setup` --conceptually_related_to--> `README.md - UniHub Project Overview`  [INFERRED]
  LOCAL_SETUP.md → README.md
- `CLAUDE.md - Project guide for Claude sessions` --conceptually_related_to--> `README.md - UniHub Project Overview`  [INFERRED]
  CLAUDE.md → README.md

## Hyperedges (group relationships)
- **UniHub three-tier data architecture** — data_layer_raw, data_layer_reporting, data_layer_historical [EXTRACTED 0.95]
- **Agents tab redesign coordination (spec + plan tasks)** — spec_agents_chart_flux, plan_agents_task1_models, plan_agents_task3_query_ctes, plan_agents_task5_frontend [EXTRACTED 0.90]
- **UniHub PWA branding asset set** — favicon_svg, pwa_192_svg, pwa_512_svg, unihub_brand_identity [EXTRACTED 0.95]

## Communities

### Community 0 - "Pydantic Models & Tests"
Cohesion: 0.06
Nodes (83): BaseModel, get_dashboard_all(), get_history_by_year(), get_special_cards(), Returns all dashboard data except history in a single response.      Runs agents, Internal helper to build special cards data without HTTP dependencies., Attach promo_qty and incentive_qty to each store stats row., Returns (multipliers, achievements) keyed by site_code.     multipliers: {site_c (+75 more)

### Community 1 - "Admin CRUD & Agents API"
Cohesion: 0.05
Nodes (68): create_focus_product(), create_user(), delete_focus_product(), delete_user(), list_focus_products(), list_users(), update_tl_assignments(), update_user() (+60 more)

### Community 2 - "Dashboard Backend Logic"
Cohesion: 0.11
Nodes (41): get_promotions_incentives(), _build_scoped_params(), _enrich_store_stats_with_campaign(), _fetch_agent_stats_rows(), _fetch_asm_stats(), _fetch_brand_mix(), _fetch_category_mix(), _fetch_focus_subcategory_mix() (+33 more)

### Community 3 - "Auth & Bootstrap"
Cohesion: 0.09
Nodes (30): hash_password(), ensure_core_users(), ensure_tl_users(), ensure_tl_users_and_assignments(), get_core_user_bootstrap_status(), get_default_core_credentials(), reset_default_core_users(), should_reset_default_users_on_boot() (+22 more)

### Community 4 - "Historical Import Pipeline"
Cohesion: 0.11
Nodes (33): collect_files(), import_one(), load_historical_df(), main(), Importă un fișier istoric.     Returnează (import_month, rows_imported) sau (Non, Citește un fișier vechi (fără Agent/Categorie/SubCategorie) și adaugă coloanele, Colectează fișierele din 2023/ și 2024/, sortate cronologic după folder + nume., detect_month() (+25 more)

### Community 5 - "Incentive & Promo Cards"
Cohesion: 0.1
Nodes (33): build_incentive_card(), build_promotion_card(), format_currency(), format_int(), incentive_multiplier(), load_incentive_codes(), load_incentive_reward_map(), month_overlaps_period() (+25 more)

### Community 6 - "AI WebSocket & Backend Imports"
Cohesion: 0.09
Nodes (27): AiWebSocket, resolveWsUrl(), _query_visits_by_store(), Returnează {site_code: {nr_vizite, avg_completion}} pentru luna dată.     Execuț, _query_visits_by_asm(), _query_visits_history(), Execuție sincronă — apelată din run_in_executor., Execuție sincronă — istoricul vizitelor per ASM. (+19 more)

### Community 7 - "Auth Flow (Frontend + JWT)"
Cohesion: 0.07
Nodes (24): bootstrap(), handleAuthenticated(), handleLogout(), getCurrentUser(), login(), logout(), me(), create_access_token() (+16 more)

### Community 8 - "CRM Alerts & Scores"
Cohesion: 0.1
Nodes (22): fetchAlerts(), fetchScores(), recalculateScores(), handleCreateTaskFromAlert(), handleRecalculate(), load(), defaultAppFilters(), load() (+14 more)

### Community 9 - "AI Chat UI"
Cohesion: 0.11
Nodes (9): handleActivateSession(), handleDeleteSession(), handleKeyDown(), handleNewSession(), normalizeMessages(), sendMessage(), activateAiSession(), createAiSession() (+1 more)

### Community 10 - "Tasks Module"
Cohesion: 0.14
Nodes (19): create_task(), delete_task(), get_my_pending_count(), get_my_tasks(), get_tasks(), list_tasks(), patch_my_task(), patch_task() (+11 more)

### Community 11 - "AI Bridge Router"
Cohesion: 0.19
Nodes (11): ai_health(), ai_websocket(), _bridge_healthy(), AI Router — WebSocket + HTTP proxy to Hermes Bridge (localhost:7777).  Endpoints, Check if the AI bridge is online., Validate JWT token for WebSocket (no Bearer header available in WS)., WebSocket chat endpoint.      Protocol:       Client → Server: {"type": "message, _validate_ws_token() (+3 more)

### Community 12 - "Admin User UI"
Cohesion: 0.15
Nodes (12): createAdminUser(), deleteAdminUser(), updateAdminUser(), updateTlAssignments(), uploadSalesFile(), handleCancelCreate(), handleCancelEdit(), handleCreateOrUpdateUser() (+4 more)

### Community 13 - "Backend Deps & Rationale"
Cohesion: 0.15
Nodes (16): backend/requirements.txt - runtime deps, Rationale: verify DB->API->Frontend after backend changes, Rationale: do not query sales_transactions for reporting (use aggregates), VIEW compatibility for Platforma-Mobiup, Historical data layer (pre-2023-Sep), Raw operational data layer, Aggregated reporting layer, asyncpg - async PostgreSQL driver (+8 more)

### Community 14 - "CRM Scoring Logic"
Cohesion: 0.21
Nodes (12): calculate_scores_for_month(), get_alerts(), get_forecast_factor(), get_store_alerts(), Magazine cu risc: scor < 40 sau scădere previziune > 20% față de luna anterioară, Factor de extrapolare: zile_luna / ultima_zi_vanzari. 1.0 daca luna e finalizata, Calculează scorul 0-100 per magazin pentru luna dată.     Formula:       - % tar, recalculate_scores() (+4 more)

### Community 15 - "Salarii Filter Tests"
Cohesion: 0.22
Nodes (11): _get_token(), GET /salarii/evolution with regional+asm returns 200 (list response)., GET /salarii/overview with regional+asm returns 200 with correct shape., GET /salarii/agents/summary with regional+asm returns 200 with items+total shape, GET /salarii/summary with regional+asm returns 200 with month+items shape., GET /salarii/trend with regional+asm returns 200 (list response)., test_salarii_agents_summary_accepts_regional_asm(), test_salarii_evolution_accepts_regional_asm() (+3 more)

### Community 16 - "HR / Leave Requests"
Cohesion: 0.18
Nodes (4): handleExpand(), load(), fetchAsmHistory(), fetchAsmPerformance()

### Community 17 - "Agents API Frontend"
Cohesion: 0.25
Nodes (3): fetchAgentHistory(), fetchAgentProfile(), load()

### Community 18 - "Project Overview Docs"
Cohesion: 0.22
Nodes (9): CLAUDE.md - Project guide for Claude sessions, Gotcha: AI tab uses overflow-hidden to prevent mobile address bar jump, LOCAL_SETUP.md - UniHub Local Development Setup, Module Focus - campaigns and focus products, Module Hub - sales analytics, Module Setari - admin zone, Module UniAI - Hermes-powered analytics assistant, Module Fisa de vizita - store visits with photos (+1 more)

### Community 19 - "Store Coverage Tests"
Cohesion: 0.39
Nodes (6): StoreCoverageItem, StoreCoverageResponse, StoreCoverageItem and StoreCoverageResponse include has_changes and modified_sto, The /stores-coverage endpoint returns has_changes on each item and modified_stor, test_stores_coverage_endpoint_returns_has_changes(), test_stores_coverage_response_shape()

### Community 20 - "Campaign Model Tests"
Cohesion: 0.39
Nodes (7): IncentiveTopAgent, PromoTopStore, Unit tests for campaigns models., test_incentive_top_agent_full_fields(), test_incentive_top_agent_no_target(), test_promo_top_store_firma_default_empty(), test_promo_top_store_has_firma()

### Community 21 - "Salarii API Frontend"
Cohesion: 0.25
Nodes (0): 

### Community 22 - "Visits Report Frontend"
Cohesion: 0.47
Nodes (3): buildParams(), getVisitsReport(), getVisitsTree()

### Community 23 - "Salary Drawer UI"
Cohesion: 0.33
Nodes (0): 

### Community 24 - "Error Boundary"
Cohesion: 0.33
Nodes (1): ErrorBoundary

### Community 25 - "Stores Coverage Spec"
Cohesion: 0.33
Nodes (6): Rationale: declare Pydantic fields explicitly to avoid silent drop, Task 1: Add has_changes + modified_stores_count to backend models, Task 3: Extend stores-coverage query with curr_agents/prev_agents CTEs, Rationale: keep uncovered_stores_count for backward compatibility, Concept: 'Cu Modificari' = stores where agent set changed vs prev month, Rationale: Active and Cu Modificari are orthogonal counts (overlap intentional)

### Community 26 - "Salarii Subtab Helpers"
Cohesion: 0.4
Nodes (0): 

### Community 27 - "conftest.py"
Cohesion: 0.5
Nodes (2): Reset the asyncpg pool before each test so async tests get a fresh pool     boun, reset_db_pool()

### Community 28 - "smoke_api.py"
Cohesion: 1.0
Nodes (3): main(), request_delete(), request_json()

### Community 29 - "getDashboardAll"
Cohesion: 0.5
Nodes (0): 

### Community 30 - "getCampaignSnapshot"
Cohesion: 0.5
Nodes (0): 

### Community 31 - "VisiteSubtab.tsx"
Cohesion: 0.5
Nodes (0): 

### Community 32 - "viewCache.ts"
Cohesion: 0.5
Nodes (0): 

### Community 33 - "canAccessTab"
Cohesion: 0.5
Nodes (0): 

### Community 34 - "formatCurrency"
Cohesion: 0.5
Nodes (0): 

### Community 35 - "Favicon"
Cohesion: 0.83
Nodes (4): Favicon - Blue rounded square with white 'U', PWA 192x192 icon - Blue rounded square with 'U', PWA 512x512 icon - Blue rounded square with 'U', UniHub brand identity (blue #1e40af + white U glyph)

### Community 36 - "Misc: formatCurrency"
Cohesion: 0.67
Nodes (0): 

### Community 37 - "Misc: PostgreSQL local setup steps"
Cohesion: 0.67
Nodes (3): PostgreSQL local setup steps, Rationale: schema reapplied only when hash changes, Rationale: hash-based schema reapplication for fast/safe startup

### Community 38 - "Misc: Filter scoping rules (Hub/Focus shared v"
Cohesion: 0.67
Nodes (3): Filter scoping rules (Hub/Focus shared vs Agenti independent), Plan: Salarii global filter integration implementation, Spec: Salarii tab - Global filter integration (2026-04-10)

### Community 39 - "Misc: Rationale: case-insensitive firma compar"
Cohesion: 0.67
Nodes (3): Rationale: case-insensitive firma comparison for salary records, Task 2: Update /overview and /evolution endpoints with regional/asm, Common JOIN with stores when regional/asm provided

### Community 40 - "Misc: Task 5: Frontend"
Cohesion: 0.67
Nodes (3): Task 5: Frontend - chart filter, renamed labels, clickable sections, Requirement: chart Miscare Personal limited to 2025-01+, Requirement: Clickable Active/Modified/Inactive boxes (one open at a time)

### Community 41 - "Misc: manualChunks"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "Misc: stores.ts"
Cohesion: 1.0
Nodes (0): 

### Community 43 - "Misc: resolveApiBaseUrl"
Cohesion: 1.0
Nodes (0): 

### Community 44 - "Misc: setTab"
Cohesion: 1.0
Nodes (0): 

### Community 45 - "Misc: formatPercent"
Cohesion: 1.0
Nodes (0): 

### Community 46 - "Misc: formatCurrency"
Cohesion: 1.0
Nodes (0): 

### Community 47 - "Misc: buildScopedMonthQuery"
Cohesion: 1.0
Nodes (0): 

### Community 48 - "Misc: utils.ts"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "Misc: Task 1: Integration tests for new salari"
Cohesion: 1.0
Nodes (2): Task 1: Integration tests for new salarii params, 5 Salarii cards filtered by global filter

### Community 50 - "Misc: Remove internal firma/store selects from"
Cohesion: 1.0
Nodes (2): Remove internal firma/store selects from Agenti card, Rationale: keep /salarii/stores backend endpoint (no breaking change)

### Community 51 - "Misc: Plan: Agents tab"
Cohesion: 1.0
Nodes (2): Plan: Agents tab - Chart range and Flux redesign implementation, Spec: Agents tab - Chart range and Magazine Flux redesign (2026-04-10)

### Community 52 - "Misc: backend/requirements-dev.txt"
Cohesion: 1.0
Nodes (2): backend/requirements-dev.txt - test deps (pytest), pytest - test framework

### Community 53 - "Misc: __init__.py"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Misc: __init__.py"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Misc: __init__.py"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Misc: vite-env.d.ts"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Misc: types.ts"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "Misc: DesktopSidebar.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "Misc: DesktopTopBar.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "Misc: HRSubtab.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 61 - "Misc: Campaigns.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 62 - "Misc: ThemeSwitcher.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 63 - "Misc: tabs.ts"
Cohesion: 1.0
Nodes (0): 

### Community 64 - "Misc: .env configuration"
Cohesion: 1.0
Nodes (1): .env configuration

### Community 65 - "Misc: Rationale: Why dashboards read aggregate"
Cohesion: 1.0
Nodes (1): Rationale: Why dashboards read aggregated reporting tables

### Community 66 - "Misc: Reference to seed.py script"
Cohesion: 1.0
Nodes (1): Reference to seed.py script

### Community 67 - "Misc: Reference to import_incentive_campaign.p"
Cohesion: 1.0
Nodes (1): Reference to import_incentive_campaign.py

### Community 68 - "Misc: Daily 02:00 backup pipeline (PostgreSQL "
Cohesion: 1.0
Nodes (1): Daily 02:00 backup pipeline (PostgreSQL + visits SQLite)

## Knowledge Gaps
- **76 isolated node(s):** `Per-agent stats for a specific store — used for Card D auto-population.`, `Reset the asyncpg pool before each test so async tests get a fresh pool     boun`, `GET /salarii/overview with regional+asm returns 200 with correct shape.`, `GET /salarii/agents/summary with regional+asm returns 200 with items+total shape`, `GET /salarii/summary with regional+asm returns 200 with month+items shape.` (+71 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Misc: manualChunks`** (2 nodes): `manualChunks()`, `vite.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: stores.ts`** (2 nodes): `stores.ts`, `getStores()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: resolveApiBaseUrl`** (2 nodes): `resolveApiBaseUrl()`, `client.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: setTab`** (2 nodes): `setTab()`, `Management.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: formatPercent`** (2 nodes): `formatPercent()`, `Dashboard.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: formatCurrency`** (2 nodes): `formatCurrency()`, `SalaryAreaChart.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: buildScopedMonthQuery`** (2 nodes): `buildScopedMonthQuery()`, `filterQueries.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: utils.ts`** (2 nodes): `utils.ts`, `cn()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: Task 1: Integration tests for new salari`** (2 nodes): `Task 1: Integration tests for new salarii params`, `5 Salarii cards filtered by global filter`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: Remove internal firma/store selects from`** (2 nodes): `Remove internal firma/store selects from Agenti card`, `Rationale: keep /salarii/stores backend endpoint (no breaking change)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: Plan: Agents tab`** (2 nodes): `Plan: Agents tab - Chart range and Flux redesign implementation`, `Spec: Agents tab - Chart range and Magazine Flux redesign (2026-04-10)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: backend/requirements-dev.txt`** (2 nodes): `backend/requirements-dev.txt - test deps (pytest)`, `pytest - test framework`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: __init__.py`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: __init__.py`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: __init__.py`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: vite-env.d.ts`** (1 nodes): `vite-env.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: types.ts`** (1 nodes): `types.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: DesktopSidebar.tsx`** (1 nodes): `DesktopSidebar.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: DesktopTopBar.tsx`** (1 nodes): `DesktopTopBar.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: HRSubtab.tsx`** (1 nodes): `HRSubtab.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: Campaigns.tsx`** (1 nodes): `Campaigns.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: ThemeSwitcher.tsx`** (1 nodes): `ThemeSwitcher.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: tabs.ts`** (1 nodes): `tabs.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: .env configuration`** (1 nodes): `.env configuration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: Rationale: Why dashboards read aggregate`** (1 nodes): `Rationale: Why dashboards read aggregated reporting tables`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: Reference to seed.py script`** (1 nodes): `Reference to seed.py script`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: Reference to import_incentive_campaign.p`** (1 nodes): `Reference to import_incentive_campaign.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc: Daily 02:00 backup pipeline (PostgreSQL `** (1 nodes): `Daily 02:00 backup pipeline (PostgreSQL + visits SQLite)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_pool()` connect `Admin CRUD & Agents API` to `Pydantic Models & Tests`, `Dashboard Backend Logic`, `Auth & Bootstrap`, `Historical Import Pipeline`, `AI WebSocket & Backend Imports`, `Auth Flow (Frontend + JWT)`, `Tasks Module`, `AI Bridge Router`, `CRM Scoring Logic`?**
  _High betweenness centrality (0.189) - this node is a cross-community bridge._
- **Why does `test_hub_specials_json_exists()` connect `CRM Alerts & Scores` to `Dashboard Backend Logic`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `AiWebSocket` connect `AI WebSocket & Backend Imports` to `AI Chat UI`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Are the 76 inferred relationships involving `get_pool()` (e.g. with `get_current_user()` and `ensure_default_users()`) actually correct?**
  _`get_pool()` has 76 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `scoped_clauses()` (e.g. with `test_dashboard_scoped_clauses_builds_agent_filter()` and `build_scope_filter()`) actually correct?**
  _`scoped_clauses()` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Returns (multipliers, achievements) keyed by site_code.     multipliers: {site_c` (e.g. with `AgentStats` and `AsmStats`) actually correct?**
  _`Returns (multipliers, achievements) keyed by site_code.     multipliers: {site_c` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Attach promo_qty and incentive_qty to each store stats row.` (e.g. with `AgentStats` and `AsmStats`) actually correct?**
  _`Attach promo_qty and incentive_qty to each store stats row.` has 19 INFERRED edges - model-reasoned connections that need verification._