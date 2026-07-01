# UniHub Retail — Analiză de cod (Senior code review)

> Sarcină: analiză completă a codului din aplicația retail. **NU s-a modificat și NU s-a rescris codul.**
> Livrabil: lista problemelor găsite (cod duplicat, funcții prea lungi, logică greoaie) + plan de acțiune pas cu pas.
> Data: 2026-06-26
> Scope: backend FastAPI/asyncpg (`backend/`) + frontend React 19/TS/Vite (`src/`).

Metodologie: citire documentație (`README.md`, `APP_ARCHITECTURE.md`, `AGENTS.md`, `docs/`) → explorare structură → analiză aprofundată în paralel pe 4 zone (services backend, repositories/models/top-level backend, componente frontend mari, lib/api/App). Toate referințele sunt `file:line` verificabile.

---

## Cuprins

- [PARTEA 1 — Probleme găsite](#partea-1--probleme-găsite)
  - [A. God-files / God-components](#a-god-files--god-components-dimensiuni-critice)
  - [B. Cod duplicat](#b-cod-duplicat)
  - [C. Funcții prea lungi](#c-funcții-prea-lungi60-linii-selecție-critică)
  - [D. Logică greoaie](#d-logică-greoaie)
  - [E. Încălcări de arhitectură](#e-încălcări-de-arhitectură-regula-routerservicerepository)
  - [F. Type safety & eroare](#f-type-safety--eroare)
  - [G. Config / security smells](#g-configsecurity-smells)
  - [H. Dead code / minor](#h-dead-code--minor)
- [PARTEA 2 — Plan de acțiune](#partea-2--plan-de-acțiune-pas-cu-pas)
- [Rezumat al ordinii](#rezumat-al-ordinii-de-ce-în-această-secvență)

---

# PARTEA 1 — Probleme găsite

## A. God-files / God-components (dimensiuni critice)

| Fișier | Linii | Cea mai mare unitate |
|---|---|---|
| `src/components/Dashboard.tsx` | 2663 | componenta `Dashboard` ~2021 linii, ~45 `useState` |
| `backend/services/dashboard/queries.py` | 1735 | `_fetch_regional_stats` 201 linii |
| `backend/services/agents.py` | 1407 | `get_agent_evaluation_v2` **557 linii** |
| `backend/services/grile_monthly.py` | 1326 | `reserve_monthly_operation` 169 linii, **fără layer de repository** |
| `src/components/Campaigns.tsx` | 1652 | componenta ~766 linii |
| `src/components/TargetCalculatorSubtab.tsx` | 1371 | componenta ~1005 linii |
| `backend/models.py` | 901 | ~70 modele Pydantic într-un singur fișier; `AgentEvaluationV2Row` are **47 câmpuri** plate |
| `src/components/AgentEvaluationSubtab.tsx` | 1121 | două sisteme de sortare paralele |
| `src/components/Agents.tsx` | 1064 | componenta ~767 linii |

---

## B. Cod duplicat

### B1. Backend — duplicare de impact mare

- **Builder-ul de scope params reimplementat de ~9 ori** în loc să folosească helper-ele canonice `_build_scoped_params` (`services/dashboard/utils.py:27`) / `base_filter_values` (`services/filters.py:30`). Reimplementări în `campaigns.py:42-65,256-281,447-456,524-534,600-611`, `agents.py:1306-1318`, `dashboard_service.py:266-296,317-346`. Comentariul din `campaigns.py:304` chiar recunoaște: *"Mirror exact al logicii din _campaign_clauses"*. Exact bug-ul pe care îl previne regula din AGENTS.md ("Do not leave unused asyncpg parameters").
- **`_compute_dashboard_promotion_result` (`queries.py:100-197`) ≈ `_compute_promotion_result` (`campaigns.py:85-200`)** — ~100 linii cu structură identică (dispatch pe `rule_type`, tail-recursion cu `cutoff_date`, fallback la cele 3 `compute_promo_*`). Doar forma de return diferă.
- **Blocul de enrichment cu metrici de campanie repetat de 4×** în `queries.py` (`_enrich_store_stats_with_campaign:459`, `_fetch_agent_stats_rows:655`, `_fetch_regional_stats:858`, `_fetch_asm_stats:1040`) — același `load_special_cards_config` → `parse_promotion_definition` → `get_incentive_campaign` + bloc SQL `cardinality($2::TEXT[])`.
- **`current_agents` CTE de 4× + `option_query` de 2×** în `agents.py` (227, 418, 550, 898).
- **`salary_base`/`salary_dedup` CTE de 5×**, expresia `agent_key` de **6×**, filtrul `MIN_SALARY_FOR_AVERAGE` de **8×** în `repositories/salarii.py` (514 linii).
- **Boilerplate de filtru identic de 3×** în `repositories/exports.py:50-69, 201-220, 275-294` (același dict + loop).
- **`'TR %'` literal în 9+ fișiere** deși constanta `_DISTRIBUTION_LOCATION_PREFIX` există în `services/filters.py:18`. Cele mai multe call-site-uri hardcodează string-ul. Locații: `repositories/target_calculator.py:52`, `repositories/exports.py:53,204,278`, `repositories/filters.py:16`, `services/filters.py:68`, `services/campaigns.py:52`, `services/contests.py:37,132`, `services/visits_report.py:164`, `services/reporting_refresh.py:145,213,312,368,470`.
- **`is_cartela` cu două semantici** (includ vs exclud) în 8+ fișiere, fără helper comun. Includere cartela (`is_cartela = true`): `target_calculator.py:432`, `dashboard.py:93`, `queries.py:1209`. Excludere retail (`NOT is_cartela`): `services/filters.py:72`, `reporting_refresh.py:144,212,311,367,469`, `contests.py:130`, `promo_copurchase.py:422`. Import: `importer.py:86,103`.
- **Aritmetica month-index în 5 formulări** (`SUBSTRING` vs `split_part` vs Python `split`), plus `shift_month` redefinit în 4 module (`target_calculator.py:49-57`, `dashboard/utils.py:11-15`, `agents.py:33-37`, `grile_monthly.py:159-165`).
- **CTE-urile promo duplicat de 3×** în `promo_copurchase.py` (`compute_promo_copurchase`, `compute_promo_trigger_discounted`, `compute_promo_same_model_pair`) — același `WITH lines AS (...)` + `discounted AS (SELECT DISTINCT ON ... ORDER BY ... l.unit_price ASC, ...)`.
- **`forecast_meta` CTE de 3×** în `queries.py` (381-401, 791-811, inline 279-303) + reimplmentat în `agents.py:591-624`, deși `services/forecast.py` are helper-ul canonical `get_forecast_factor`.
- **`safe_filename`** două implementări: `grile_monthly.py:195-201` vs `exports.py:693-699`.
- **`excluded_by_site_item`** duplicat: `promo_copurchase.py:64-69` (metodă) vs `campaigns.py:76-82` (funcție).
- **`sales_summary` CTE** aproape identic în `dashboard.py:41-58` și `205-227`.

### B2. Frontend — duplicare de impact mare

- **State-setting boilerplate de 4×** în `Dashboard.tsx` (cache-hit + API-success pentru current și history) — același bloc de 15 `setX(...)` + `setCachedView(...)` la `762-783`, `789-821`, `852-870`, `886-918`.
- **6 handler-e de sortare + 6 memo-uri sorted sunt clone** în `Dashboard.tsx:1336-1454` (`sortedStores`/`sortedAgents`/`sortedRegionals`/`sortedHistoryRegionals`/`sortedHistoryStores`/`sortedHistoryAgents`).
- **JSX de tabel current vs history duplicat** (tabel RM, Magazine, Agenti, overview, promo, top categorii — fiecare în 2 copii): RM 1770-1835 vs 2405-2468; Magazine 1837-1908 vs 2471-2540; Agenti 1910-1976 vs 2542-2607; overview 1516-1622 vs 2185-2295; promo 1681-1707 vs 2298-2342; top categorii 1742-1767 vs 2377-2402.
- **Array-ul de luni românești** duplicat în `TargetCalculatorSubtab.tsx:49`, `AgentEvaluationSubtab.tsx:47,56`, `SalariiSubtab.tsx:43`, `GrileMonthlyPanel.tsx:23`, `api/grile.ts:156`.
- **Formatters locale shadow-uiesc `lib/formatters`** în `SalariiSubtab.tsx:51-66`, `AgentEvaluationSubtab.tsx:14-30`, `Agents.tsx:37-38` — cu semantică divergentă (unele returnează `'0'` pentru null, altele `'-'`).
- **`LoadingCard`/`ErrorCard`/`Metric`** definite în `DashboardWidgets.tsx:627-653,73-100` și redefinite în `Campaigns.tsx:1409-1439`.
- **`FirmBadge` local (`AgentEvaluationSubtab.tsx:143-158`) vs `FirmaBadge`** folosit în alte module — două componente pentru același concept, cu styling divergent.
- **Pattern-ul manual fetch+cache+`isMountedRef`** în `Dashboard.tsx:709-931` și `Campaigns.tsx:151-292` (~400 linii boilerplate) vs. TanStack Query folosit corect în `Agents.tsx`.
- **Pattern-ul drawer/overlay** repetat în 4 componente (`StoreDetailDrawer`, `AgentDrawer`, `VisitDrawer`, `SalaryDrawer`) — toate `fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm` + outside-click-close + `X` header.
- **Segmented tab switcher** repetat în 5 locuri (`Dashboard:1471-1503`, `Campaigns:387-401`, `Agents:506-539`, `Settings:299-318`, `AgentEvaluation:991-1009`).
- **Trio-ul sort-state+handler+sorted-memo** reinventat de ~10 ori (6× în Dashboard, 2× în AgentEvaluation, 2× în Salarii, 1× în Campaigns/SortableTable).
- **Pattern-ul blob-download** duplicat de 5× (`targetCalculator.ts:196-204`, `grile.ts:162-169`, `tableExport.ts:60-68`, `Settings.tsx:277-284`, `VisiteSubtab.tsx:34-38`) — cu bug latent: unele variante nu append-uiesc `<a>` la DOM.
- **Filter→query "omit All sentinel"** în 3 implementări: `filterQueries.ts:5-16` (canonic), `visitsReport.ts:100-107` (manual `URLSearchParams`), `Agents.tsx:329-332` (literal `'Toate'`/`'Toti'` hardcodate).
- **Tipuri query care se suprapun**: `DashboardQuery` (`api/dashboard.ts:9-18`), `CampaignQuery` (`api/campaigns.ts:4-11` — subset), `AgentsQuery` (`api/agents.ts:3-11` — redenumire `month`→`selected_month`).
- **Tuple-ul store-identity** `{ site_code, locatie, firma, regional, asm }` definit de 3+ ori în `types.ts:336-342`, `types.ts:287-294` (în `AgentOption`), `grile.ts:22-46`.
- **Chart config boilerplate** repetat de 5× în `Dashboard.tsx` (daily 1725-1737, history daily 2358-2372, currentHistory 2014-2029, yearHistory 2038-2057, kpi 2094-2112) — același `<CartesianGrid strokeDasharray="3 3" />` / `<XAxis tick={{fontSize:10}}/>`.
- **`client.ts` își duplicatează propriul bloc URL+params** în `get` (42-55) și `post` (76-89) — caracter-cu-caracter identic; `put`/`patch`/`delete` repetă linia `API_BASE_URL` dar **nu suportă params** (forțează workaround `crm.ts:43` cu `post` + `null` body).
- **`RO_MONTHS` + `formatMonthLabel`** duplicate între `api/grile.ts:156-161` și `GrileMonthlyPanel.tsx:23-30`.

---

## C. Funcții prea lungi(>60 linii, selecție critică)

### Backend
- `get_agent_evaluation_v2` — `services/agents.py:536-1092` — **557 linii**
- `rebuild_reporting_month` — `services/reporting_refresh.py:79-497` — **419 linii**
- `get_promotions_incentives` — `services/campaigns.py:287-708` — **422 linii**
- `get_agent_evaluation` — `services/agents.py:191-534` — **344 linii**
- `get_dashboard_all` — `services/dashboard_service.py:368-685` — **318 linii**
- `_fetch_regional_stats` — `services/dashboard/queries.py:730-930` — 201 linii
- `rebuild_agent_lifecycle_reporting` — `services/reporting_refresh.py:500-694` — 195 linii
- `_fetch_agent_stats_rows` — `services/dashboard/queries.py:534-727` — 194 linii
- `_fetch_asm_stats` — `services/dashboard/queries.py:933-1115` — 183 linii
- `fetch_report_rows` — `repositories/exports.py:12-192` — **181 linii** (cea mai mare funcție din setul de repo)
- `reserve_monthly_operation` — `services/grile_monthly.py:329-497` — 169 linii
- `_fetch_promo_incentive_summary` — `services/dashboard/queries.py:1494-1668` — 175 linii
- `fetch_summary` — `repositories/dashboard.py:11-145` — 135 linii
- `build_incentive_card` — `services/dashboard_specials.py:597-739` — 143 linii
- `get_store_detail` — `repositories/target_calculator.py:379-523` — 145 linii
- `compute_promo_same_model_pair` — `services/promo_copurchase.py:604-728` — 125 linii
- `fetch_overview` — `repositories/salarii.py:14-94` — 81 linii
- `fetch_agents_summary` — `repositories/salarii.py:156-268` — 113 linii
- `fetch_trend` — `repositories/salarii.py:396-487` — 92 linii
- `fetch_summary_by_site` — `repositories/salarii.py:301-394` — 94 linii
- `_daily_comparison_table` — `services/exports.py:529-623` — 95 linii
- `export_excel` — `services/target_calculator.py:411-508` — 98 linii
- `fetch_monthly_history` — `repositories/dashboard.py:168-261` — 94 linii
- `compute_promo_actuals_from_report` — `services/promo_copurchase.py:270-391` — 122 linii
- `compute_promo_copurchase` — `services/promo_copurchase.py:394-505` — 112 linii
- `compute_promo_trigger_discounted` — `services/promo_copurchase.py:508-601` — 94 linii
- `get_history_by_year` — `services/dashboard_service.py:247-366` — 120 linii
- `calculate` — `services/target_calculator.py:159-313` — 155 linii
- `require_auth` — `backend/auth.py:125-202` — 78 linii
- `auth_proxy` — `backend/main.py:255-319` — 65 linii
- `save_draft_scenario` — `repositories/target_calculator.py:99-201` — 103 linii

### Frontend
- componenta `Dashboard` — `Dashboard.tsx:594-2615` — ~**2021 linii**
- componenta `TargetCalculatorSubtab` — 366-1371 — ~1005 linii
- componenta `Campaigns` — 101-867 — ~766 linii
- componenta `Agents` — 297-1064 — ~767 linii
- componenta `Settings` — 48-651 — ~603 linii
- componenta `SalariiSubtab` — 121-687 — ~566 linii
- `StoreDetailDrawer` — `TargetCalculatorSubtab.tsx:168-355` — 187 linii
- `VisitDrawer` — `VisiteSubtab.tsx:119-339` — 220 linii
- `fetchCurrentData` — `Dashboard.tsx:742-830` — 88 linii
- `loadHistory` — `Dashboard.tsx:832-931` — 99 linii
- `loadCurrentFocus` — `Campaigns.tsx:160-259` — 99 linii
- `App()` — `App.tsx:62-302` — ~240 linii (12 `useState` + 11 `useEffect`)
- `SortableTable` — `Campaigns.tsx:1530-1640` — 110 linii

---

## D. Logică greoaie

- **`repositories/dashboard.py:15-31` — 11 lanțuri `.replace()` pe clauze SQL** pentru a realias-ui `s.`→`cs.` / `agg.`→`c.`. Cel mai fragil cod din set — se strică silențios dacă un alias se schimbă sau dacă un nume de coloană e substring al altuia (ex. `agg.asm` vs `agg.asmx`). Fără test care să valideze realias-uirea. Același `.replace("agg.", "s.").replace("s.agent", "agg.agent")` trick și la 172-176 și 279-283 (cu special-case pentru `agent` pentru că remaparea ar fi greșită).
- **`dashboard_service.py:get_dashboard_all`** (368-685) — 13 închideri async concurente (fiecare `self.pool.acquire()` separat) + `asyncio.gather` de 15 task-uri despachetat **pozițional** (`results[0]`...`results[14]` la 652-666, fiecare cu `# type: ignore[assignment]`). Reordonarea listei gather strică maparea silențios; + presiune pe pool (până la 13 conexiuni concurente per request).
- **`get_agent_evaluation_v2`** (`agents.py:536-1092`) — string SQL de ~350 linii cu 15+ CTE, `CASE` cu magic numbers `0.6667/0.3333` (698-700), `0.4` (735); apoi 130 linii Python scoring cu dicționare de ponderi hardcodate (989-993) și sistem 6-ramuri `_score_band`/`_score_rating`.
- **`get_promotions_incentives` (422 linii)** — nesting adâncă (`if has_active_promotion` → `if incentive_campaign` → `if reward_map_for_stores` → `if has_active_promotion` din nou la 560) + acces fragil pe liste poziționale `store_inc.get(s.store_name.split(" - ")[0], [None, 0.0, "", 0])[3]` (564) și `[None, 0.0, "", 0, 0.0][4]` (569) — magic-index list access care se strică dacă forma listei se schimbă.
- **`reserve_monthly_operation`** (`grile_monthly.py:329-497`) — state mutabil (`reservation`/`blocked_message`/`operation_id`) prin 6+ queries într-o tranzacție cu early-return-uri multiple și `ON CONFLICT ... DO NOTHING` retry (447-483). Greu de urmărit tranzițiile de stare.
- **`time.sleep` în `async def`** în `grile_monthly.py` (951, 1056, 1149) — blochează event loop-ul. + `print()` pentru logging în funcții async (948, 957-960, 1044, 1070-1078, 1174, 1236-1237), capturat via `contextlib.redirect_stdout` în `run_monthly_op:1285` — brittel vs. logging structurat.
- **`main.py:auth_proxy` (293-306)** — OIDC discovery rewrite prin `.replace()` pe text JSON (URL hardcodat `https://auth.unihub.ro/application/o/token/` și `/userinfo/`), deși `auth.py:33-39` citește `OIDC_ISSUER` din env — două sururi de adevăr pentru issuer. Dacă issuer-ul se schimbă sau returnează o variantă cu trailing slash, rewriting se anulează silențios. Ar trebui parse JSON → mutare câmpuri → re-serializare.
- **`App.tsx`** — 12 `useState` + 11 `useEffect`, plus un **global event bus** ascuns (`window` `'unihub:navigate'` CustomEvents la 183-200) care mută stare (`activeTab`/`campaignsSection`/`hubSection`/`mgmtSubtab`) bypassând props/context — canal de data-flow greu de trasat, netipizat la dispatch.
- **`agents.py:133`** — `c.replace("import_month = $1", "import_month <= $1")` — string surgery pe SQL fragil (dacă clauza se schimbă formatul, replace-ul nu mai prinde).
- **`Agents.tsx` section ternary (506-539)** — `concurs ? ... : loading ? ... : error ? ... : promo ? ... : incentive ? ... : premium ? ...` — 460 linii ternar imbricat (`Campaigns.tsx:403-864` pattern similar).
- **`_daily_comparison_table`** (`exports.py:529-623`) — nesting `for dim_key ... for day in range(1, max_day+1) ... for metric in metrics ... for month in months` (589-617) — 4 niveluri de nesting cu coloane delta condiționale.
- **`get_history_by_year`** (`dashboard_service.py:247-366`) — două loops scope-param cu offset-uri diferite (`p = 2` vs `p = 3`), expansiune `current_scope` condițională, special-casing `year == 2023` (269, 305, 314).
- **`allocate_with_floors`** (`target_calculator.py:72-132`) — loop iterativ `while remaining:` care mutează un `set` și `dict`, cu corecție de rounding (122-130) care face `max(adjustable or rows, key=...)` — fallback-ul `or rows` când nimic nu e ajustabil e ușor de ratat.
- **`finalize_scenario`** (`repositories/target_calculator.py:308-377`) — întoarce bare `False` (321, 333, 337) pentru 3 motive distincte de eșec → caller-ul nu poate distinge 409 (stale revision) vs 422 (validare).

---

## E. Încălcări de arhitectură (regula router→service→repository)

AGENTS.md: *"Backend flow is router -> service -> repository. Keep SQL and business logic out of routers."*

- **SQL în services (la scară largă)**:
  - `services/dashboard/queries.py` — **toate** funcțiile execută SQL direct via `conn.fetch(f"""...""")`. 13+ query-uri embedded. Modulul se numește "queries" și stă în `services/` dar e efectiv un repository care ia `conn: Any` (fără typing `asyncpg.Connection`). Nu există `repositories/dashboard/queries.py`.
  - `services/agents.py` — repo-ul e pass-through executor (`self.repo.get_*_stats(query, ...)`); tot SQL-ul stă în service (153-154, 453-454, 933-934, 1177, 1247, 1293, 1393).
  - `services/grile_monthly.py` — **fără layer de repository deloc**. Fiecare funcție de DB (`load_entries:283`, cele 10+ din 329-690, `ensure_reset_items:600`, etc.) execută SQL direct pe `asyncpg.Pool`.
  - `services/promo_copurchase.py` — fără repository; cele 4 `compute_promo_*` rulează `conn.fetch(f"""...""")` direct.
  - `services/reporting_refresh.py` — fără repository; totul via `conn.execute(...)`.
  - `services/campaigns.py:get_promotions_incentives:621-631` — rulează raw `conn.fetch(f"""SELECT agg.agent ... FROM reporting_item_month agg ...""")` bypassând repo-ul, în aceeași metodă care altfel folosește repo-ul. Inconsistență internă.
  - **Excepții curate**: `services/exports.py` și `services/target_calculator.py` folosesc corect `self.repo.fetch_*` — modelul de urmat.
- **Anti-pattern `join_sql`/`where_sql`/`clauses` injection**: repo-urile `salarii.py` (8 metode cu `join_sql`/`where_sql`), `dashboard.py` (3 metode cu `clauses: list[str]`), `campaigns.py` (5 metode cu `*_where_sql`/`*_clauses`) acceptă fragmente SQL pre-asamblate în service și le f-string-interpolează. Corectitudinea depinde silențios de alias-urile folosite (`st`/`sr`/`agg`). Nu e injectable (valori sunt parametrizate), dar e fragil și netestabil izolat. Inversează spiritul regulei: SQL-ul e asamblat în service și executat în repo, fără link compile-time între alias-ele fragmentului și query-ul repo-ului.
- **Logică business în repository**:
  - `finalize_scenario` (`target_calculator.py:328-337`) encodă invariantele AGENTS.md ("toate valorile manager + alocare zero" și comparația 2-decimale) direct în SQL/Python în repo. Tranzacția/advisory lock în repo e OK, dar semantica regulii ar fi mai clară în service. + întoarce `False` în loc de excepții distincte (vezi D).
  - `_aggregate_report_rows` (`repositories/visits_report.py:161-212`) face grouping/averaging/sorting în Python — logică de raport, nu de acces la date; ar trebui în service.
- **Două implementări paralele de scope-filter**: `services/filters.py:scoped_clauses` (stil `string_to_array($N::TEXT, ',')` cu `positions` dict) vs `repositories/exports.py:50-69` (stil `ANY($N::TEXT[])` cu list+counter). Ambele produc clauze "firma/regional/asm/site_code/agent scope" dar cu stil de parametri incompatibil și handling `TR %`/`is_active` diferit.
- **Dashboard SQL există în 2 layere**: `repositories/dashboard.py` și `services/dashboard/queries.py` — repository-ul e parțial redundant/legacy; SQL pentru dashboard e în ambele.
- **Visits repository pe SQLite+filesystem** în loc de pool-ul asyncpg Postgres (`visits_report.py:7-8`) — legitim (vizitele sunt în SQLite-ul app-ului mobil), dar `_aggregate_report_rows` e logică business în repo și `photo_path` leakează `Path` la caller.

---

## F. Type safety & eroare

- **`client.ts` construit pe `any`** (`src/api/client.ts`): `<T = any>` pe fiecare metodă (41, 75, 115, 128, 141); `params?: Record<string, any>`; `data?: any`; `return { data: blob as unknown as T }` (68, 109) — double cast prin `unknown`. Caller-ul poate cere `client.get<MyType>(..., { responseType: 'blob' })` și primește `Blob` tipizat ca `MyType`.
- **11 apeluri în `hr.ts`/`tasks.ts`/`crm.ts` omit generic** → răspuns `any`. Tipul declarat pe wrapper (`Promise<LeaveRequest[]>` etc.) e **minciună** — typos în nume de câmpuri trec typecheck până la runtime. Locații: `hr.ts:23,34,39,44,84,89`; `tasks.ts:35,40,45`; `crm.ts:38,43,48`; `salarii.ts:151`.
- **Fără structured error type**: `client.ts:32-38` aruncă `Error('API error: N')` — corpul JSON al backend-ului nu se consumă, caller-ul nu poate face switch pe status. Toate erorile devin "API error: 500" fără detalii.
- **Latch `unauthorizedRedirectStarted` (`client.ts:14`)** — modul-level, **nu se resetează**. Dacă user-ul se re-loghează, o a doua eroare 401 în altă parte nu mai declanșează handler-ul.
- **`SortableTable` în `Campaigns.tsx`** — generic `T extends Record<string, unknown>` forțează **~25 cast-uri `as unknown as X`** (502, 521, 551, 560, 577, 617, 626, 628, 638, 646, 657, 690, 708, 710, 719, 727, 740, ...) + `rows={promoData.top_stores as (PromoTopStore & Record<string, unknown>)[]}` noise.
- **`any` în tooltip-uri recharts**: `Agents.tsx:163` (`{ active, payload, label }: any`), `Agents.tsx:262` (`CustomTooltip`), `payload.map((entry: any, i: number)` la 276.
- **Unsafe casts în `App.tsx`**: 184 `(event as CustomEvent<{...}>).detail` pe `Event` netipizat; 43,49,80-82 `saved as HubSection`/`as ManagementTab`/`as CampaignsSection` după `.includes()` pe array widenit; `auth/AuthContext.tsx:70` `(window as unknown as Record<string, unknown>).__E2E_USER__ as User | undefined`; `viewCache.ts:13` `cache.get(key) as CacheEntry<T> | undefined` (cache-ul stochează `CacheEntry<unknown>`).
- **`models.py`**: lipsă validare pe `month: str` (niciun `pattern` `YYYY-MM`), `target_value: Decimal` fără `>= 0` deși e business write (AGENTS.md: "store target writes"), status-uri ca plain `str` cu comentarii în loc de `Literal` (ex. `StoreCoverageItem.status:601`), `avg_completion: float` fără range 0-100. Mixat naming `proc_`/`prc_` (două abrevieri pentru "procent").
- **`models.py` forward-ref spaghetti**: `DashboardAllResponse:508-525` referă 6 tipuri ca string-uri, unele definite înainte (`ReceiptBucketItem:32`), unele după (`PeriodComparisonPayload:560`, `CategoryMixItem:566`, `BrandMixItem:573`). `FilterOptions:357` referă `StoreOption` definit la 492 — forward ref de 130 linii. Ordine aleatoare; unele ref-uri sunt needless forward-refs.

---

## G. Config / security smells

- **`auth.py:40`** — `OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "4yiNauwNNzIoIE3Mq9IFnylxtdih9jFSqSKGw93t")` — **client_id real ca default**. Dacă lipsește env, autentifică silențios contra unui audience specific. Ar trebui fail-closed (fără default) în producție.
- **`auth.py:130-137`** — bypass localhost + `X-Hub-Internal` secret care impersonifică `unihub-admin` (`groups=["unihub-admin"]`). Documentat, dar combinația "orice request de la localhost" + "secret static" înseamnă că orice SSRF la localhost care poate seta header-e ocolește OIDC. Dat fiind statutul auth forte al AGENTS.md, merită flag.
- **`rate_limits.py:89`** — `rate_limiter = InMemoryRateLimiter()` e **per-proces**. Cu mai mulți uvicorn workers, limita efectivă e `limit × worker_count`, nu limita globală documentată. Pentru `SALES_IMPORT_UPLOAD_LIMIT=5/900s` = 5 upload-uri / 15 min **per worker**. Gap real de corectitudine pentru endpoint-urile "risky/costly" pe care fișierul le protejează. + `_hits: dict` (68) nu se evictă (creștere nemărginită).
- **`rate_limits.py:92-103`** — `_client_ip` trust-uiește `cf-connecting-ip`/`x-forwarded-for` necondiționat. Dacă app-ul e reachable direct (nu doar prin CF+proxy), clientul poate spoofa header-e pentru bucket-uri fresh.
- **`visits_report.py:7-8`** — **paths absolute hardcodate** `/opt/Mobiup/unihub-retail/data/visits/...` (nu din env). Se strică în orice deploy non-`/opt/Mobiup/...`. `VISITS_DB_PATH` există în config — nu se folosește aici.
- **`auth.py:44-45`** — `_jwks_cache`/`_jwks_fetched_at` module-level fără lock; `_fetch_jwks` (48-72) citește/scrie fără `asyncio.Lock`. Sub cereri concurente la cold-start mai multe coroutines pot fetch-a JWKS simultan. + fallback stale-cache (66-68) fără max-stale bound — un JWKS stalic de zile tot se servește.
- **`auth.py:199-200`** — `iat=payload.get("iat", 0), exp=payload.get("exp", 0)` — `AuthClaims` poate reprezenta o stare imposibilă (token fără `exp` → claim care arată expirat dar a fost verificat).
- **Magic literals business** (de centralizat în config/constante):
  - prag `0.99/0.89` pentru incentive multiplier (`dashboard_specials.py:487-493`)
  - `0.9` qualified-store threshold (`queries.py:1643`)
  - `20%` promo_impact (`queries.py:1659` `promo_sales * Decimal("0.20")`)
  - baseline `'2025-01'` repetat de **7×** în `agents.py` (249, 277, 377, 438, 570, 669, 824)
  - ponderi de scoring hardcodate (`agents.py:989-993`)
  - `min_working_days = 8`, `min_receipts = 20 if is_partial else 30` (`agents.py:967-971`)
  - `MIN_SALARY_FOR_AVERAGE = 2000` (`salarii.py`, interpolat în 8 locuri)
  - `DEFAULT_MIN_FLOOR = Decimal("35000")` (`target_calculator.py:23`)
  - `LIMIT 8` (`repositories/campaigns.py:54,70`), top-5 (`queries.py:1422,1477,1719` `rank_no <= 5`), ferestre 12/15/16 luni (`hr.py:91`, `target_calculator.py:402-404,486-490`, drawer 16 luni)
  - epsilon `0.01` (`target_calculator.py:339,457`, frontend `TargetCalculatorSubtab:110,533,739,1212,1338`)
  - frontend: praguri `80/50` complianță vizite (`VisiteSubtab:67,80-84,631-635`), `scoreColor 16/10`, `pointColor 3/1`, `score100Color 75/50`, `achievementColor 0.99/0.89`, `+5%` threshold, `200` max agents (`Agents:935`), `slice(0, 5)` top-flux, `300`ms debounce, `700`ms autosave, `15000`ms collab refresh
- **`permissions.py:11-18 vs 20-27`** — `SALARY_ACCESS_GROUPS` și `MANAGEMENT_ACCESS_GROUPS` sunt seturi **identice**. Dacă unul se schimbă, celălalt nu. + mesajele de eroare (105-108, 138, 166) omit `authentik admins`/`unihub-hr` deși sunt în setul permis — mesaj user-facing mai îngust decât politica reală.
- **`permissions.py:111`** — `request.state.salary_claims = claims` mută stare pe request, dar celelalte `require_*` deps nu — inconsistent.
- **`main.py:10,14,33-37`** — `load_dotenv`/`setup_logging`/`sentry_sdk.init` la import-time, înainte de `FastAPI` import — side effects la import, greu de testat.
- **`main.py:147-153 vs 340-352`** — politica de cache SPA no-cache duplicată în `SecurityHeadersMiddleware.dispatch` și `SPAStaticFiles.get_response`.
- **`models.py`** — `StoreStats:289-307` nullabilitate inconsistentă (`qty_total: int | None` vs `nr_bonuri: int` vs `target: Decimal` vs `proc_realizare_target: Decimal | None`) din aceeași sursă de query.

---

## H. Dead code / minor

- **`Dashboard.tsx:656`** — `const [, setAsms] = useState<AsmStat[]>([])` — valoarea nu se citește niciodată (destructured la nimic), doar se scrie. `aggregateAsms:382` și `DashboardWidgets.getAsmSortValue:531` sunt effectively dead. Șterge sau randează un tabel ASM.
- **`dashboard_specials.py:702-727`** — branch `if per_product_mode:` vs `else:` produce liste `metrics` **byte-identice** (ambele 4 metrici "Unitati nete" etc.). Ramură pointless — șterge.
- **`repositories/exports.py:73`** — `field_group` computat dar nereferit în f-string (query-ul folosește `field_aliases` la 122). Dead code.
- **`repositories/exports.py:278-286`** — `update_final_targets` compută `existing` și întoarce `int(existing or 0)` dar nu îl folosește să guardeze comportamentul — `executemany` rulează oricum. COUNT-ul e no-op audit.
- **Caches module-level mutable fără lock** (nu sunt thread-safe pe backend concurent, deși ARQ worker `max_jobs=1` mitiga pentru worker): `promo_copurchase.py:46-49` `_promo_actuals_cache`; `dashboard_specials.py:22-25` 4 cache-uri; `auth.py:44-45` `_jwks_cache`.
- **`grile_monthly.py`** — `attempts=6, base_delay=3.0` repetat la 769-774, 1046-1051, 1123 — ar trebui constante numite. `RESET_RANGES:46-57`, `GRILA_CELLS:58-77` sunt adrese de celule hardcodate (cuplare fragilă la layout-ul sheet-ului, dar cel puțin centralizate).
- **`grile_monthly.py`** — `build_google_services()` rebuild per call (945, 1040, 1149) — AGENTS.md zice "Build one service per worker thread"; rebuild per call e wasteful (deși safe).
- **`grile.py` repository** — `SELECT *` la 252, 262, 269, 278 (fragil la schimbări de schemă, restul repo-urilor enumeră coloane). + lipsă filtru `TR %` în `get_hierarchy:87-107` și `get_active_sheets:15-25` — confirmă dacă Grile include intenționat locații de distribuție.
- **`hr.py` repository** — `($2::text IS NULL OR s.regional = $2)` pattern repetat (130, 152-153, 164-165) — idiom asyncpg dar defeates index usage când param e NULL. + `SELECT *` la 141. + `to_char(now() - ($2 || ' months')::interval, 'YYYY-MM')` cu `str(months)` coercion (153, 165, 179) — convoluat; `make_interval(months => $2::int)` mai curat.
- **`salarii.ts`** — outlier de prefix rută: folosește `/salarii/...` fără `/api/` (90, 99, 114, 133, 151) pe când toate celelalte api files folosesc `/api/...`. Inconsistență — capcană de mentenanță.
- **Query keys inline** fără factory: `['agents', 'overview', queryParams]` (`Agents:337`), `['grile-overview', month]` (`GrileSubtab:388`), etc. — granularitate inconsistentă (segmented vs hyphenated single string); invalidările trebuie retype-uite literal → typos silențioase care rate invalidarea cache-ului.
- **`hr.ts:88`** — `months = 6` default history window magic.
- **`auth/AuthContext.tsx:15`** — `OIDC_CLIENT_ID = '4yiNauwNNzIoIE3Mq9IFnylxtdih9jFSqSKGw93t'` fallback — pentru SPA public nu e secret, dar env-misconfigured deploy target-uiește silențios clientul greșit.
- **`agents.py:get_agents_overview:78-189`** — `c.replace("import_month = $1", "import_month <= $1")` la 133 — string surgery pe SQL.
- **`SalariiSubtab.tsx:357-370`** — IIFE inline în `<select>` options (loop nested pentru month options în JSX).
- **`Agents.tsx:310`** — `(localStorage.getItem('agents_activeTab') as any)` — unsafe cast din string stocat la union.
- **`Agents.tsx:366-386`** — 4 effects separate de persistență localStorage (unul per câmp) — ar trebui un `usePersistentState` hook.

---

# PARTEA 2 — Plan de acțiune pas cu pas

Principiu de prioritizare: **foundație/shared helpers mai întâi** (risc mic, leverage mare, deblochează refactorările mari) → **fix-uri de arhitectură** → **spargerea god-files** → **type safety & eroare** → **curățenie magic/dead code**. Fiecare pas e independent testabil prin `npm run typecheck` / `npm run typecheck:strict` / `npm run lint` / `pytest backend/tests/ -q` / `mypy backend/ --ignore-missing-imports --explicit-package-bases` / `npm run build`.

## Faza 0 — Quick wins de încredere (risc minim, impact imediat)

### 0.1 Elimină duplicarea literalului `'TR %'` și a filtrului `is_cartela`
- **De ce**: invariant business central (AGENTS.md: "Retail excludes Cartele and locations matching TR %"), duplicat în 9+ fișiere — un singur typo produce rapoarte greșite care includ/exclud distribuție.
- **Cum**: toate call-site-urile folosesc constanta `_DISTRIBUTION_LOCATION_PREFIX` din `services/filters.py:18`; adaugă helper `retail_exclusion_clauses()` pentru perechea `NOT is_cartela AND locatie NOT ILIKE 'TR %'`.
- **Verificare**: `pytest backend/tests/ -q`.

### 0.2 Unifică formatters-urile frontend și array-ul de luni
- **De ce**: 4+ copii ale array-ului de luni + formatters locale cu semantică divergentă (returnează `'0'` vs `'-'` pentru null) — bug-uri vizuale greu de trasat.
- **Cum**: creează `src/lib/dates.ts` (luni + `formatMonthLabel`); obligă `SalariiSubtab`/`AgentEvaluationSubtab`/`Agents` să importe din `lib/formatters` în loc să redefinească; șterge duplicatele.

### 0.3 Elimină duplicarea `LoadingCard`/`ErrorCard`/`Metric`/`FirmBadge` și blob-download
- **De ce**: două definiții divergente ale acelorași componente + 5 copii ale blob-download cu bug latent (fără append la DOM în `targetCalculator.ts:196`).
- **Cum**: importă din `DashboardWidgets`; șterge redefinițiile din `Campaigns.tsx:1409-1439`; creează `src/lib/download.ts` cu `downloadBlob(blob, filename)` care append-uiește la DOM consistent; înlocuiește cele 5 call-site-uri.

### 0.4 Adaugă generice pe apelurile netipizate; importă constantele `ALL_*` în `Agents.tsx`
- **De ce**: ~10 linii schimbate, deblochează type-safety reală pe `hr`/`tasks`/`crm`; elimină un bug silențios dacă sentinel-ul `'Toate'`/`'Toti'` se schimbă (filterValues.ts le definește ca `ALL_FIRMS`/`ALL_SCOPE`/`ALL_STORES`).
- **Cum**: adaugă `<LeaveRequest[]>` etc. pe cele 11 apeluri; înlocuiește `Agents.tsx:329-332` `'Toate'`/`'Toti'` cu constantele.

## Faza 1 — Shared helpers backend (deblochează Faza 3)

### 1.1 Forțează toate scope-param loops prin `_build_scoped_params`/`base_filter_values`
- **De ce prioritate mare**: ~9 reimplementări = ~9 locuri unde poate apărea silent un asyncpg parameter unused (exact bug-ul pe care îl previne AGENTS.md). E prerequisit pentru mutarea SQL-ului în repositories (Faza 3) — fără un builder canonical, mutarea doar relochează duplicarea.
- **Cum**: înlocuiește loop-urile manuale din `campaigns.py:42-65,256-281,447-456,524-534,600-611`, `agents.py:1306-1318`, `dashboard_service.py:266-296,317-346` cu helper-ul existent; șterge `_campaign_clauses` din `campaigns.py`.

### 1.2 Unifică aritmetica month-index și `shift_month` într-un singur modul utilitar
- **De ce**: 5 formulări diferite (`SUBSTRING`/`split_part`/Python) pentru același calcul — risc de inconsistență la schimbări.
- **Cum**: creează `backend/services/date_utils.py` cu `month_index_sql(alias)` + `shift_month(ym, n)`; înlocuiește toate reimplementările (`agents.py:29-30,33-37`, `reporting_refresh.py:22-24`, `dashboard/utils.py:11-15`, `target_calculator.py:49-57`, `grile_monthly.py:159-165`).

### 1.3 Unifică cele două implementări de scope-filter
- `services/filters.py:scoped_clauses` (stil `string_to_array`) vs `repositories/exports.py` (stil `ANY($N::TEXT[])`). Alege una (cea cu `ANY($N::TEXT[])` e mai curată pentru array-uri) și elimină paralela.

## Faza 2 — Refactorări frontend cu leverage mare, risc moderat

### 2.1 Adoptă TanStack Query uniform (ca în `Agents.tsx`) pentru `Dashboard`/`Campaigns`/`Salarii`/`Visite`
- **De ce**: ~400 linii boilerplate duplicat (pattern-ul manual `isMountedRef` + `getCachedView`/`setCachedView`) + race conditions; TanStack Query oferă cache, dedup, invalidare — deja o dependență prezentă și folosită corect în `Agents.tsx`.
- **Impact**: elimină cea mai mare sursă de bug-uri de stale-state pe frontend.

### 2.2 Extrage primitivele shared: `<SideDrawer>`, `<SegmentedTabs>`, `useSortable<T>`, `toneForThreshold(value, tiers)`, `usePersistentState`
- **De ce**: pattern-uri repetate de 4-10 ori fiecare; extragerea deblochează spargerea god-componentelor din Faza 4 (componentele devin mai mici natural când există primitivele).
- `useSortable<T>` singur elimină trio-urile sort-state+handler+memo din ~10 locuri (Dashboard ×6, AgentEvaluation ×2, Salarii ×2, Campaigns/SortableTable).
- `<SideDrawer>` unifică `StoreDetailDrawer`/`AgentDrawer`/`VisitDrawer`/`SalaryDrawer`.
- `<SegmentedTabs>` unifică 5 switchere.
- `usePersistentState` colapsează cele 6 effects de localStorage mirror din `App.tsx` + 4 din `Agents.tsx`.

### 2.3 Șterge dead code-ul
- state `asms` + `aggregateAsms` + `getAsmSortValue` din `Dashboard.tsx` (mort — scris, niciodată citit);
- ramura `per_product_mode` din `dashboard_specials.py:702-727` (liste byte-identice);
- `field_group` din `exports.py:73`;
- `store_join` conditional duplicat în `dashboard.py:14,150,171`.

## Faza 3 — Fix-uri de arhitectură backend (cea mai mare rată de reducere a riscului)

### 3.1 Mută SQL-ul din `services/dashboard/queries.py` în `repositories/dashboard.py` (sau un `repositories/dashboard/queries.py`)
- **De ce**: 1735 linii SQL într-un service = cea mai mare încălcare a regulei din AGENTS.md. Repository-ul `dashboard.py` existent devine sursa unică. Reduce și duplicarea dintre cele două layere (E).
- **Secvență**: mută CTE cu CTE, păstrând semnăturile funcțiilor din service identice (service-ul devine wrapper subțire). Testează cu `pytest` după fiecare grup de funcții mutate.

### 3.2 Creează `repositories/grile_monthly.py` și mută tot SQL-ul din `services/grile_monthly.py`
- **De ce**: singurul domeniu fără repository deloc (1326 linii SQL direct în service). + înlocuiește `time.sleep` (951, 1056, 1149) cu `asyncio.sleep` și `print()` (948, 957-960, 1044, 1070-1078, 1174, 1236-1237) cu logging structurat în aceeași trecere.

### 3.3 Mută SQL din `agents.py` în `repositories/agents.py` (acum pass-through) și extrage CTE-urile duplicate
- **De ce**: `get_agent_evaluation_v2` (557 linii) e negrefactorabilă cât SQL-ul stă în service; deduplicarea CTE-urilor `current_agents` (4×) + `option_query` (2×) + `premium_lines` (2×) reduce dimensiunea cu ~150 linii înainte de spargerea funcției.

### 3.4 Mută SQL din `promo_copurchase.py` și `reporting_refresh.py` în repositories; deduplică cele 3 CTE-uri promo într-un builder
- **De ce**: `promo_copurchase.py` are 3 funcții cu CTE-uri `WITH lines AS (...)`+`discounted AS (...)` aproape identice; un `build_promo_lines_cte(scope_sql)` reduce ~150 linii.

### 3.5 Elimină anti-pattern-ul `join_sql`/`where_sql`/`clauses` injection din `salarii.py`/`dashboard.py`/`campaigns.py` repo
- **Cum**: repo-urile își construiesc clauzele intern dintr-un `ScopeFilters` tipizat (folosind builder-ul unificat din Faza 1.3), nu din string-uri injectate. Elimină cele 11 `.replace()` din `dashboard.py:15-31` (cel mai fragil cod) prin alias-uri consistente în CTE-urile cartela.
- **De ce**: face repo-urile testabile izolat și elimină cuplarea silențioasă de alias. Reduce duplicarea `salary_base` (5×)/`agent_key` (6×)/`MIN_SALARY_FOR_AVERAGE` (8×) din `salarii.py`.

## Faza 4 — Spargerea god-files/components

După Faza 1-3 există helper-ele necesare; acum se pot tăia fișierele mari în siguranță.

### 4.1 `Dashboard.tsx` → `useDashboardData`/`useDashboardHistory` hooks + `<CurrentDashboard>`/`<HistoryDashboard>` + un `<BreakdownTable>` parametrizat
- Tabel RM/Magazine/Agenti current+history devin un component cu props pentru setul de coloane. Colapsează cele 6 clone sort într-un `useSortable`. Estimat **-800 linii**.

### 4.2 `services/agents.py:get_agent_evaluation_v2` (557) → desparte în `build_evaluation_sql()` (repo), `compute_v2_scores(rows)` (scoring Python), `assemble_result()`
- Mută ponderile de scoring (989-993) și pragurile `min_working_days`/`min_receipts` (967-971) în config.

### 4.3 `services/grile_monthly.py:reserve_monthly_operation` (169) → un mic state machine explicit
- `ReservationState` cu `idle/locked/blocked/reserved` în loc de variabile mutabile prin 6 queries.

### 4.4 `services/campaigns.py:get_promotions_incentives` (422) → desparte în `compute_store_promo_incentive` + `compute_agent_promo_incentive` + `categorize_tiers`
- Înlocuiește accesul `store_inc.get(...)[3]` (magic index) cu un dataclass tipizat. Mută la builder-ul de scope unificat (Faza 1.1).

### 4.5 `dashboard_service.py:get_dashboard_all` (318) → `asyncio.gather` dict-keyed + strategie shared de conexiune
- Înlocuiește cele 13 closures + gather pozițional cu gather dict-keyed (rezultate după cheie, nu `results[0]`...`results[14]`); strategie shared de acțiune a conexiunii reduce presiunea pe pool.

### 4.6 `models.py` (901) → desparte pe domenii + validare
- `models/dashboard.py`, `models/agents.py`, `models/campaigns.py`, etc.;
- adaugă `Literal` pe status-uri și `pattern` pe `month: str`;
- desparte `AgentEvaluationV2Row` (47 câmpuri) în `AgentEvaluationV2Metrics` + `AgentEvaluationV2Scores` + `AgentEvaluationV2Row` compunându-le;
- stabilește o ordine de definire care minimizeze forward-ref-urile și adaugă `model_rebuild()` acolo unde e necesar.

### 4.7 Componentele frontend mari (`Campaigns`, `TargetCalculatorSubtab`, `Agents`, `Settings`, `SalariiSubtab`) → desparte pe sub-secțiuni
- Folosește primitivele din Faza 2.
- Convertește ref-mirror state din `TargetCalculatorSubtab` (`scenarioRef`/`dirtyRowsRef`/`editVersionsRef` sincronizate manual la 433-435, 578, 603, 633) într-un singur `useReducer` — elimină hazardul de stale-closure.
- Înlocuiește cele două sisteme de sortare paralele din `AgentEvaluationSubtab` (`SortKey`/`V2SortKey`, 380-517) cu un `useSortable` parametrizat.
- Mută textul hardcoded al regulilor de scor din `NewEvaluationSubsection:698-785` într-un config array.

## Faza 5 — Type safety, error handling, security

### 5.1 Refactor `client.ts`
- Tipizează corect (`<T>` fără `any` default);
- introdu `ApiError` cu `status` + corp parsat (switch pe status la caller);
- resetează latch-ul `unauthorizedRedirectStarted` (14) la re-auth;
- un helper `buildUrl(url, params)` pentru toate verbele (incl. PUT/PATCH/DELETE care acum nu suportă params → workaround `crm.ts:43`).

### 5.2 Repo `target_calculator.py:finalize_scenario` → rezultate distincte
- Excepții tipizate în loc de bare `False`, ca router-ul să poată distinge 409 (stale revision) vs 422 (validare).

### 5.3 `auth.py`
- Elimină client_id default (40) — fail-closed fără env;
- rezervă localhost bypass (130-137) doar cu secret rotativ sau elimină-l dacă nu mai e necesar;
- adaugă `asyncio.Lock` pe `_fetch_jwks` și max-stale bound pe fallback;
- un singur sursă de adevăr pentru issuer (mută URL-urile hardcodate din `main.py:303-304` să folosească `OIDC_ISSUER`).

### 5.4 `rate_limits.py`
- Migrează la un backend shared (Valkey/DB) pentru limita globală reală across workers;
- adaugă evictare pe bucket-urile goale din `_hits`;
- validează origin înainte de a trust-a `cf-connecting-ip`/`x-forwarded-for`.

### 5.5 `visits_report.py`
- Paths din env (`VISITS_DB_PATH`/`VISITS_IMAGES_DIR` există deja în config — folosește-le la 7-8);
- mută `_aggregate_report_rows` (161-212) în service — repo-ul returnează rows, service-ul agregă.

## Faza 6 — Curățenie finală

- Mută toate magic literals business în config/constante numite (praguri incentive `0.99/0.89`, baseline `'2025-01'`, ponderi scoring, floor `35000`, ferestre 12/15/16 luni, `LIMIT 8`, top-5, `promo_impact 20%`, epsilon `0.01`, praguri complianță `80/50`, praguri culoare scor).
- Elimină cache-urile module-level fără lock sau adaugă `asyncio.Lock` (`promo_copurchase:46`, `dashboard_specials:22`, `auth:44`).
- Centralizează cheile de query TanStack într-un factory `queryKeys` (tipizat, compile-checked) ca să nu se mai typo-eze invalidările.
- Unifică prefix-ul de rută `/api/` (`salarii.ts` e outlier — 6 endpoint-uri fără `/api/`) și centralizează rutele per-resursă.
- Unifică `MANAGEMENT_ACCESS_GROUPS`/`SALARY_ACCESS_GROUPS` dacă intenția de divergență nu se materializează (sau adaugă comentariu care documentează intenția) și sincronizează mesajele user-facing cu seturile permise.
- Mută side effects din `main.py` import-time (`load_dotenv`/`setup_logging`/`sentry_sdk.init`) într-un `bootstrap()` apelat explicit din `lifespan`.
- Centralizează politica de cache SPA no-cache (un singur loc, nu `main.py:147-153` + `340-352`).
- Curăță `SELECT *` din `grile.py:252,262,269,278` și `hr.py:141` — enumeră coloane.

---

## Rezumat al ordinii (de ce în această secvență)

1. **Faza 0-1** pun fundația (helpers shared, eliminare duplicare de bază) — risc mic, deblochează tot restul.
2. **Faza 2-3** atac duplicarea structurală (TanStack uniform, SQL în repositories, eliminarea fragment-injection) — cea mai mare reducere de risc arhitectural.
3. **Faza 4** sparge god-files acum că helper-ele există — altfel spargerea ar recrea duplicare.
4. **Faza 5-6** curățenie de calitate (type safety, security, magic literals) — cel mai bine făcute după ce structura e stabilă.

---

## Note pentru agentul de double-check

- **NU s-a modificat codul** — analiză read-only.
- Toate referințele sunt `file:line` și au fost verificate prin citire efectivă (cu `Read` + offset pentru fișierele mari).
- Sursele de context: `README.md`, `APP_ARCHITECTURE.md`, `AGENTS.md`, `docs/retail-org-analysis.md`, `docs/RUNBOOK-campanii-promo-incentive-concursuri.md`.
- Validare propusă pentru orice pas de refactor executat ulterior: `npm run typecheck` + `npm run typecheck:strict` + `npm run lint` + `npm run test` + `pytest backend/tests/ -q` + `mypy backend/ --ignore-missing-imports --explicit-package-bases` + `npm run build` (rulează secvențial — typecheck poate race cu Vite build cât `dist/` se regenerează).
- Invariante business de respectat la refactor (din AGENTS.md): site_code domină scope istoric; excludere Cartele + `TR %`; builder-ele de scope canonice; fără param asyncpg unused; timeout-uri DB doar prin `DB_*_TIMEOUT_MS`; media salarială exclude sub 2000 RON doar din medii; `total_salary` include bonuri masă; alocare target = store target / store selling days × agent selling days; grile `YYYY-MM` + cel mult un run `queued/running` per lună; Calculator Target un draft per lună + revision pentru stale writes (409); promo qualifying receipts ≠ incentive quantity; vizite grupate după TL snapshot-ul autorului.
