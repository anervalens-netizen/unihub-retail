# UniHub Retail — Plan de implementare refactoring (v2, verificat)

> Document bazat pe `AUDIT_POST_REFACTOR.md` + verificări prin 4 subagenți pe zonele riscante.
> Principiu fundamental: **nu stricăm aplicația**. Fiecare pas e conservativ, cu teste înainte de refactor și validare secvențială după.
> Data: 2026-06-27

---

## Cum a fost construit acest plan

1. Am pornit de la auditul din `AUDIT_POST_REFACTOR.md` (care a verificat lucrarea agentului primar — verdict: corect, fără regresii).
2. Am lansat 4 subagenți care au verificat zonele riscante din recomandările mele: `.replace()` în dashboard repo, `print()` în grile_monthly, consolidare scope builders, coverage teste + invariante business.
3. **3 recomandări din auditul meu au fost corectate ca nesigure** (vezi tabelul de mai jos). Planul de mai jos incorporate aceste corecturi.
4. Am identificat **3 zone cu teste slabe** care necesită teste ADĂUGATE ÎNAINTE de refactor.

### Ajustări majore față de auditul original

| Recomandare AUDIT_POST_REFACTOR | Verdict subagent | Decizie în planul v2 |
|---|---|---|
| `.replace()` = "cel mai fragil, eșec silențios, prioritatea #1" | Parțial greșit: doar `fetch_summary:15-31` e cartela CTE; `fetch_monthly_history:172` și `fetch_year_history_monthly:279` sunt alt mecanism (alias swap pt store_targets, risc mic). Eșec e mai degrabă LOUD (SQL error la alias inexistent), nu silențios cu schema de azi. | Prioritatea rămâne #1 dar **doar `fetch_summary`**; abordare schimbată (vezi Pasul 3.1); **teste adăugate înainte**. |
| Înlocuiește `print()` cu logging în `grile_monthly.py` (15×) | **GREȘIT — `print()` e load-bearing**: output-ul e capturat în `result.output`, stocat în `grile_monthly_operations.result` (JSONB), returnat prin API și **afișat în UI** (`GrileMonthlyPanel.tsx:244-247` într-un `<pre>`). Test `test_grile_monthly_service.py:774` asertează pe `result["output"]`. | **NU înlocui.** Dual-write (`print()` + `logger.info`) doar dacă se vrea logging structurat. Elimină din plan ca pas de refactor. |
| Migrează `get_stores_coverage` (`agents.py:1303`) la `build_scoped_params` | **GREȘIT — comportament genuin diferit**: sentinel field-specific (`firma!="Toate"`, `regional!="Toti"`) vs `normalize_filter` (set mai larg incluzând diacritice `Toți`); SQL scalar `=` vs `= ANY(...)`; **nu are** retail exclusion clause. Migrarea ar schimba silențuis care input-uri sunt tratate ca "no filter" + ar injecta `TR %` exclusion. | **Elimină din plan.** Nu e o omisiune, e un pattern diferit. |
| Introdu `ScopeFilters` dataclass tipizate | **RISCANT**: nu acoperă `current_scope`/`include_closed_stores` (sunt clause concerns, aplicate în 3 locuri diferite, nu param concerns); `initial_params` variază 1-6 elemente cu semantici diferite; ~25 call-site-uri de schimbat cu risc real de shiftare pozițională asyncpg. | **Elimină din plan.** `build_scoped_params` actual cu kwargs e deja sigur și tipizat suficient. |
| Migrează Dashboard/Campaigns la TanStack Query | **OK dar cu capcane**: trebuie `staleTime: 3*60_000` (nu default 60s); `placeholderData: keepPreviousData` pentru instant stale paint; `prefetchHistory` (Dashboard:722) trebuie replicat explicit; `historyDetailCacheKey` e multi-month aggregate → **un query**, nu N; `Settings.tsx` folosește și el `viewCache` → nu se poate șterge `viewCache.ts`. | **Păstrează dar cu reguli stricte** (vezi Pasul 2.5). Campaigns întâi (mai simplu), apoi Dashboard. |
| Consolidează `_build_scoped_params` (alias) cu cel public | **SIGUR**: wrapper-ul privat e passthrough pur, zero comportament adăugat, toți callerii folosesc kwargs. | **Păstrează** ca quick-win mecanic (Pasul 1.4). |

### Zone cu teste slabe — necesită teste ÎNAINTE de refactor

| Zonă | Coverage | Risc | Ce teste de adăugat |
|---|---|---|---|
| `agents.py` `get_agent_evaluation` + `_v2` | **ZERO teste** | HIGH — scoring weights, thresholds, target allocation formula, `'-'`/`'TR%'` filters — orice refactor trece silențios | Vezi Pasul 0.1 |
| `dashboard.py` `fetch_summary` cartela CTE + forecast math | **MOCK ONLY** — repo e mocked, niciodată SQL real | HIGH — refactor `.replace()` poate leak-ui Cartele în Retail totals | Vezi Pasul 0.2 |
| Frontend `Dashboard`/`Campaigns`/`TargetCalculator` rendering | **ZERO componente test** | MEDIUM — refactor structura poate strica afișare cu toate unit testele verzi | Vezi Pasul 0.3 |

---

## Secvența de validare (de rulat după FIECARE pas)

**Obligatoriu secvențial** (AGENTS.md: typecheck poate race cu Vite build cât `dist/` se regenerează):

```bash
npm run typecheck
npm run typecheck:strict
npm run lint
npm run test
backend/scripts/run_tests_isolated.sh    # PostgreSQL 18 temporar, NU atinge baza de producție
mypy backend/ --ignore-missing-imports --explicit-package-bases
npm run build
```

După modificări backend care afectează live path:
```bash
sudo systemctl restart unihub-backend
curl -fsS http://127.0.0.1:9898/health   # port 9898, NU 8000
```

După modificări worker (grile, imports):
```bash
sudo systemctl restart unihub-worker
```

`run_tests_isolated.sh` e verificat ca SIGUR (triplu guard: container ephemeral `postgres:18-alpine` pe port loopback random, `validate_test_database_url` refuză non-PostgreSQL/non-loopback/port 5432/db name non-test, `test_database_safety.py` asertează toate căile de refuz).

---

## Pasul 0 — Teste de siguranță înainte de refactor (PREREQUISIT)

Aceste teste se adaugă ÎNAINTE de orice refactor din Pașii 1-6. Fără ele, refactorările din zonele slabe sunt "fly blind".

### 0.1 Teste pentru `agents.py` evaluation (înainte de Pasul 4.3)

De adăugat în `backend/tests/test_agents_service.py` (sau un fișier nou `test_agents_evaluation.py`):

1. **`pct_points` threshold boundaries** (v1, 6 segmente):
   - Target valoare: 100%→3p, 99.99%→2p, 90%→2p, 89.99%→1p, 80%→1p, 79.99%→0p
   - Medie zilnică: peste medie→3p, sub→0p
   - Valoare reper: 100→3p, 99.99→2p, 95→2p, 94.99→1p, 90→1p, 89.99→0p
   - % Bonuri: 35→3p, 34.99→2p, 30→2p, 29.99→1p, 25→1p, 24.99→0p
   - Focus: 8→3p, 7.99→2p, 7→2p, 6.99→1p, 6→1p, 5.99→0p
   - Folii Premium: 50→3p, 49.99→2p, 40→2p, 39.99→1p, 30→1p, 29.99→0p
2. **`qualifier` mapping**: 18→Excelent, 17→Foarte Bun, 14→Foarte Bun, 13→Bun, 10→Bun, 9→Mediu, 6→Mediu, 5→Sub_STANDARD
3. **`current_agents` CTE filters**: asertează că SQL-ul generat exclude `agent='-'` AND `agent NOT ILIKE 'TR%'` (parse query string sau mock-fetch cu rows care conțin aceste valori → verifică că nu apar în rezultat)
4. **Target allocation formula**: cu mock inputs `store_target=100000, store_working_days=24, agent_working_days=20` → `agent_target == 83333.33` (100000/24*20). Testează și cu `store_working_days=0` (edge case — trebuie să nu împartă la zero)
5. **v2 weights**: standard (Target 25, Productivitate 20, Bon2Acc 15, Focus 15, Folii 10, Valoare reper 15) vs provisional (Target 10, Productivitate 25, Bon2Acc 20, Focus 20, Folii 10, Valoare reper 15). Asertează că suma ponderilor = 100 în ambele cazuri.
6. **v2 confidence flags**: cu `working_days < 8` sau `receipts < 20`/`30` → flag `insuficient` setat, scor marcat provizoriu.

**Criteriu**: teste trec pe codul actual (fără modificări) — confirmă că prind comportamentul existent.

### 0.2 Teste pentru `dashboard.py` `fetch_summary` cartela + forecast (înainte de Pasul 3.1)

De adăugat ca **test de integrare** în `run_tests_isolated.sh` (DB real temporar):

1. **Cartela nu contaminează Retail totals**:
   - Seed: `reporting_agent_day` cu 2 magazin (SITE01, SITE02), `sales_transactions` cu rânduri Cartele (`is_cartela=true`) pentru SITE01, `import_snapshots` lună finalizată.
   - Apel `fetch_summary` cu `current_scope=False`.
   - Asertează: `summary.total_sales` exclude Cartele; `summary.cartele_qty` > 0 și e populat separat; `summary.total_quantity` exclude Cartele.
2. **Cartela respectă site_code dominance**:
   - Apelează cu `site_code="SITE01"` → `cartele_qty` reflectă doar SITE01, nu SITE02.
3. **Forecast math**:
   - Seed: `import_snapshots` cu `is_month_final=false`, `period_end` ziua 6, lună cu 31 zile.
   - Asertează: `forecast_sales == total_sales / 6 * 31` (Decimal, 2 zecimale).
4. **Manager-scope OR-expansion pentru cartela**:
   - Apelează cu `current_scope=True`, `regional="Andrei Stancu"`, fără asm/site.
   - Asertează: `cartele_qty` include magazinele unde managerul e ASM (nu doar RM) — adică OR-expansion se aplică și cartela CTE. **Acesta e testul care protejează subtilitatea de la Pasul 3.1.**

**Criteriu**: teste trec pe codul actual (cu `.replace()` existent) — confirmă comportamentul înainte de refactor.

### 0.3 Teste de render pentru componente frontend cheie (înainte de Pasul 2.5 și 4)

De adăugat în `src/components/`:

1. **`Dashboard.test.tsx`**: render `<Dashboard/>` cu mock TanStack Query client returnând un `dashboard/all` payload fix → asertează că `cartele_qty` apare ca rând informational separat, nu în total; asertează KPI-uri principale randate.
2. **`TargetCalculatorSubtab.test.tsx`**: render cu email non-allowlist → asertează buton `Finalizează` ascuns; render cu 409 revision conflict → asertează mesaj stale-write afișat.
3. **`Campaigns.test.tsx`**: render → asertează `promo_qualifying_bons` și `incentive_qty` în coloane separate (nu reutilizate).

**Criteriu**: teste trec pe codul actual. Acestea devin safety net pentru Pașii 2.5 și 4.

---

## Pasul 1 — Quick wins cu risc minim (închidere gaps prima transană)

### 1.1 Verifică și completează migrarea `downloadBlob`

- Verifică `targetCalculator.ts:196`, `grile.ts:162`, `tableExport.ts:60`, `Settings.tsx:277`, `VisiteSubtab.tsx:34` — dacă toate importă `lib/download.ts`.
- Migrează ce nu e migrat. Șterge pattern-ul inline `createObjectURL`/`createElement('a')`.
- **Validare**: `grep -rn "createObjectURL" src/` → trebuie să returneze doar `src/lib/download.ts`.
- **Risc**: minim (helper cu append la DOM consistent).

### 1.2 Verifică și completează migrarea `LoadingCard`/`ErrorCard`/`Metric`

- Verifică `Campaigns.tsx:1409-1439` — dacă mai are definiții locale.
- Dacă da, șterge și importă din `DashboardWidgets`.
- **Validare**: `grep -n "function LoadingCard\|function ErrorCard\|function Metric" src/components/` → doar în `DashboardWidgets.tsx`.

### 1.3 Verifică formatters locale

- `SalariiSubtab.tsx:51-66`, `AgentEvaluationSubtab.tsx:14-30`, `Agents.tsx:37-38` — dacă mai redefiniesc formatters.
- Migrează la `lib/formatters`/`lib/dates` dacă nu s-a făcut.
- **Atenție**: `SalariiSubtab` are semantică divergentă (returnează `'0'` pentru null) — verifică dacă schimbarea break-uiește UI. Dacă da, păstrează dar adaugă comentariu de ce.

### 1.4 Consolidează `build_scoped_params` (alias removal — SIGUR, verificat subagent)

- Schimbă importurile în 6 fișiere ca să folosească `services.filters.build_scoped_params` direct în loc de `services.dashboard.utils._build_scoped_params`:
  - `services/promo_copurchase.py:31`
  - `services/premium_glass.py:18`
  - `services/dashboard/queries.py:18`
  - `services/dashboard/specials_data.py:13`
  - `services/dashboard_service.py:47`
  - `tests/test_dashboard_utils_extended.py:6`
- Păstrează `_build_scoped_params` în `dashboard/utils.py` ca alias de compatibilitate (sau șterge-l dacă toate importurile sunt actualizate).
- **Verificat SIGUR de subagent**: wrapper-ul e passthrough pur, zero comportament adăugat, toți callerii folosesc kwargs, niciun risc de shiftare pozițională.
- **Validare**: `pytest backend/tests/test_filters_extended.py backend/tests/test_dashboard_utils_extended.py -q` + `mypy`.

### 1.5 Înlocuiește `'Toate'`/`'Toti'` rămas în `Agents.tsx`

- Linile 323, 324 (`cardFirma`/`cardMagazin` state init), 395, 399 (comparări), 964, 996, 1018 (label-uri).
- **Atenție**: acestea sunt pentru sub-filtrul local de card, NU pentru filtrele principale (care folosesc deja `ALL_FIRMS`/`ALL_STORES` la 330-333).
- Creează constantă locală `const ALL_CARD = 'Toate' as const` sau folosește `ALL_FIRMS`/`ALL_STORES` dacă semantically se potrivește.
- **NU atinge** `get_stores_coverage` (`agents.py:1303`) — verificat de subagent ca comportament diferit, nu se migrează.

### Criteriu de ieșire Pasul 1

- `npm run typecheck` + `npm run typecheck:strict` + `npm run lint` + `npm run test` OK
- `backend/scripts/run_tests_isolated.sh` OK
- `mypy backend/` OK
- `grep -rn "createObjectURL" src/` → doar `lib/download.ts`
- `grep -rn "_build_scoped_params" backend/services/` → 0 (sau doar alias)

---

## Pasul 2 — Primitive frontend comune + migrare TanStack

### 2.1 `useSortable<T>` hook

- Semnătură: `useSortable<T>({ rows, key, direction, defaultAscKeys }): { sorted, sortKey, direction, handleSort }`.
- Elimină trio-urile sort-state+handler+memo din Dashboard (×6), AgentEvaluation (×2), Salarii (×2).
- **Test**: adaugă `useSortable.test.ts` cu sortare numerică/string, direcție toggle, default-asc keys.
- **Validare**: `npm run test` + `npm run typecheck:strict`.

### 2.2 `<SegmentedTabs>` component

- Props: `options: {label, value}[], value, onChange`.
- Unifică 5 switchere (`Dashboard:1471`, `Campaigns:387`, `Agents:506`, `Settings:299`, `AgentEvaluation:991`).
- **Test**: render + click → onChange apelat cu valoarea corectă.

### 2.3 `<SideDrawer>` component

- Props: `open, onClose, title, children`.
- Unifică 4 drawer-e (`StoreDetailDrawer`, `AgentDrawer`, `VisitDrawer`, `SalaryDrawer`).
- Pattern: `fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm` + outside-click-close + `X` header.
- **Test**: render cu `open=true` → conținut vizibil; click pe backdrop → `onClose` apelat.

### 2.4 `usePersistentState` hook

- Semnătură: `usePersistentState<T>(key: string, default: T): [T, Dispatch<SetStateAction<T>>]`.
- Colapsează 6 effects de localStorage mirror din `App.tsx` + 4 din `Agents.tsx`.
- **Test**: setează valoare → localStorage actualizat; re-mount → valoare restaurată.

### 2.5 Migrare TanStack Query — Campaigns ÎNTÂI, apoi Dashboard

**Reguli stricte** (verificate de subagent):

1. **`staleTime: 3 * 60_000`** (3 min) per query — NU default 60s (ar refetch-a de 3× mai des decât azi).
2. **`placeholderData: keepPreviousData`** (TanStack v5) pentru instant stale paint la schimbare de key.
3. **`prefetchHistory`** (Dashboard:722-740) trebuie replicat cu `queryClient.prefetchQuery(...)` explicit — NU e automat.
4. **`historyDetailCacheKey`** (Dashboard:879-918) e multi-month aggregate (`Promise.all` + `aggregateDashboardDetails`) → **un singur query** cu queryFn care face agregarea, keyed `['dashboard','history-detail', selectedHistoryMonths, query]`. NU N query-uri separate (ar pierde instant paint-ul și granularity de refetch).
5. **`currentHistory`** (Dashboard:980-988, `months_back: 14`) e fetch separat care NU folosește cache — migrează independent sau lasă-l.
6. **`Settings.tsx` folosește și el `viewCache`** (linia 12) → **NU șterge `viewCache.ts`**. Migrează doar Dashboard + Campaigns.

**Ordine**:
- **2.5a Campaigns întâi** (mai simplu — fără prefetch, fără multi-month aggregate). Query keys:
  - `['campaigns', 'current', activeSection, promoMonth, selectedPromotionKey, query]` — staleTime 3min
  - `['campaigns', 'history', historyMonth, {...query, months_back: 12}]` — staleTime 3min
  - **Test**: adaugă `Campaigns.test.tsx` (de la Pasul 0.3) care randează cu mock query client.
- **2.5b Dashboard după ce 2.5a e validat în producție**. Query keys:
  - `['dashboard', 'current', currentMonth, query]` — staleTime 3min
  - `['dashboard', 'history', historyMonth, {...query, months_back: 12}]` — staleTime 3min
  - `['dashboard', 'history-detail', selectedHistoryMonths, query]` — staleTime 3min, queryFn cu `Promise.all` + `aggregateDashboardDetails`
  - `queryClient.prefetchQuery({ queryKey: ['dashboard', 'history', ...], queryFn: ... })` în loc de `prefetchHistory`
  - **Test**: adaugă `Dashboard.test.tsx` (de la Pasul 0.3).

**`queryKeys` factory**:
- Creează `src/lib/queryKeys.ts` cu:
  ```ts
  export const queryKeys = {
    dashboard: { current: (m, q) => ['dashboard','current',m,q], history: (m, q) => ['dashboard','history',m,q], historyDetail: (months, q) => ['dashboard','history-detail',months,q] },
    campaigns: { current: (s, m, k, q) => ['campaigns','current',s,m,k,q], history: (m, q) => ['campaigns','history',m,q] },
    agents: { overview: (q) => ['agents','overview',q], ... },
    grile: { overview: (m) => ['grile-overview',m], ... },
  }
  ```
- Tipizat, compile-checked — elimină typos pe invalidări.

### Criteriu de ieșire Pasul 2

- `Dashboard.tsx` și `Campaigns.tsx` nu mai au `isMountedRef`/`getCachedView`/`setCachedView` pentru fluxurile principale (verifică cu grep).
- `viewCache.ts` rămâne (Settings îl folosește).
- Testele de render (Pasul 0.3) trec.
- `npm run typecheck` + `npm run typecheck:strict` + `npm run test` OK.

---

## Pasul 3 — Backend: eliminare `.replace()` + repository boundaries

### 3.1 Elimină `.replace()` din `fetch_summary` (PRIORITATEA #1 — dar doar `fetch_summary`)

**Context** (verificat subagent):
- Doar `fetch_summary:15-31` e cartela CTE (celelalte 2 site-uri sunt alt mecanism, risc mic — se ating doar dacă vrem curățenie).
- Pattern-ul sigur **deja există** în `queries.py:1188-1211`: cheamă `scoped_clauses` a doua oară cu alias-uri cartela.
- **Subtilitatea**: `_expand_current_manager_scope` (`dashboard/utils.py:46-62`) emite `s.regional`/`s.asm` hardcodat — `.replace()` le transformă în `cs.regional`/`cs.asm` pentru cartela. Dacă sărim acest pas (cum face `queries.py` pt period-comparison), cartela cohort se micșorează pentru manager-scope + regional selected. **Trebuie păstrat comportamentul exact.**

**Pași**:
1. **Mai întâi adaugă testele de la Pasul 0.2** (cartela nu contaminează, site_code dominance, forecast, manager-scope OR-expansion). Confirmă că trec pe codul actual.
2. Parametrizează `_expand_current_manager_scope` cu `store_alias: str = "s"`:
   - Înlocuiește `s.regional`/`s.asm` din emit cu `{store_alias}.regional`/`{store_alias}.asm`.
   - **Test**: asertează că `_expand_current_manager_scope(..., store_alias="cs")` emite `cs.regional`/`cs.asm`.
3. În `dashboard_service.py:get_summary` (după ce build `clauses`), build `cartela_clauses`:
   ```python
   cartela_clauses = scoped_clauses(positions, site_alias="c", store_alias="cs", agent_alias="c")
   if current_scope:
       cartela_clauses = _expand_current_manager_scope(cartela_clauses, positions, store_alias="cs")
   if current_scope and not include_closed_stores:
       cartela_clauses.append("cs.is_active = true")
   ```
4. Schimbă semnătura `fetch_summary(self, clauses, params, cartela_clauses, current_scope=False)` și **șterge linile 15-31** (loop-ul `.replace()`).
5. În `cartele_summary` CTE (repo linia 87-94), folosește `cartela_clauses` direct.
6. Pentru month clause: trece `month_alias=None` la cartela `scoped_clauses` (repo are hardcoded `c.import_month = $1` la linia 92 — elimină duplicatul inofensiv).
7. **Nu atinge** `fetch_monthly_history:172` și `fetch_year_history_monthly:279` (alt mecanism, risc mic — se pot face opțional mai târziu ca curățenie).

**Validare**:
- Testele de la Pasul 0.2 trec (cartela nu contaminează, manager-scope OR-expansion păstrat).
- `grep -c "\.replace(" backend/repositories/dashboard.py` → scade de la 14 la ~4 (doar cele 2 site-uri mici risc).
- `pytest backend/tests/test_dashboard*.py -q` + `run_tests_isolated.sh`.
- **Live**: după deploy, verifică manual un card Hub cu regional selectat (fără asm/site) — `cartele_qty` trebuie să includă magazinele unde managerul e ASM, nu doar RM.

### 3.2 Elimină `join_sql`/`where_sql`/`clauses` injection din `repositories/salarii.py`

- Repo-urile își construiesc clauzele intern din kwargs tipizate (`firma`, `regional`, `asm`, `site_code`, `agent`, `month`), NU din string-uri injectate.
- Elimină duplicarea `salary_base` CTE (×5), `agent_key` expresie (×6), `MIN_SALARY_FOR_AVERAGE` filtru (×8).
- **Mai întâi adaugă teste repo-level** pentru dedup + consolidation (subagent a confirmat coverage WEAK la repo — service test mock-uiește repo-ul).
- **Atenție la invarianta**: "agent-month values below 2000 RON exclude din medii, nu din totaluri/istoric". Teste care asertează ambele (avg exclude, total nu).

### 3.3 Elimină fragment-injection din `repositories/campaigns.py` (5 metode rămase)

- `fetch_overview` (ia `focus_where_sql`/`totals_where_sql`), `fetch_history`, `fetch_promo_total`, `fetch_promo_store_rows`, `fetch_incentive_store_rows` — toate iau `*_clauses: list[str]`.
- Repo-urile primesc `ScopeFilters` kwargs și construiesc intern.
- **Campaigns e STRONG testat** (subagent) — securizează refactorul.

### 3.4 NU introduce `ScopeFilters` dataclass

- **Verificat de subagent ca RISCANT**: nu acoperă `current_scope`/`include_closed_stores` (clause concerns) și `initial_params` (variază 1-6 elemente).
- Păstrează kwargs actuale (`firma=`, `regional=`, etc.) la `build_scoped_params` — sunt deja sigure și tipizate.

### 3.5 NU atinge `get_stores_coverage`

- **Verificat de subagent**: comportament genuin diferit (sentinel field-specific, SQL scalar, fără retail exclusion). Nu e omisiune.

### Criteriu de ieșire Pasul 3

- `grep -rn "join_sql\|where_sql.*str" backend/repositories/` → 0 în salarii/campaigns.
- `grep -c "\.replace(" backend/repositories/dashboard.py` → ≤4.
- Testele de la Pașii 0.1, 0.2 trec.
- `mypy backend/` + `run_tests_isolated.sh` OK.

---

## Pasul 4 — Spargerea god-files (după Pașii 0-3)

### 4.1 `grile_monthly.py` → repo separat + state machine explicit

- Creează `repositories/grile_monthly.py` și mută tot SQL-ul din `services/grile_monthly.py`.
- `reserve_monthly_operation` (169 linii) → `ReservationState` enum (`idle/locked/blocked/reserved`) în loc de variabile mutabile.
- **NU înlocui `print()` cu logging** — e load-bearing (UI + DB + teste). Dacă se vrea logging structurat: **dual-write** (`print()` + `logger.info` cu același mesaj), aditiv, zero-risc.
- `time.sleep` în `retry_api:261` — **NU schimba** (e sync, rulat în thread-uri via `asyncio.to_thread`).
- **Test**: `test_grile_monthly_service.py:774` asertează pe `result["output"]` — trebuie să rămână verde.

### 4.2 `models.py` → desparte pe domenii

- `models/dashboard.py`, `models/agents.py`, `models/campaigns.py`, etc.
- Adaugă `Literal` pe status-uri, `pattern` pe `month: str` (`r'^\d{4}-\d{2}$'`), `ge=0` pe `target_value`.
- Desparte `AgentEvaluationV2Row` (47 câmpuri) în `AgentEvaluationV2Metrics` + `AgentEvaluationV2Scores` + `AgentEvaluationV2Row` compunându-le.
- **Mai întâi adaugă testele de la Pasul 0.1** (agents evaluation) — ca să prinzi regresii de validare.
- **Atenție**: forward-ref-urile — adaugă `model_rebuild()` acolo unde e necesar.

### 4.3 `agents.py` `get_agent_evaluation_v2` (557) → desparte

- `build_evaluation_sql()` (repo) — mută SQL-ul în `repositories/agents.py`.
- `compute_v2_scores(rows)` (scoring Python pur) — mută ponderile (989-993) și pragurile (967-971) în config/constante numite.
- `assemble_result()`.
- Deduplică `current_agents` CTE (×4) + `option_query` (×2) + `premium_lines` (×2) — extrage într-un helper SQL reusable.
- `c.replace("import_month = $1", "import_month <= $1")` (linia 133) → query parametric separat, nu string surgery.
- **Mai întâi adaugă testele de la Pasul 0.1**.

### 4.4 `campaigns.py` `get_promotions_incentives` (422) → desparte

- `compute_store_promo_incentive` + `compute_agent_promo_incentive` + `categorize_tiers`.
- Înlocuiește `store_inc.get(...)[3]` (magic index) cu dataclass tipizate.
- `get_promotions_incentives` are raw `conn.fetch` la 621 (subagent a confirmat) — mută în repo.
- **Campaigns e STRONG testat** — securizează.

### 4.5 `dashboard_service.py` `get_dashboard_all` (318) → gather dict-keyed

- Înlocuiește 13 closures + `asyncio.gather` pozițional (`results[0]`...`results[14]`) cu gather dict-keyed (rezultate după cheie).
- Strategie shared de conexiune (reduce presiune pool — azi până la 13 conexiuni concurente per request).
- **Mai întâi adaugă test** care asertează mapping-ul (cheie → rezultat) ca să prinzi reordonări.

### 4.6 `Dashboard.tsx` → desparte

- `useDashboardData`/`useDashboardHistory` hooks (din Pasul 2.5b).
- `<CurrentDashboard>` + `<HistoryDashboard>` + `<BreakdownTable>` parametrizat (tabel RM/Magazine/Agenti current+history devine un component cu props pentru setul de coloane).
- Colapsează cele 6 clone sort în `useSortable` (Pasul 2.1).
- **Șterge dead state `asms`** (linia 656) + `aggregateAsms` + `getAsmSortValue`.
- Estimat -800 linii.

### 4.7 Alte componente mari

- `Campaigns.tsx` → `<IncentiveSection>`/`<PromoSection>`/`<ContestSection>`/`<PremiumSection>`/`<FocusSection>`.
- `TargetCalculatorSubtab.tsx` → ref-mirror state (`scenarioRef`/`dirtyRowsRef`/`editVersionsRef`) → `useReducer`. Mobile cards vs desktop table → un component cu variant.
- `Agents.tsx` → `<AgentsOverview>`/`<StoreCoverage>`/`<AgentList>`. Coverage cards (×3 clone) → `<CoverageCard status="...">`.
- `App.tsx` → `usePersistentState` (Pasul 2.4) + `useAppNavigation` reducer + navigation context (înlocuiește global CustomEvent bus).

### Criteriu de ieșire Pasul 4

- Fiecare fișier mare scade fără schimbare de payload.
- Testele de la Pașii 0.1, 0.2, 0.3 trec.
- `npm run typecheck` + `npm run test` + `run_tests_isolated.sh` OK după fiecare mutare.

---

## Pasul 5 — Hardening API, auth, security

### 5.1 `ApiError` frontend

- `client.ts:67` înlocuiește `throw new Error('API error: N')` cu `throw new ApiError(status, detail, body)`.
- `ApiError` class cu `status: number`, `detail: string`, `body: unknown`.
- Caller pot face `switch (err.status)`.
- Corpul JSON parsat din response.
- **Test**: `client.test.ts` — asertează că 403 aruncă `ApiError` cu `status=403`.

### 5.2 `auth.py` security

- Elimină client_id default (linia 40) — fail-closed fără env.
- Localhost bypass (130-137): secret rotativ sau elimină.
- JWKS cache: `asyncio.Lock` + max-stale bound (ex: max 24h).
- Un singur sursă de adevăr pentru issuer (mută URL-urile hardcodate din `main.py:303` să folosească `OIDC_ISSUER`).

### 5.3 `target_calculator.py` `finalize_scenario` → excepții tipizate

- Înlocuiește bare `False` (321, 333, 337) cu excepții distincte:
  - `ScenarioConflictError` → 409
  - `ScenarioValidationError` → 422 (pending final, total mismatch)
- Router-ul prinde și mapează la status code corect.
- **Target calculator e STRONG testat** (subagent) — securizează.

### 5.4 `rate_limits.py` — DOAR dacă se trece la multi-worker

- Azi `uvicorn --workers 1` → limita per-proces = limita globală. Nu e bug.
- Dacă se trece la multi-worker: migrează la backend shared (Valkey).
- Adaugă evictare pe bucket-urile goale din `_hits`.

### 5.5 `visits_report.py`

- Paths din env (deja făcut în Pasul 1 al agentului primar — verifică).
- Mută `_aggregate_report_rows` (161-212) din repo în service.

### 5.6 `main.py` side effects

- Mută `load_dotenv`/`setup_logging`/`sentry_sdk.init` din import-time într-un `bootstrap()` apelat din `lifespan`.

### Criteriu de ieșire Pasul 5

- Teste auth/client/rate-limit acoperă cazurile noi.
- Fără relaxare OIDC.
- `npm run test` + `run_tests_isolated.sh` OK.

---

## Pasul 6 — Curățenie finală

1. **Magic literals → constante/config numite**:
   - Praguri incentive `0.99/0.89` (`dashboard_specials.py:487-493`)
   - Baseline `'2025-01'` ×7 (`agents.py:249,277,377,438,570,669,824`)
   - Ponderi scoring (`agents.py:989-993`)
   - Floor `35000` (`target_calculator.py:23`)
   - Ferestre 12/15/16 luni (`hr.py:91`, `target_calculator.py:402-404,486-490`)
   - `LIMIT 8` (`campaigns.py:54,70`), top-5 (`queries.py:1422,1477,1719`)
   - `promo_impact 20%` (`queries.py:1659`)
   - Epsilon `0.01` (`target_calculator.py:339,457`)
   - Praguri culoare scor (frontend), praguri complianță vizite `80/50`
2. **Caches module-level → `asyncio.Lock`** (`promo_copurchase:46`, `dashboard_specials:22`, `auth:44`).
3. **`SELECT *` eliminat** din `grile.py:252,262,269,278`, `hr.py:141`.
4. **`MANAGEMENT_ACCESS_GROUPS`/`SALARY_ACCESS_GROUPS`** — unifică sau documentează intenția de divergență + sincronizează mesajele user-facing.
5. **Documentație actualizată** după fiecare decizie stabilă.

---

## Rezumat: ordinea de execuție

```
Pasul 0 (teste safety net) ────► Pasul 1 (quick wins) ────► Pasul 2 (frontend primitives + TanStack)
                                                            │
                                                            ▼
Pasul 3 (backend .replace() + repo boundaries) ────► Pasul 4 (spargere god-files)
                                                            │
                                                            ▼
                                            Pasul 5 (hardening) ────► Pasul 6 (curățenie)
```

**Reguli de aur**:
1. **Nu combina refactorizări structurale cu schimbări business.**
2. **Păstrează contractele API/payload** până la un motiv explicit.
3. **Teste înainte de refactor** pentru zonele slabe (Pașii 0.1, 0.2, 0.3).
4. **Validare secvențială după fiecare pas** (typecheck → typecheck:strict → lint → test → pytest isolated → mypy → build → restart → health).
5. **NU înlocui `print()` în grile_monthly** (e load-bearing).
6. **NU migra `get_stores_coverage`** (comportament diferit).
7. **NU introduce `ScopeFilters` dataclass** (riscant, coverage parțială).
8. **Păstrează `viewCache.ts`** (Settings îl folosește).
9. **TanStack: `staleTime: 3min`, `keepPreviousData`, `prefetchQuery` explicit, un query pentru agregate.**
10. **`.replace()`: doar `fetch_summary`, mirror `queries.py:1188-1211`, parametrizează `_expand_current_manager_scope`.**

**Dacă se face un singur lucru**: Pasul 3.1 (eliminare `.replace()` din `fetch_summary`) cu testele de la Pasul 0.2 adăugate înainte. E cel mai fragil cod, cu mode de eșec silențios la schimbare de alias, și singurul care poate produce bug-uri de raportare greu de detectat.

---

## Note pentru agentul care execută

- Citește `AGENTS.md`, `README.md`, `APP_ARCHITECTURE.md` pentru invariante business complete.
- Invariante critice de respectat:
  - `site_code` domină scope istoric (nu constrânge și pe firma/RM/ASM)
  - Excludere Cartele + `TR %` din KPI Retail (cartela e doar rând informational separat, via `sales_transactions` brute cu `is_cartela=true`)
  - Fără param asyncpg unused (folosește `build_scoped_params` canonice)
  - Timeout-uri DB doar prin `DB_*_TIMEOUT_MS`
  - Media salarială exclude sub 2000 RON doar din medii, nu din totaluri/istoric
  - `total_salary` include bonuri masă
  - Alocare target = store target / store selling days × agent selling days
  - Grile `YYYY-MM` + cel mult un run `queued/running` per lună + reset ireversibil/admin-gated
  - Calculator Target: un draft per lună, finalized nu se recalculează, stale writes → 409
  - Promo qualifying receipts ≠ incentive quantity (metrici distincte)
  - Vizite grupate după TL snapshot-ul autorului vizitei
- `run_tests_isolated.sh` NU atinge baza de producție (triplu guard verificat).
- După modificări backend care afectează live path: `restart unihub-backend` + `curl http://127.0.0.1:9898/health`.
- După modificări worker (grile, imports): `restart unihub-worker`.
- Verifică manual path-ul schimbat pe live după deploy.
