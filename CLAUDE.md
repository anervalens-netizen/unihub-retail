# CLAUDE.md — Ghid pentru sesiunile Claude

Acest fisier explica tot ce trebuie sa stii pentru a lucra eficient pe proiectul **UniHub**.
Citeste-l la inceputul fiecarei sesiuni noi.

---

## Cine esti si cu cine lucrezi

Andrei este managerul echipei Mobiup. Lucreaza exclusiv cu Claude. Are bypass approvals activat — executa fara a cere confirmare pentru fiecare pas.

Tonul corect: direct, tehnic, fara padding. Explica pe scurt ce ai facut si de ce, fara liste lungi de recapitulari.

---

## Starea proiectului

- Aplicatie deployed pe server `192.168.0.68`, accesibila la https://unihub.astancu.eu/
- Stack: React 19 + Vite + TypeScript (frontend) / FastAPI + asyncpg + PostgreSQL 18 (backend)
- Module functionale: Hub, Focus, Agenti (+ Salarii), Vizite, Management (Echipa/Magazine/Tasks/HR), Setari, AI
- pytest passing, typecheck curat, build passing
- UniHub este sursa de adevar pentru vanzari SI vizite; Platforma-Mobiup citeste de aici
- UniAI: sesiuni persistente per-device, istoric selectabil, suport atasamente

Deploy productie (dupa modificari):
```bash
cd /opt/Mobiup/unihub
git pull
npm run build
sudo systemctl restart unihub-backend
```

Pentru modificari care ating UniAI / bridge-ul Hermes:
```bash
sudo -u andrei XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user restart hermes-unihub-bridge
```

---

## Structura importanta

### Frontend — `src/components/`
| Fisier | Rol |
|--------|-----|
| `App.tsx` | Auth + tab routing + localStorage persistence tab activ |
| `MainLayout.tsx` | Shell principal, navigare, filtre |
| `Dashboard.tsx` | Tab Hub — Luna în curs (tabele RM/ASM/Magazine/Agenti), Istoric (aceleasi tabele filtrate pe luna analizata), grafice |
| `Campaigns.tsx` | Tab Focus — campanii, incentive per-produs, Top Agenti + Top Magazine sortabile |
| `Agents.tsx` | Tab Agenti — include AgentDrawer, AgentDetails |
| `SalariiSubtab.tsx` | Sub-tab Salarii in Agenti |
| `SalaryDrawer.tsx` | Drawer detalii salariu per agent |
| `SalaryAgentBarChart.tsx` | Bar chart salarii per agent |
| `SalaryAreaChart.tsx` | Area chart evolutie salarii |
| `VisiteSubtab.tsx` | Tab Vizite — ASM accordion + drawer vizita cu poze |
| `Management.tsx` | Tab Management — shell cu 4 sub-taburi (Echipa/Magazine/Tasks/HR) |
| `ASMSubtab.tsx` | Sub-tab Echipa — performanta ASM combinata PG + SQLite |
| `CRMSubtab.tsx` | Sub-tab Magazine — scoruri CRM, alerte, recalculare |
| `TasksSubtab.tsx` | Sub-tab Tasks — task-uri per agent/magazin, creare din alerte CRM |
| `HRSubtab.tsx` | Sub-tab HR — cereri concediu, pontaj, performanta ASM |
| `AIChat.tsx` | Tab AI — chat UI, sesiuni, attachments, drawer istoric |
| `Settings.tsx` | Tab Setari (admin) |
| `PinScreen.tsx` | Ecran PIN pentru autentificare |
| `ErrorBoundary.tsx` | Error boundary React |

### Backend — `backend/routers/`
| Router | Prefix / Rol |
|--------|--------|
| `auth` | `/api/auth` |
| `dashboard` | `/api/dashboard` |
| `campaigns` | `/api/campaigns` |
| `filters` | `/api/filters` |
| `imports` | `/api/imports` |
| `stores` | `/api/stores` |
| `visits_report` | `/api/visits-report` — citeste SQLite din `data/visits/visits.db` |
| `admin` | `/api/admin` |
| `agents` | `/api/agents` |
| `salarii` | `/salarii` (fara prefix `/api`) |
| `tasks` | `/api/tasks` — task-uri per agent/magazin; sursa si din alerte CRM |
| `hr` | `/api/hr` — concedii, pontaj, performanta ASM (merge PG + SQLite) |
| `crm` | `/api/crm` — scoruri magazine, alerte, `get_forecast_factor` (shared cu hr.py) |
| `ai` | `/api/ai` — WebSocket proxy + sesiuni + attachments pentru Hermes bridge |
| `dashboard_filters` | *(fara prefix)* — helpers SQL: `where_clauses`, `scoped_clauses`, `transaction_filter_parts` |
| `shared` | *(fara prefix)* — utilitare comune: `normalize_filter`, `build_scope_filter` |

### UniAI / AI tab
- Frontend:
  - `src/components/AIChat.tsx` — layout messenger, composer fix jos, drawer sesiuni, upload attachments
  - `src/api/ai.ts` — WebSocket client pentru streaming (`device_id`, `session_id`, `attachments`)
  - `src/api/aiSessions.ts` — REST client pentru sesiuni si upload fisiere
- Backend UniHub:
  - `backend/routers/ai.py` — WS `/api/ai/ws` + REST pentru list/create/activate sesiuni si upload attachments
  - `backend/models.py` — modelele Pydantic pentru sesiuni AI / attachments
- Hermes bridge:
  - `/home/andrei/.hermes/hermes-agent/unihub_bridge.py` — SSE bridge catre AIAgent
  - `/home/andrei/.hermes/hermes-agent/unihub_session_store.py` — persistenta sesiuni active per-device
  - serviciu systemd user: `hermes-unihub-bridge`

- Persistenta sesiuni:
  - `device_id` salvat in localStorage sub cheia `unihub_ai_device_id`
  - transcriptul salvat in Hermes `SessionDB` (SQLite)
  - sesiunea activa per-device mapata in `~/.hermes/sessions/unihub_active_sessions.json`

- Endpointuri AI:
  - `GET /api/ai/sessions?device_id=...`
  - `GET /api/ai/sessions/{session_id}`
  - `POST /api/ai/sessions?device_id=...`
  - `POST /api/ai/sessions/{session_id}/activate?device_id=...`
  - `DELETE /api/ai/sessions/{session_id}` — sterge sesiunea din Hermes SQLite
  - `POST /api/ai/attachments`
  - `WS /api/ai/ws?token=...&device_id=...&session_id=...`

- Suport attachments: imagini (vision), `.txt`, `.md`, PDF (`pdftotext`), `.docx/.xlsx/.pptx`

- Grafice in chat: Hermes poate returna blocuri ```chart cu JSON spec; frontend-ul le randeaza via `ChartBlock` (recharts). Tipuri: `bar`, `line`, `pie`, `area`.

- Memorie cross-sesiune: Hermes citeste/scrie `memory.md` in workspace (`/opt/Mobiup/unihub/data/uniai-workspace/`) la prima interactiune din sesiune. Configurat in `/home/andrei/.hermes/SOUL.md`.

- Gotcha important:
  - bridge-ul trebuie sa creeze `AIAgent` cu `session_id` + `session_db`, iar payload-ul catre bridge trebuie sa includa `user_id`
  - `MainLayout.tsx`: tabul AI are `overflow-hidden` (nu `overflow-y-auto`) — scroll-ul e gestionat intern de messages area pentru a preveni saltul address bar-ului pe mobile

- Variabile de mediu:
  - `AI_BRIDGE_URL` — adresa bridge Hermes (default: `http://127.0.0.1:7777`)
  - `AI_BRIDGE_TIMEOUT` — timeout in secunde (default: `180`)

### Tab Management

Tab nou cu 4 sub-taburi, accesibil rolurilor `admin` si `management`.

| Sub-tab | Componenta | Backend | Descriere |
|---------|-----------|---------|-----------|
| Echipa (asm) | `ASMSubtab.tsx` | `/api/hr` | Performanta ASM — merge `reporting_agent_month` (PG) + `visits.db` (SQLite) + forecast factor din CRM |
| Magazine (crm) | `CRMSubtab.tsx` | `/api/crm` | Scoruri magazine, alerte, recalculare manuala. Alerte pot fi convertite direct in Tasks |
| Tasks | `TasksSubtab.tsx` | `/api/tasks` | Task-uri per agent/magazin. `source` poate fi `manual` sau `crm_alert` (cu `source_meta` JSONB) |
| HR | `HRSubtab.tsx` | `/api/hr` | Cereri concediu (creare, aprobare/respingere), pontaj zilnic, istoric ASM |

**Dependenta cross-router importanta:** `hr.py` importa `get_forecast_factor` din `crm.py` — la modificari in CRM, verifica si HR.

**CRM score logic:** `get_forecast_factor(conn, month)` calculeaza factor extrapolat (zile_luna / ultima_zi_vanzari). 1.0 daca luna e finalizata.

**Endpoints principale:**
- `GET /api/crm/scores?month=YYYY-MM` — scoruri magazine
- `POST /api/crm/scores/recalculate?month=YYYY-MM` — recalculeaza scoruri
- `GET /api/crm/alerts?month=YYYY-MM` — alerte active
- `GET /api/hr/leave-requests` — cereri concediu
- `POST /api/hr/leave-requests` — creare cerere
- `PATCH /api/hr/leave-requests/{id}` — aprobare/respingere
- `GET /api/hr/asm-performance?month=YYYY-MM&regional=...` — performanta ASM
- `GET /api/hr/asm-performance/{name}/history?months=N` — istoric ASM
- `GET /api/tasks` — lista task-uri
- `POST /api/tasks` — creare task
- `GET /api/tasks/my` — task-urile utilizatorului curent
- `GET /api/tasks/my/pending-count` — badge notificari

### Baza de date
- Schema unica: `backend/db/schema_v2.sql`
- Aplicata hash-based la boot via `ensure_schema_current()` in `backend/db/connection.py`
- **Nu modifica schema direct in DB** — editeaza `schema_v2.sql` si reporneste backend-ul
- Reporting pe agregate: `reporting_agent_*`, `reporting_item_*`, `reporting_focus_*`, `reporting_category_*`

#### Tabele principale
| Tabel | Continut |
|-------|----------|
| `sales_transactions` | Tranzactii detaliate 2023-09 → prezent |
| `historical_annual_sales` | Agregate anuale: 2022 complet, 2023 Ian-Aug (derivat) |
| `incentive_campaigns` | Campanii incentive per luna (titlu, subtitlu, descriere) |
| `incentive_products` | Produse eligibile + reward per produs per campanie |
| `store_targets` | Targete lunare per magazin |
| `stores` | Magazine cu site_code, locatie, firma, asm, regional |
| `reporting_agent_month` | Agregat lunar per agent (sursa principala dashboard) |
| `reporting_item_month` | Agregat lunar per produs |
| `historical_annual_sales` | 2022 an complet + 2023 Ian-Aug per magazin/firma |
| `tasks` | Task-uri per agent/magazin (`title`, `assignee`, `site_code`, `deadline`, `status`, `source`, `source_meta`) |
| `leave_requests` | Cereri concediu agenti (`agent_name`, `start_date`, `end_date`, `leave_type`, `status`) |
| `attendance_records` | Pontaj zilnic (`agent_name`, `record_date`, `status`) — UNIQUE per agent+zi |
| `store_scores` | Scoruri CRM per magazin per luna (`site_code`, `score_month`, `score`, `breakdown` JSONB) — UNIQUE per magazin+luna |

#### VIEW-uri compatibilitate Platforma-Mobiup
- `v_platforma_dashboard` — agregat lunar pe agent (din `reporting_agent_month` JOIN `stores`)
- `v_platforma_import_meta` — metadata per luna (din `import_snapshots`)
- `v_platforma_raw_sales` — tranzactii brute (din `sales_transactions` JOIN `stores`; `bon_nr` alisat ca `nr`)
- `v_platforma_store_targets` — targete magazin (din `store_targets` JOIN `stores`)

### Acoperire date istorice
| Perioada | Sursa | Granularitate |
|----------|-------|---------------|
| 2022 | `historical_annual_sales` | anual per magazin |
| 2023 Ian-Aug | `historical_annual_sales` | anual per magazin (derivat: annual - Q4) |
| 2023 Sep-Dec | `sales_transactions` | tranzactie per tranzactie |
| 2024 Ian-Dec | `sales_transactions` | tranzactie per tranzactie |
| 2025 Ian → prezent | `sales_transactions` | tranzactie per tranzactie |

**Nota import istoric:** fisierele 2023-2024 nu aveau coloana `Agent` (prezenta din 2025).
Agent = `'-'` pentru toate tranzactiile 2023-2024. Rapoartele per-ASM/magazin sunt corecte.

### Integrare Platforma-Mobiup
- **Date vanzari**: Platforma-Mobiup citeste din PostgreSQL UniHub via VIEW-urile `v_platforma_*`
  - Importul de vanzari se face **o singura data**, in UniHub
  - Ruta `/api/v2/intermediate-import` din Platforma-Mobiup returneaza 410 Gone
- **Vizite**: UniHub este sursa de adevar — `data/visits/visits.db` si `data/visits/images/`
  - Platforma-Mobiup citeste din acelasi fisier (default hardcodat la `/opt/Mobiup/unihub/data/visits/visits.db`)
  - Router `visits_report.py` citeste SQLite async via `run_in_executor` (non-blocking)
  - Endpoint `/api/visits-report/photo/{visit_id}/{filename}` serveste pozele cu auth (`FileResponse`)
  - Frontend: componenta `AuthImage` face fetch blob cu axios + `URL.createObjectURL` (nu `<img src>` direct)

### Hub Dashboard — structura tabele

Sectiunea **Luna in curs** si sectiunea **Istoric** afiseaza ambele 4 tabele: RM, ASM, Magazine, Agenti.

- **Coloane Magazine**: Magazin / Firma / Target / Vanzari / Procent / **Incentive** / Cantitate / Nr bonuri / Agenti / Zile active / Medie zilnica
- **Coloane RM / ASM**: fara `promo_qty` in Istoric (filtrat la render)
- **Coloane Agenti**: fara `promo_qty` in Istoric
- `incentive_qty` la Magazine este calculat in `_enrich_store_stats_with_campaign()` din `dashboard.py` — query pe `reporting_item_month` grupat pe `site_code`. Daca lipseste aceasta functie, valorile apar 0.

Pattern enrichment campanie (acelas pentru RM/ASM/Magazine/Agenti):
1. Incarca `promotion_codes` + `incentive_codes` din config/DB
2. Daca niciun cod activ → seteaza 0 si returneaza
3. Query `reporting_item_month` grupat pe cheia relevanta (regional / asm / site_code / agent)
4. Join pe rows de baza si ataseaza `promo_qty` + `incentive_qty`

### Hub Specials (incentive/promotii)
- **Incentive**: stocate complet in DB — `incentive_campaigns` + `incentive_products`
  - `hub_specials.json` contine doar promotii (coduri fixe); sectiunea `incentives` este goala
  - Logica in `backend/services/incentive_db.py` — `get_incentive_campaign(conn, month)`
  - Dashboard citeste reward_map din DB, nu din Excel
  - Pentru a adauga o campanie noua:
    ```bash
    cd /opt/Mobiup/unihub/backend
    source venv/bin/activate
    python3 scripts/import_incentive_campaign.py \
        --month 2026-05 \
        --title "Incentive Mai 2026" \
        --file "NumeFisier.xlsx" \
        --sheet Sheet1 \
        [--header 1]  # daca header-ul nu e pe primul rand
    ```
- **Promotii**: configurate in `data/hub_specials.json` (array `promotions` cu `item_codes`, `start_date`, `end_date`)
- Cardurile inactive se ascund automat in sectiunea Istoric

### Targete magazine
- Tabel: `store_targets (site_code, import_month, target_value)`
- Format fisier nou per luna: `Regional, ASM, Firma, Locatie, Cod, Target` (sheet "target")
- **Nu** folosi `load_targets_dataframe()` pentru acest format — aceea e pentru `Istoric targete.xlsx`
- Pattern import: script Python direct cu `upsert_store_targets()`, rulat din `backend/` cu venv activat

### Scripts utile (`backend/scripts/`)
| Script | Scop |
|--------|------|
| `import_historical.py` | Import batch fisiere vechi 2023/2024 (format fara Agent/Categorie) |
| `import_annual_summary.py` | Import rezumat anual din `vanzari 2022 si 2023.xlsx` |
| `import_incentive_campaign.py` | Import campanie incentive dintr-un Excel in DB |
| `rebuild_reporting.py` | Reconstruieste agregatele de reporting (toate lunile sau una anume) |
| `reset_default_users.py` | Reseteaza parolele admin/management la `9999` |
| `seed.py` | Seed complet din fisierele din `data/` |

### Backup
- Locatie unica: `/opt/Mobiup/backups/`
  - `postgres/` — dump-uri PostgreSQL (format custom pg_dump, `.dump`)
  - `visits/` — copii SQLite vizite
  - `platforma-mobiup/` — arhive punctuale Platforma-Mobiup
  - `backup.log` — log al rularii zilnice
- Script: `/opt/Mobiup/scripts/backup.sh`
- Cron: zilnic la 02:00, retentie 30 zile
- Restore PostgreSQL:
  ```bash
  pg_restore -h localhost -U unihub -d unihub --clean /opt/Mobiup/backups/postgres/unihub_YYYYMMDD.dump
  ```

---

## Reguli de lucru

### Nu citi din `sales_transactions` pentru raportare
Toate query-urile de raportare merg pe agregatele `reporting_*`. Exceptie: lookup-uri administrative punctuale.

### Modele Pydantic in `backend/models.py`
Orice camp returnat de un endpoint trebuie sa fie declarat explicit in modelul Pydantic corespunzator, altfel Pydantic il elimina din raspuns fara eroare (silent drop). Modelele cu `ConfigDict(from_attributes=True)` sunt deosebit de susceptibile — SQL poate calcula campul, dar daca nu e declarat in model, nu apare in raspuns.

### Filtre in frontend
Filtrul global (firma, regional, asm, magazin) din `MainLayout` este shared intre Hub si Focus.
Modulul **Agenti** are filtrele sale proprii, independente (`agentsFilters` in `App.tsx`).

`SalariiSubtab` primeste `globalFilters: AppFilters` din `Agents.tsx` — acestea sunt `agentsFilters`, nu `hubFilters`. Butonul flotant de filtru activ pe tab-ul Agenti alimenteaza `agentsFilters`.

Mapping `AppFilters` → parametri backend salarii:
- `firma` (`!= 'Toate'`) → `company_name` — comparatie **case-insensitive** (`LOWER()`), deoarece `salary_records.company_name` (`'Mobicell'`/`'Mobiup'`) difera ca si majuscule de `stores.firma` (`'MobiCell'`/`'MobiUp'`)
- `rm` (`!= 'Toti'`) → `regional`
- `asm` (`!= 'Toti'`) → `asm`

Endpointurile salarii adauga `LEFT JOIN stores` **doar** cand `regional` sau `asm` sunt prezente (evita JOIN inutil).

### Autentificare
- Roluri: `admin`, `management`, `tl`
- `admin` si `management` vad totul
- `tl` vede doar magazinele alocate lui
- Parole default: `9999` pentru admin si management

---

## Cum sa incepi o sesiune noua

1. Citeste acest fisier
2. Intreaba-l pe Andrei ce vrea sa lucreze azi

---

## Verificare end-to-end dupa modificari backend

Dupa orice import de date sau modificare backend (coloane noi, enrichment, logica noua):
1. Query direct in DB — confirma ca valorile sunt corecte
2. Apeleaza endpoint-ul API corespunzator — confirma ca returneaza valorile din DB
3. Confirma ca frontend-ul citeste din sursa corecta (DB vs fisier JSON)

Nu declara task-ul terminat inainte de aceasta verificare. Erorile de tipul `incentive_qty = 0` sau date lipsa apar exact din cauza ca pasul 3 e sarit.

---

## CSS / Layout

La orice modificare de CSS sau layout:
- Testeaza atat pe mobile cat si pe desktop
- Cand un element nu se redimensioneaza corect, verifica: `box-sizing`, `overflow`, constrangerile containerului parinte — nu doar elementul tinta
- Daca utilizatorul raporteaza ca problema e inca vizibila, cere descrierea exacta sau un screenshot inainte de urmatorul fix

---

## Graphify (skill `/graphify`)

Skill versionat in `.claude/skills/graphify/SKILL.md` — calatoreste cu repo-ul, disponibil pe orice masina unde clonezi proiectul. Transforma codul + docs intr-un knowledge graph (HTML + JSON + `GRAPH_REPORT.md`).

**Dependenta**: necesita `graphifyy` (Python 3.10+) instalat pe masina respectiva pentru utilitarele CLI (path / explain / query / update / cluster-only):
```bash
python3 -m venv ~/.venvs/graphify && ~/.venvs/graphify/bin/pip install graphifyy
```

Invocare din Claude Code: `/graphify .` (prima data — full pipeline) sau `/graphify . --update` (incremental, doar AST). Output-ul merge in `graphify-out/` care e in `.gitignore`.

---

## Ce sa nu faci

- Nu crea fisiere temporare in radacina proiectului (`fix.py`, `patch.txt`, etc.) — curata-le dupa
- Nu modifica schema direct in DB
- Nu reseta parolele utilizatorilor fara confirmare explicita
- Nu importa campanii incentive din Excel manual — foloseste `import_incentive_campaign.py`
- Nu aplica fix-uri speculative in cascada fara sa diagnostichezi root cause-ul mai intai
