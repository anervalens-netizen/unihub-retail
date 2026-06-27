# Handover catre Codex — Refactoring transa 2 (2026-06-27)

> Acest document este handover-ul de la opencode (agent de revizuire) catre Codex
> (agent primar) pentru verificarea si continuarea refactoring-ului Retail.
> Citeste `REFACTORING_PLAN_V2.md` pentru planul complet si `docs/refactoring-
> roadmap-2026-06-26.md` pentru status actualizat.

## Context

1. Am analizat codul din `/opt/Mobiup/unihub-retail` (audit in `CODE_REVIEW.md`).
2. Codex a implementat transa 1 (Etapa 1 + partial Etapa 3) — corect, fara regresii.
3. Am facut double-check pe lucrarea Codex (`AUDIT_POST_REFACTOR.md`) — verdict: corect.
4. Am construit un plan verificat (`REFACTORING_PLAN_V2.md`) cu 4 subagenti care au
   validat zonele riscante si au corectat 3 recomandari nesigure.
5. Am executat transa 2 din plan (Pasul 1.4 + Pasul 0.2 + Pasul 3.1).

## Ce s-a implementat in transa 2

### Pasul 1.4 — Consolidare `build_scoped_params` (mecanic, sigur)

- `_build_scoped_params` din `services/dashboard/utils.py` era un wrapper passthrough
  la `build_scoped_params` din `services/filters.py`.
- Transformata din functie wrapper in import alias direct:
  `from services.filters import build_scoped_params as _build_scoped_params`.
- Elimina indirection-ul fara sa atinga cele 30+ call-site-uri. Zero risc.
- Validat de subagent: wrapper-ul era passthrough pur, toate call-site-urile folosesc
  kwargs, niciun risc de shiftare pozitionala asyncpg.

### Pasul 0.2 — Teste de integrare pentru `fetch_summary` (safety net)

Fisier nou: `backend/tests/test_dashboard_summary_integration.py` (5 teste).

Aceste teste seed-uiesc DB izolat (prin `run_tests_isolated.sh`) si valideaza
comportamentul `fetch_summary` INAINTE de refactor:

1. `test_cartela_does_not_contaminate_retail_totals` — Cartele nu contamineaza
   Retail totals (`total_sales`, `total_quantity`); `cartele_qty` e separat.
2. `test_cartela_respects_site_code_scope` — Cartela cohort respecta site_code.
3. `test_forecast_math_partial_month` — Forecast math: `total_sales / last_day *
   days_in_month` pentru luni partiale.
4. `test_manager_scope_or_expansion_applies_to_cartela` — Manager-scope OR-expansion
   (regional OR asm) se aplica si cartela CTE, nu doar Retail totals. **Acesta e
   testul care protejeaza subtilitatea refactorului `.replace()`.**
5. `test_tr_percent_locations_excluded_from_retail` — `TR %` locations excluse.

Toate 5 trec pe codul vechi (cu `.replace()`) si pe codul nou (cu `cartela_clauses`).

### Pasul 3.1 — Eliminat `.replace()` din `fetch_summary` (PRIORITATEA #1)

**Cel mai fragil cod din codebase** — 11 lanturi `.replace()` pe clauze SQL pentru
a realias-ui `s.`→`cs.` si `agg.`→`c.` pentru cartela CTE.

**Abordare** (verificata de subagent, mirror al pattern-ului deja probat in
`queries.py:1188-1211`):

1. Parametrizat `_expand_current_manager_scope` cu `store_alias: str = "s"` (default
   backward-compatible; cartela foloseste `store_alias="cs"`).
2. In `dashboard_service.py:get_summary`, dupa build `clauses`, build `cartela_clauses`
   separat cu `scoped_clauses(positions, site_alias="c", store_alias="cs",
   agent_alias="c")` + `_expand_current_manager_scope(..., store_alias="cs")` +
   `cs.is_active = true` (cand `current_scope` + `!include_closed_stores`).
3. Schimbat semnatura `fetch_summary(self, clauses, params, cartela_clauses,
   current_scope=False)` si **sters loop-ul `.replace()`** (liniile 15-31 vechi).
4. `cartele_summary` CTE foloseste `cartela_clauses` direct.

**Ce NU s-a atins** (conform planului):
- `fetch_monthly_history:172` si `fetch_year_history_monthly:279` — alt mecanism
  (alias swap pt store_targets, risc mic). Ramane pentru curatenie ulterioara.

## Ajustari ale planului (corectate de subagenti)

3 recomandari din `AUDIT_POST_REFACTOR.md` au fost verificate de subagenti si
corectate ca nesigure. **NU le implementa:**

1. **`print()` in `grile_monthly.py` — NU inlocui cu logging.** Subagentul a
   descoperit ca output-ul e load-bearing: e capturat in `result.output`, stocat
   in `grile_monthly_operations.result` (JSONB), returnat prin API si afisat in UI
   (`GrileMonthlyPanel.tsx:244-247`). Testul `test_grile_monthly_service.py:774`
   aserteaza pe `result["output"]`. Inlocuirea ar goli panoul de progres al
   adminului + ar sparge testul. Daca se vrea logging structurat: dual-write
   (`print()` + `logger.info`), aditiv, zero-risc.

2. **`get_stores_coverage` (`agents.py:1303`) — NU migra la `build_scoped_params`.**
   Subagentul a confirmat ca are comportament genuin diferit: sentinel
   field-specific (`firma!="Toate"`, `regional!="Toti"` fara diacritice) vs
   `normalize_filter` (set mai larg incluzand `Toți`); SQL scalar `=` vs
   `= ANY(...)`; nu are retail exclusion clause. Migrarea ar schimba silențuis
   care input-uri sunt tratate ca "no filter" + ar injecta `TR %` exclusion.

3. **`ScopeFilters` dataclass — NU introduce.** Subagentul a confirmat ca e
   riscant: nu acopera `current_scope`/`include_closed_stores` (sunt clause
   concerns, aplicate in 3 locuri diferite) si `initial_params` (variază 1-6
   elemente cu semantici diferite); ~25 call-site-uri de schimbat cu risc real de
   shiftare pozitionala asyncpg. `build_scoped_params` cu kwargs e deja sigur.

## Validari rulate (toate verzi)

```bash
npm run typecheck                    # OK
npm run typecheck:strict             # OK
npm run lint                         # OK
npm run test                         # OK, 11 fisiere / 134 teste
backend/scripts/run_tests_isolated.sh  # OK, 540 passed / 7 skipped
mypy backend/ --ignore-missing-imports --explicit-package-bases  # OK, 154 files
npm run build                        # OK
sudo systemctl restart unihub-backend
curl -fsS http://127.0.0.1:9898/health  # {"status":"ok"}
```

Logs backend curate (nicio eroare, 401 corect pe dashboard endpoints care
necesita auth OIDC).

## Fisiere modificate in transa 2

- `backend/services/dashboard/utils.py` — `_build_scoped_params` → import alias;
  `_expand_current_manager_scope` → parametrizat cu `store_alias`.
- `backend/services/dashboard_service.py` — `get_summary` construieste
  `cartela_clauses` separat si le passeaza la `fetch_summary`.
- `backend/repositories/dashboard.py` — `fetch_summary` semnatura schimbata
  (accepta `cartela_clauses`); sters loop-ul `.replace()` (11 lanturi).
- `backend/tests/test_dashboard_summary_integration.py` — **fisier nou**, 5 teste
  de integrare.
- `docs/refactoring-roadmap-2026-06-26.md` — status actualizat cu transa 2.

## Ce Codex trebuie sa verifice

1. **Citeste `REFACTORING_PLAN_V2.md`** — planul complet cu ajustarile din subagenti.
2. **Ruleaza validarile** (secvential, nu in paralel — typecheck poate race cu build):
   ```bash
   npm run typecheck
   npm run typecheck:strict
   npm run lint
   npm run test
   backend/scripts/run_tests_isolated.sh
   mypy backend/ --ignore-missing-imports --explicit-package-bases
   npm run build
   ```
3. **Verifica live**: `curl -fsS http://127.0.0.1:9898/health` → `{"status":"ok"}`.
4. **Verifica `.replace()` eliminat**: `grep -c "\.replace("
   backend/repositories/dashboard.py` → 2 (doar `fetch_monthly_history` +
   `fetch_year_history_monthly`, care sunt alt mecanism, conform planului neatinsi).
5. **Verifica teste noi trec**: `bash backend/scripts/run_tests_isolated.sh -k
   "test_cartela or test_forecast or test_manager_scope or test_tr_percent"` →
   5 passed.
6. **Verifica invariante business** (din `AGENTS.md`):
   - Cartele + `TR %` excluse din KPI Retail (testele 1, 5 valideaza).
   - `site_code` domina scope istoric (testul 2 valideaza).
   - Manager-scope OR-expansion pastrat (testul 4 valideaza — subtilitatea cheie).
   - Forecast math corect pentru luni partiale (testul 3 valideaza).

## Urmatorul batch recomandat (transa 3)

Conform `REFACTORING_PLAN_V2.md`:

1. **Pasul 3.2** — Elimina `join_sql`/`where_sql` injection din
   `repositories/salarii.py` (8 metode). Adauga teste repo-level inainte (subagent
   a confirmat coverage WEAK la repo — service test mock-uiește repo-ul).
   Atentie la invarianta: "agent-month values below 2000 RON exclude din medii, nu
   din totaluri/istoric".
2. **Pasul 3.3** — Elimina fragment-injection din `repositories/campaigns.py`
   (5 metode ramase). Campaigns e STRONG testat (subagent), securizeaza refactorul.
3. **Pasul 2.1-2.4** — Primitive frontend (`useSortable`, `SegmentedTabs`,
   `SideDrawer`, `usePersistentState`) inainte de spargerea `Dashboard.tsx`.
4. **Pasul 2.5a** — Migreaza `Campaigns.tsx` la TanStack Query. Reguli stricte
   (verificate subagent): `staleTime: 3*60_000` (nu default 60s),
   `placeholderData: keepPreviousData`, `prefetchQuery` explicit, un query pentru
   multi-month aggregate. **Campaigns intai** (mai simplu), Dashboard dupa
   validare in productie. **NU sterge `viewCache.ts`** (Settings il foloseste).

## BUG REZOLVAT DE CODEX — luna curenta afisata gresit (2026-05 in loc de 2026-06)

**Prioritate: MARE — user-affecting regression.**

### Simptom

Dupa transa 2 (restart backend + `npm run build`), frontend-ul afiseaza luna
curenta `2026-05` in loc de `2026-06`. Inainte de modificarile din transa 1+2,
aparea corect `2026-06` (luna in curs, partiala, `is_month_final=false`).

### Ce s-a verificat initial

1. **DB e corect** — `import_snapshots` are `2026-06` cu `status='completed'`,
   `is_month_final=false`, `created_at=2026-06-26`. Query-ul direct
   `SELECT DISTINCT import_month FROM import_snapshots WHERE status='completed'
   ORDER BY import_month DESC` returneaza `2026-06` prima.
2. **`get_available_months` nu are cache** in `services/filter_options.py:82` —
   paseaza direct la `repo.get_available_months()`.
3. **`App.tsx` nu e modificat** — `git diff HEAD src/App.tsx` = gol. Logica
   bootstrap (linia 165-171) apeleaza `getAvailableMonths()` si seteaza
   `currentMonth` la `availableMonths[0]` daca valoarea salvata nu e in lista.
4. **`repositories/filters.py` difera doar prin helper-ul `retail_filters`**
   (inlocuieste literal `'TR %'` cu `distribution_location_clause("agg")`) —
   nu afecteaza `get_available_months` (query-ul nu foloseste acest helper).
5. **Logs backend** arata request-uri `GET /api/filters/months` → 200, apoi
   frontend-ul cere `GET /api/dashboard/all?month=2026-05` (nu 2026-06).
6. **`client.ts` a fost refactorit de Codex in transa 1** (buildUrl, parseResponse,
   default `unknown`) — poate afecta cum se parseaza raspunsul? Nu e confirmat.
7. **`SecurityHeadersMiddleware`** nu seteaza `Cache-Control: no-cache` pe
   `/api/*` (doar pe `/assets/`, HTML, `sw.js`) — `/api/filters/months` ar putea
   fi cache-uit de browser/CDN. Dar era asa si inainte de transa 1.
8. **PWA `registerType: 'autoUpdate'`** — la `npm run build` SW-ul nou poate
   determina reload; daca browser-ul are un raspuns stale din HTTP cache pentru
   `/api/filters/months`, `availableMonths[0]` ar putea fi `2026-05` (dinainte
   ca `2026-06` sa apara in DB la 26 iunie).

### Ipoteze de investigat (Codex)

1. **localStorage stale** — `unihub_current_month` in browser-ul userului are
   `2026-05` salvat. Logica `App.tsx:169-171` pastreaza valoarea salvata daca e
   in `availableMonths`. Daca `2026-05` e in lista (este), `currentMonth` ramane
   `2026-05`. **Verifica**: `localStorage.getItem('unihub_current_month')` in
   browser. Daca e `2026-05`, bug-ul e aici — dar era asa si inainte, deci nu
   explica de ce "pana acum arata corect 06".
2. **HTTP cache stale** — browser-ul cache-uie `/api/filters/months` (fara
   `Cache-Control: no-cache` pe `/api/*`) si returneaza un raspuns dinainte de
   26 iunie cand `2026-06` nu era in DB. `npm run build` + SW update a fortat
   reload, dar fetch-ul a lovit cache-ul HTTP. **Verifica**: adauga
   `Cache-Control: no-cache, no-store, must-revalidate` pe `/api/*` in
   `SecurityHeadersMiddleware` din `backend/main.py:149-156` (extinde conditia
   `elif` sa acopere si `/api/`).
3. **`client.ts` refactor** — poate `parseResponse` intoarce alt tip pentru
   `string[]`? `getAvailableMonths` face `client.get<string[]>(...)`. Cu noul
   `parseResponse`, daca raspunsul e gol sau `204`, returneaza `undefined as T`.
   Daca cumva noul `client.get` schimba comportamentul pentru array-uri string,
   `availableMonths` ar putea fi `undefined` → `availableMonths[0]` → `undefined`
   → fallback la valoarea salvata `2026-05`. **Verifica**: `client.test.ts` —
   exista test pentru GET cu array string? Adauga un test cu `['2026-06',
   '2026-05']` daca nu.
4. **Ordine inversa** — poate noul `client.get` nu trimite auth header corect
   prima data, primeste 401, `unauthorizedRedirectStarted` se seteaza, dar apoi
   re-login cu token valid → al doilea request returneaza lista corecta, dar
   `currentMonth` deja setat la valoarea salvata. **Verifica**: logs pentru
   secventa 401 → 200 pe `/api/filters/months` la bootstrap.

### Ce NU trebuie sa faca Codex

- **Nu reveni modificarile din transa 2** (`fetch_summary` refactor) fara
  confirmare ca ele sunt cauza — testele de integrare (5/5) valideaza ca
  comportamentul e identic, iar bug-ul e pe path-ul filters/months, nu
  dashboard/summary.
- **Nu sterge localStorage-ul userului** din productie.
- Daca gaseste root cause-ul in `client.ts` (refactor Codex transa 1),
  atentie sa nu strice cele 134 teste frontend (in special `client.test.ts`).

### Reproducere

1. Deschide `https://retail.unihub.ro` in browser (nu incognito).
2. Verifica `localStorage.getItem('unihub_current_month')` in DevTools.
3. Verifica Network tab pentru `GET /api/filters/months` — response body, status,
   response headers (`Cache-Control` lipsa?).
4. Daca response body contine `2026-06` dar UI afiseaza `2026-05`, bug-ul e in
   frontend (localStorage sau `client.ts`). Daca response body NU contine
   `2026-06`, bug-ul e in backend/cache.

### Rezolvare Codex

Root cause-ul a fost ipoteza 1: `App.tsx` pastra luna din
`localStorage` daca era in lista disponibila. Cum `2026-05` era inca o luna
valida, `Hub > Luna in curs` ramanea blocat pe mai, desi backend-ul returna
`2026-06` prima in `/api/filters/months`.

Fix aplicat:

- `src/lib/currentMonth.ts` introduce `selectCurrentMonth`, care selecteaza
  intotdeauna prima luna din lista backend pentru fluxul "Luna in curs";
- `src/App.tsx` nu mai initializeaza `currentMonth` din `localStorage`; dupa
  bootstrap rescrie valoarea salvata cu luna curenta reala (`2026-06`);
- `backend/main.py` seteaza `Cache-Control: no-cache, no-store,
  must-revalidate` si `CDN-Cache-Control: no-store` pe toate rutele `/api/*`,
  pentru a preveni raspunsuri stale din browser/CDN.

Teste adaugate/rulate:

- `src/lib/currentMonth.test.ts` valideaza ca `['2026-06', '2026-05']` selecteaza
  `2026-06`;
- `backend/tests/test_request_context.py` valideaza headerele no-store pe API;
- `npm run test -- src/lib/currentMonth.test.ts src/api/client.test.ts`;
- `PYTHONPATH=backend backend/venv/bin/pytest backend/tests/test_request_context.py -q`.

Validari pentru bugfix si quick wins:

- `npm run typecheck` - OK;
- `npm run typecheck:strict` - OK;
- `npm run lint` - OK;
- `npm run test` - OK, 12 fisiere / 136 teste;
- `backend/scripts/run_tests_isolated.sh` - OK, 542 passed / 7 skipped;
- `backend/venv/bin/mypy backend --ignore-missing-imports --explicit-package-bases`
  - OK, 154 source files;
- `backend/venv/bin/mypy . --ignore-missing-imports --explicit-package-bases`
  - OK, 156 source files;
- `npm run build` - OK;
- `sudo systemctl restart unihub-backend.service` + local/public health - OK;
- `/api/filters/months` returneaza 401 fara token (corect) cu no-store headers
  local si public;
- DB live: `import_snapshots` ordonat descendent incepe cu `2026-06|completed|f`,
  apoi `2026-05|completed|t`.

## Continuare Codex — Pasul 3.3 Campaigns repository boundary

Codex a continuat planul cu partea mai mica si bine testata din transa 3:
`repositories/campaigns.py`.

Schimbari:

- `repositories/campaigns.py` nu mai primeste `where_sql`/`*_clauses` construite
  in service pentru overview/history/promo/incentive;
- repo-ul construieste intern clauzele cu `build_scoped_params` si
  `scoped_clauses`, pe metode cu filtre keyword-only (`firma`, `regional`, `asm`,
  `site_code`, `agent`);
- `services/campaigns.py` paseaza doar valorile business si nu mai are helperul
  `_campaign_clauses` sau constructii manuale de `promo_clauses`,
  `inc_store_clauses`, `inc_agent_clauses`;
- `backend/tests/test_campaign_clauses.py` verifica helper-ele de repository si
  contractul service -> repo.

Criteriu verificat:

- `rg "where_sql|join_sql|focus_where_sql|totals_where_sql|_clauses: list\\[str\\]"`
  pe `backend/repositories/campaigns.py backend/services/campaigns.py` - fara
  rezultate;
- `PYTHONPATH=backend backend/venv/bin/pytest backend/tests/test_campaign_clauses.py backend/tests/test_campaigns_promos.py -q`
  - OK, 18 passed;
- validarea finala completa dupa acest pas: `npm run typecheck`, `npm run
  typecheck:strict`, `npm run lint`, `npm run test` (12/136), `run_tests_isolated.sh`
  (542 passed / 7 skipped), mypy ambele forme, `npm run build`, restart live si
  health local/public - toate OK.

## Continuare Codex — Pasul 3.2 Salarii repository boundary

Codex a inchis si boundary-ul `repositories/salarii.py`, cu atentie speciala la
invarianta financiara: salariile sub 2000 RON se exclud din medii, dar raman in
totaluri/istoric.

Schimbari:

- `services/salarii.py` nu mai construieste `join_sql`, `where_sql`, `where`,
  `where_clause` sau liste de conditii SQL;
- `repositories/salarii.py` construieste intern scope-ul prin `_salary_scope`,
  cu metode keyword-only pentru filtre (`company_name`, `site_code`, `regional`,
  `asm`, `year`, `month`, `q`);
- `fetch_overview`, `fetch_evolution_*`, `fetch_agents_summary`,
  `fetch_latest_month`, `fetch_summary_by_site`, `fetch_trend`, `fetch_stores`
  si `fetch_records` nu mai primesc fragmente SQL externe;
- `backend/tests/test_salarii_repository.py` adauga teste DB izolate care
  valideaza explicit ca totalurile includ salariul de 1500 RON, iar mediile il
  exclud.

Criteriu verificat:

- `rg "join_sql|where_sql|join_stores|where_clause|where =|conditions:
  list\\[str\\]|params: list\\[Any\\]"` pe `backend/repositories/salarii.py
  backend/services/salarii.py backend/repositories/campaigns.py
  backend/services/campaigns.py` - fara rezultate de injection (doar
  `initial_params`/`initial_conditions` in helper);
- `PYTHONPATH=backend backend/venv/bin/pytest backend/tests/test_salarii_service.py backend/tests/test_salarii_repository.py -q`
  - OK, 26 passed / 2 skipped fara DB izolata;
- `backend/scripts/run_tests_isolated.sh -k "salarii_repository or salarii_service or salarii_service_overview or salarii_service_summary"`
  - OK, 30 passed;
- validarea finala completa dupa Pasul 3.2: `npm run typecheck`, `npm run
  typecheck:strict`, `npm run lint`, `npm run test` (12/136),
  `run_tests_isolated.sh` (544 passed / 7 skipped), mypy ambele forme
  (155/157 source files), `npm run build`, restart live si health local/public -
  toate OK.

## Reguli de aur pentru continuarile viitoare

1. Nu combina refactorizari structurale cu schimbari business.
2. Păstreaza contractele API/payload pana la un motiv explicit.
3. Teste inainte de refactor pentru zonele slabe.
4. Validare secventiala dupa fiecare pas.
5. NU inlocui `print()` in `grile_monthly` (load-bearing).
6. NU migra `get_stores_coverage` (comportament diferit).
7. NU introduce `ScopeFilters` dataclass (riscant).
8. Păstreaza `viewCache.ts` (Settings il foloseste).
9. TanStack: `staleTime: 3min`, `keepPreviousData`, `prefetchQuery` explicit.
10. `.replace()` in `fetch_monthly_history`/`fetch_year_history_monthly`: neatins
    in transa 2 (alt mecanism, risc mic) — optional pentru curatenie ulterioara.
