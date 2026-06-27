# UniHub Retail — Audit post-refactor + plan nou

> Context: agentul primar a implementat prima transană din `docs/refactoring-roadmap-2026-06-26.md` (Etapa 1 + părți din Etapa 3). Acest document = (1) verdict pe lucrarea agentului primar, (2) audit complet proaspăt pe starea curentă, (3) plan actualizat.
> Data auditului: 2026-06-27
> Toate referințele sunt `file:line` verificate prin citire/grep. Codul nu a fost modificat.

---

## Partea 1 — Verdict pe lucrarea agentului primar

### Verdict general: CORECT și bine executat.

Agentul primar a făcut un double-check al `CODE_REVIEW.md`, a ajustat corect 3 puncte din review (vezi mai jos), a scris un roadmap executabil și a implementat Etapa 1 + două piese din Etapa 3. Validările reclamate sunt reale (am rulat `npm run typecheck` + `npm run lint` — curat; roadmap-ul documentează `pytest 535 passed/7 skipped`, `mypy` OK, `build` OK, serviciu repornit, health OK).

### Ce s-a implementat corect (verificat)

| Livrabil | Verificare | Status |
|---|---|---|
| `backend/retail_filters.py` — sursă unică `TR %` + `NOT is_cartela` | Adoptat în 8 fișiere (filters, exports, contests, target_calculator, visits, reporting_refresh, campaigns, repositories/filters). Niciun literal `'TR %'` rămas în sursă non-test. | OK |
| `is_cartela` cu dublă semantică | Helper-ul e folosit doar pentru excludere (`NOT is_cartela`); cazurile de includere (`is_cartela = true` pt. card Cartele — `queries.py:1209`, `dashboard.py:93`, `target_calculator.py:434`) sunt lăsate raw, corect (excepția documentată). | OK |
| `src/lib/dates.ts` (luni RO + `formatMonthLabel` + `shiftMonth`) + `src/lib/download.ts` (`downloadBlob` cu append la DOM) | Fișiere noi, test `dates.test.ts` adăugat. | OK |
| `src/api/client.ts` — `buildUrl` comun, default generic `unknown`, params pe toate verbele, handling 204/empty, reset latch 401 pe non-401 + la `setAccessTokenProvider` | Verificat `client.ts:35-50` (`buildUrl`), `60-68` (latch), `101/114/129/143/157` (toate verbele cu params). | OK |
| Generice pe apelurile netipizate `hr`/`tasks`/`crm`/`salarii`/`grile`/`targetCalculator` | `hr.ts:23` `<LeaveRequest[]>`, `tasks.ts:35` `<Task[]>`, `crm.ts:38` `<StoreScore[]>` etc. — toate au generice explicite. | OK |
| `ALL_FIRMS`/`ALL_SCOPE`/`ALL_STORES` în `Agents.tsx` | Import la linia 24; folosite la 330-333 (query principal) și 473-476 (title). | OK |
| Paths Vizite din env/config | `repositories/visits_report.py:7` importă `get_visits_db_path`/`get_visits_images_dir` din `config.py`; `config.py:28-33` citește env cu fallback. | OK |
| OIDC discovery rewrite prin JSON parse | `main.py:303` `json.loads`, `313` `json.dumps`. | OK |
| `build_scoped_params` public + adoptat | Definit `services/filters.py:48`; folosit în `campaigns.py:52,259,433,508,581`, `dashboard_service.py:74,131,218`, `queries.py` (16 call-site-uri), `premium_glass.py:43`, `promo_copurchase.py:313,414,530,642`, `specials_data.py:76`. | OK |
| `_campaign_clauses` consolidat | `campaigns.py:42-68` acum deleghează la `build_scoped_params`+`scoped_clauses` (nu mai e loop manual); comentariul "Mirror exact" a dispărut. | OK |
| Mutare SQL top-agent-incentive din service în repo | `repositories/campaigns.py:176` `fetch_incentive_agent_rows`; `services/campaigns.py` nu mai are `conn.fetch` raw. | OK |
| `asyncio.sleep` în flow-urile async Grile | `grile_monthly.py:951,1056` convertite. | OK |

### Ajustări corecte făcute de agentul primar la `CODE_REVIEW.md`

1. **Rate limiter per-proces** — nu e bug activ acum (`systemd` rulează `uvicorn --workers 1`). Corect — rămâne datorie doar la trecerea la multi-worker.
2. **`/salarii` fără `/api/`** — nu e bug; router montat intenționat `prefix="/salarii"` (`routers/salarii.py:13`). Corect.
3. **`_DISTRIBUTION_LOCATION_PREFIX` privat** — a făcut helper public `retail_filters.py` (nu import peste tot din `_...`). Corect, mai bine decât propunerea originală.

### Observații / mici probleme (nu blochează)

1. **`time.sleep` în `grile_monthly.py:261` și `grile_agent_targets.py:431` — lăsate corect.** Am verificat: `retry_api` (`grile_monthly.py:253`) e **sync** și e apelat din funcții sync (`extract_store_rows`, `archive_month`, `reset_month`) care rulează în thread-uri via `asyncio.to_thread`/`run_monthly_op`. `grile_agent_targets.py:431` e în closure-ul sync `fetch` rulat via `await asyncio.to_thread(fetcher, ...)` la linia 392. Deci `time.sleep` acolo NU blochează event loop-ul. **Agentul primar a făcut distincția corectă** — a convertit doar sleep-urile în context async real (951, 1056). *Notă: `CODE_REVIEW.md` original a fost imprecis pe `grile_agent_targets:431` — era deja în `to_thread`.*
2. **`Agents.tsx` mai are literal `'Toate'`/`'Toti'`** la 323, 324, 395, 399, 964, 996, 1018 — dar pentru `cardFirma`/`cardMagazin` (sub-filtru local de card), nu pentru filtrele principale. Inconsistent dar prioritate mică.
3. **`build_scoped_params` are două entry points**: `services/filters.py:48` (public) și `services/dashboard/utils.py:27` `_build_scoped_params` (wrapper privat). Multe fișiere importă wrapper-ul privat din `dashboard.utils`. Funcționează, dar ar trebui un singur entry point public.
4. **`parseResponse` returnează `undefined as T`** (`client.ts:72,80`) pentru 204/empty — type lie minor, trade-off acceptabil.
5. **`print()` în `grile_monthly.py` (15 ocurențe)** — netratat în Etapa 1 (roadmap-ul menționa doar "Grile async sleep"). Capturate via `contextlib.redirect_stdout` în `run_monthly_op:1285`, deci funcționează, dar e brittel vs. logging structurat. Datorie rămasă.

### Concluzie Partea 1: lucrarea agentului primar e solidă, fără regresii, cu ajustări mai bune decât review-ul original. Se poate continua pe roadmap.

---

## Partea 2 — Audit complet proaspăt (stare curentă)

### Ce s-a rezolvat din `CODE_REVIEW.md` (Etapa 1 + partial Etapa 3)

- B1 (scope params reimplementați ~9×) — **parțial rezolvat**: `build_scoped_params` adoptat în campaigns/dashboard/premium_glass/promo_copurchase/queries. _Încă rămas_: `agents.py:1306-1318` (`get_stores_coverage` are loop propriu), `dashboard_service.py:get_history_by_year` (are 2 loop-uri cu offset diferit — cazul 2-aliase justificat parțial), `repositories/exports.py` (folosește alt stil `ANY($N::TEXT[])`, parallel impl).
- B1 (`'TR %'` în 9+ fișiere) — **rezolvat**.
- B1 (`is_cartela` scatter) — **rezolvat** pentru excludere; includerea lăsată intenționat.
- B2 (array luni RO duplicat) — **rezolvat** (`dates.ts`).
- B2 (blob-download ×5) — **parțial**: `download.ts` există, dar nu am verificat că toate cele 5 call-site-uri (`targetCalculator.ts`, `grile.ts`, `tableExport.ts`, `Settings.tsx`, `VisiteSubtab.tsx`) migrează. Necesită verificare.
- B2 (formatters locale shadow) — **parțial**: `lib/formatters.ts` are `formatAmount` nou (commit `dd3d73e`), dar `SalariiSubtab`/`AgentEvaluation`/`Agents` încă pot avea duplicate locale.
- B2 (`LoadingCard`/`ErrorCard`/`Metric` duplicate în Campaigns) — **de verificat** (commit `dd3d73e` atinge Campaigns.tsx).
- F (client.ts `any`) — **rezolvat** (`unknown` default + generice).
- F (generice hr/tasks/crm) — **rezolvat**.
- F (latch 401 never reset) — **rezolvat**.
- G (visits paths hardcodate) — **rezolvat**.
- G (OIDC rewrite string replace) — **rezolvat**.
- D (time.sleep în async Grile) — **rezolvat** pentru contextele async reale.

### Ce a rămas NEREZOLVAT (datoria structurală mare — explicit în Etapele 2-6 din roadmap)

Acestea sunt cele mai mari riscuri rămase, în ordinea impactului:

#### A. God-files/components — neatinse (dimensiuni identice)
| Fișier | Linii | Cea mai mare unitate |
|---|---|---|
| `src/components/Dashboard.tsx` | 2663 | componenta ~2021 linii, ~45 useState |
| `backend/services/dashboard/queries.py` | 1735 | `_fetch_regional_stats` 201 |
| `backend/services/agents.py` | 1407 | `get_agent_evaluation_v2` **557** |
| `backend/services/grile_monthly.py` | 1326 | `reserve_monthly_operation` 169, **fără repo** |
| `src/components/Campaigns.tsx` | 1652 | componenta ~766 |
| `src/components/TargetCalculatorSubtab.tsx` | 1370 | componenta ~1005 |
| `backend/models.py` | 901 | 47-field `AgentEvaluationV2Row` |
| `src/components/AgentEvaluationSubtab.tsx` | 1121 | 2 sisteme de sortare paralele |
| `src/components/Agents.tsx` | 1064 | componenta ~767 |

#### B. Arhitectură backend — încălcări majore rămase
- **`repositories/dashboard.py:15-31` — 11 lanțuri `.replace()` pe SQL** (14 ocurențe `.replace(` încă prezente). Cel mai fragil cod din codebase. **Netratat.**
- **`dashboard_service.py:get_dashboard_all` — 13 closures async + `asyncio.gather` pozițional** (`results[0]`...`results[14]` cu `# type: ignore`). 16 match-uri `asyncio.gather`/`results[`. **Netratat.**
- **SQL în services**: `queries.py` (tot), `agents.py` (repo pass-through), `grile_monthly.py` (**fără repo deloc**), `promo_copurchase.py` (fără repo), `reporting_refresh.py` (fără repo). **Netratat.**
- **Anti-pattern `join_sql`/`where_sql`/`clauses` injection** în `repositories/salarii.py` (8 metode), `dashboard.py` (3 metode), `campaigns.py` (încă 5 metode — doar `fetch_incentive_agent_rows` mutat). **Parțial: 1 din ~14 mutat.**
- **Două implementări paralele scope-filter**: `services/filters.py:scoped_clauses` (stil `string_to_array`) vs `repositories/exports.py` (stil `ANY($N::TEXT[])`). **Netratat.**

#### C. Frontend structural — neatins
- Pattern manual fetch+cache+`isMountedRef` în `Dashboard.tsx`/`Campaigns.tsx` (~400 linii) vs TanStack Query în `Agents.tsx`. **Netratat.**
- Drawer/overlay repetat ×4, SegmentedTabs ×5, sort trio ×10, `usePersistentState` lipsă. **Netratat (Etapa 2).**
- `App.tsx` god component (12 useState + 11 useEffect + global CustomEvent bus). **Netratat.**
- `SortableTable` forțează ~25 cast-uri `as unknown as`. **Netratat.**

#### D. Type safety & eroare — parțial
- `ApiError` tipizat cu `status` + corp parsat — **lipsă** (`client.ts:67` încă `throw new Error('API error: N')`). Etapa 5.
- `auth.py:40` client_id default real (fail-open) — **netratat**.
- `auth.py:130-137` localhost bypass admin — **netratat**.
- JWKS cache fără lock/max-stale — **netratat**.
- `models.py` lipsă validare (`month` fără pattern, `target_value` fără `>=0`, status-uri plain str). **Netratat.**

#### E. Alte datorii rămase
- **`print()` în `grile_monthly.py` (15×)** în funcții async/run-in-thread — capturate via `redirect_stdout` dar brittel. Nu e în nicio etapă din roadmap explicit. **Gap în roadmap.**
- **Magic literals business** (praguri incentive `0.99/0.89`, baseline `'2025-01'` ×7, ponderi scoring, floor `35000`, ferestre 12/15/16 luni, `LIMIT 8`, `promo_impact 20%`, epsilon `0.01`). **Netratat (Etapa 6).**
- **Caches module-level fără lock** (`promo_copurchase:46`, `dashboard_specials:22`, `auth:44`). **Netratat.**
- **Query keys TanStack inline** fără factory. **Netratat.**
- **`SELECT *`** în `grile.py:252,262,269,278`, `hr.py:141`. **Netratat.**
- **`rate_limits.py` per-proces** — datorie doar la multi-worker (corect amânat).
- **`_aggregate_report_rows` business logic în `repositories/visits_report.py`**. **Netratat.**
- **`finalize_scenario` întoarce bare `False`** (pierde 409 vs 422). **Netratat.**
- **`agents.py:133`** `c.replace("import_month = $1", ...)` string surgery pe SQL. **Netratat.**
- **`main.py` side effects la import-time**. **Netratat.**

### Itemi noi / sub-weighted în roadmap-ul curent

1. **`print()` → logging structurat în `grile_monthly.py`** — nu e în nicio etapă. Ar trebui adăugat (azi se captează prin `redirect_stdout`, brittel).
2. **Consolidare entry point `build_scoped_params`** — două definiții (`filters.py:48` public + `dashboard/utils.py:27` privat). Unify imports.
3. **Verificare migrare efectivă a `downloadBlob`** în toate cele 5 call-site-uri (roadmap claim "folosesc helper-ele comune" —需 verify `targetCalculator.ts`, `grile.ts`, `tableExport.ts`, `Settings.tsx`, `VisiteSubtab.tsx` chiar importă `download.ts`).
4. **Verificare migrare `LoadingCard`/`ErrorCard`/`Metric`** din Campaigns în `DashboardWidgets` (commit `dd3d73e` atinge Campaigns dar nu e clar că duplicatele au fost șterse).
5. **`get_stores_coverage` (`agents.py:1306-1318`)** — încă are loop propriu de scope, nu folosește `build_scoped_params`. Omis din Etapa 3.
6. **`repositories/exports.py`** — încă are stil parallel `ANY($N::TEXT[])` + boilerplate filtru ×3. Nu e menționat explicit în Etapa 3 (care zice doar "campaigns și salarii întâi").

---

## Partea 3 — Plan actualizat

Roadmap-ul existent (`docs/refactoring-roadmap-2026-06-26.md`) e bun și direcția corectă. Planul de mai jos **refină și extinde** cu itemii noi identificați, păstrând numerotarea etapelor pentru continuitate. Fiecare pas are criteriu de ieșire și validare secvențială: `npm run typecheck` → `npm run typecheck:strict` → `npm run lint` → `npm run test` → `pytest backend/tests/ -q` (sau `run_tests_isolated.sh`) → `mypy backend/ --ignore-missing-imports --explicit-package-bases` → `npm run build` → `sudo systemctl restart unihub-backend` → `curl -fsS http://127.0.0.1:9898/health`.

### Etapa 1.5 — Închidere gaps din prima transană (risc mic, înainte de a porni Etapa 2)

1. **Verifică și completează migrarea `downloadBlob`** în `targetCalculator.ts:196`, `grile.ts:162`, `tableExport.ts:60`, `Settings.tsx:277`, `VisiteSubtab.tsx:34`. Dacă unele nu importă `lib/download.ts`, migrează-le. Șterge pattern-ul inline.
2. **Verifică și completează migrarea `LoadingCard`/`ErrorCard`/`Metric`** din `Campaigns.tsx:1409-1439` → import din `DashboardWidgets`. Șterge redefinițiile.
3. **Verifică formatters locale** în `SalariiSubtab.tsx:51-66`, `AgentEvaluationSubtab.tsx:14-30`, `Agents.tsx:37-38` — migrează la `lib/formatters`/`lib/dates` dacă nu s-a făcut.
4. **Consolidează entry point `build_scoped_params`**: un singur loc public (`services/filters.py`); redenumește importurile din `dashboard/utils.py` să pointeze direct la cel public; transformă `_build_scoped_params` în alias de compatibilitate sau șterge-l.
5. **Migrează `agents.py:1306-1318` (`get_stores_coverage`)** la `build_scoped_params` — omis din prima transană.
6. **Înlocuiește `'Toate'`/`'Toti'` rămas** în `Agents.tsx:323,324,395,399,964,996,1018` cu o constantă locală `ALL_CARD = 'Toate'` (sau folosește `ALL_FIRMS`/`ALL_STORES` dacă semantically se potrivește).
- **Criteriu**: typecheck + lint + test + pytest trec; `grep -rn "createObjectURL" src/` returnează doar `lib/download.ts`.

### Etapa 2 — Primitive frontend comune (ca în roadmap, + 1 item)

1. `useSortable<T>` (elimină ~10 trio-uri sort-state+handler+memo).
2. `<SegmentedTabs>` (unifică 5 switchere).
3. `<SideDrawer>` (unifică 4 drawer-e).
4. `usePersistentState` (colapsează 6 effects în `App.tsx` + 4 în `Agents.tsx`).
5. **(Nou)** Extract `useDashboardData`/`useDashboardHistory` hook-uri cu TanStack Query care înlocuiesc pattern-ul manual `isMountedRef`+`getCachedView` din `Dashboard.tsx:709-931` și `Campaigns.tsx:151-292`. Fă asta **înainte** de spargerea componentelor (Etapa 4), altfel spargerea recrează duplicarea.
6. **(Nou)** `queryKeys` factory tipizat pentru TanStack (elimină literal-urile inline `['agents','overview',...]`).
- **Criteriu**: `Dashboard.tsx`/`Campaigns.tsx` nu mai au `isMountedRef`/`getCachedView` pentru fluxurile principale; typecheck:strict + test trec.

### Etapa 3 — Backend scope + repository boundaries (ca în roadmap, + 2 itemi)

1. **`ScopeFilters` tipizat** (dataclass/Pydantic) + un singur builder public care produce `(params, clauses, positions)`.
2. **Elimină `join_sql`/`where_sql`/`clauses` injection** din `repositories/salarii.py` (8 metode), `dashboard.py` (3 metode), `campaigns.py` (5 metode rămase). Repo-urile își construiesc clauzele intern din `ScopeFilters`.
3. **Elimină cele 11 `.replace()` din `repositories/dashboard.py:15-31`** prin alias-uri consistente în CTE-urile cartela (generează clauze pentru alias-ul corect, nu realias-uire string). **Prioritate mare — cel mai fragil cod.**
4. **(Nou) Unifică stilul paralel din `repositories/exports.py`** (`ANY($N::TEXT[])` + boilerplate ×3) cu builder-ul canonical.
5. **(Nou) Mută `get_history_by_year` (`dashboard_service.py:247-366`)** pe builder-ul unificat — cele 2 loop-uri cu offset diferit sunt un caz justificat (2 alias-e) dar trebuie modelat explicit în `ScopeFilters` (suport multi-alias), nu ca excepție ad-hoc.
6. Refactorizează campaigns repo (parțial început) și salarii repo întâi (suprafață mai mică decât dashboard).
- **Criteriu**: `grep -rn "join_sql\|where_sql\|\.replace(\"agg" backend/repositories/` = 0; niciun param asyncpg unused; mypy + pytest trec.

### Etapa 4 — Spargerea god-files (ca în roadmap, + ordonare)

Ordine recomandată (de la cel mai izolat la cel mai cuplat):
1. **`grile_monthly.py`** → separă `repositories/grile_monthly.py` (SQL) + state machine explicit pentru `reserve_monthly_operation` (înlocuiește variabilele mutabile `reservation`/`blocked_message`/`operation_id` cu `ReservationState` enum). Înlocuiește `print()` cu logging structurat în aceeași trecere (**itemul nou din roadmap**).
2. **`models.py`** → desparte pe domenii (`models/dashboard.py`, `models/agents.py`, etc.) + validare `Literal`/`pattern` + desparte `AgentEvaluationV2Row` (47 câmpuri) în Metrics+Scores+Row.
3. **`services/agents.py:get_agent_evaluation_v2` (557)** → `build_evaluation_sql()` (repo) + `compute_v2_scores(rows)` + `assemble_result()`. Mută ponderile scoring în config. Deduplică `current_agents` CTE (×4) + `option_query` (×2) + `premium_lines` (×2).
4. **`services/campaigns.py:get_promotions_incentives` (422)** → `compute_store_promo_incentive` + `compute_agent_promo_incentive` + `categorize_tiers`; înlocuiește `store_inc.get(...)[3]` (magic index) cu dataclass.
5. **`dashboard_service.py:get_dashboard_all` (318)** → `asyncio.gather` dict-keyed + strategie shared de conexiune (reduce presiune pool).
6. **`Dashboard.tsx`** → `<CurrentDashboard>`/`<HistoryDashboard>` + `<BreakdownTable>` parametrizat (tabel RM/Magazine/Agenti current+history devine un component). -800 linii estimate.
7. **`Campaigns.tsx`**, **`TargetCalculatorSubtab.tsx`** (ref-mirror state → `useReducer`), **`Agents.tsx`**, **`Settings.tsx`**, **`SalariiSubtab.tsx`** → desparte pe sub-secțiuni cu primitivele din Etapa 2.
8. **`App.tsx`** → `usePersistentState` + `useAppNavigation` reducer + navigation context (înlocuiește global CustomEvent bus).
- **Criteriu**: fiecare fișier mare scade fără schimbare de payload; testele domeniului + typecheck trec după fiecare mutare.

### Etapa 5 — Hardening API, auth, rate limits (ca în roadmap)

1. `ApiError` frontend cu `status` + corp JSON parsat; `client.ts` fără `any`/`as unknown as T` pe blob.
2. `auth.py:40` — elimină client_id default (fail-closed).
3. `auth.py:130-137` — localhost bypass: secret rotativ sau elimină.
4. JWKS cache: `asyncio.Lock` + max-stale bound.
5. `repositories/target_calculator.py:finalize_scenario` — excepții tipizate (409 vs 422) în loc de bare `False`.
6. `rate_limits.py` — backend shared (Valkey) **doar dacă** se trece la multi-worker.
7. `repositories/visits_report.py` — mută `_aggregate_report_rows` în service.
8. `main.py` — mută side effects din import-time în `lifespan`/`bootstrap()`.
- **Criteriu**: teste auth/client/rate-limit acoperă cazurile noi; fără relaxare OIDC.

### Etapa 6 — Curățenie finală (ca în roadmap, + itemi)

1. Magic literals → constante/config numite (praguri incentive, baseline `'2025-01'`, ponderi scoring, floor, ferestre, `LIMIT`, epsilon, praguri culoare scor, praguri complianță vizite).
2. Caches module-level → `asyncio.Lock` (`promo_copurchase`, `dashboard_specials`, `auth`).
3. `SELECT *` eliminat din `grile.py`/`hr.py`.
4. Documentație actualizată.
5. **(Nou)** `agents.py:133` `c.replace("import_month = $1", ...)` → query parametric separat, nu string surgery.
6. **(Nou)** Unifică `MANAGEMENT_ACCESS_GROUPS`/`SALARY_ACCESS_GROUPS` (sau documentează intenția de divergență) + sincronizează mesajele user-facing cu seturile permise.

---

## Partea 4 — Recomandare execuție

1. **Începe cu Etapa 1.5** (închidere gaps) — risc minim, confirmă că prima transană e completă. ~1-2 ore.
2. **Apoi Etapa 3 prioritar, nu Etapa 2** — argument: cele 11 `.replace()` din `dashboard.py:15-31` sunt cel mai fragil cod din codebase (bug silențios la schimbare de alias). Frontend primitives (Etapa 2) pot aștepta; acest risc backend nu should. Totuși, Etapa 3 e mai mare, deci dacă se vrea paralelizare: Etapa 2 (frontend) și Etapa 3 (backend) sunt independente și pot merge în paralele pe două fire.
3. **Etapa 4** după ce 2+3 fundamentează (altfel spargerea recrează duplicare).
4. **Etapa 5+6** la final.

**Prioritatea absolută #1 dacă se face un singur lucru:** eliminarea celor 11 `.replace()` din `repositories/dashboard.py:15-31` (Etapa 3.3). E cel mai fragil cod, cu mode de eșec silențios, și singurul care poate produce bug-uri de raportare greu de detectat la o schimbare de alias.

---

## Note pentru agentul care execută

- Nu combina refactorizări structurale cu schimbări business.
- Păstrează contractele API/payload până la un motiv explicit.
- Preferă helper-e publice și testate.
- SQL se mută pe domenii mici, nu printr-o mutare masivă.
- Validare secvențială (typecheck poate race cu Vite build cât `dist/` se regenerează).
- Invariante business (AGENTS.md): `site_code` domină scope istoric; excludere Cartele + `TR %` (acum via `retail_filters.py`); fără param asyncpg unused; timeout-uri DB doar prin `DB_*_TIMEOUT_MS`; media salarială exclude sub 2000 RON doar din medii; `total_salary` include bonuri masă; alocare target = store target / store selling days × agent selling days; grile `YYYY-MM` + cel mult un run `queued/running` per lună; Calculator Target revision pentru stale writes (409); promo qualifying receipts ≠ incentive quantity; vizite grupate după TL snapshot-ul autorului.
