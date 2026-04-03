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
- Module functionale: Hub, Focus, Agenti (+ Salarii), Vizite, Setari, AI
- 26 pytest passing, typecheck curat, build passing
- Integrata cu Platforma-Mobiup pentru vizite (SQLite read-only)
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
| `Dashboard.tsx` | Tab Hub — carduri Incentive/Promo, navigare catre Focus |
| `Campaigns.tsx` | Tab Focus — campanii, incentive per-produs |
| `Agents.tsx` | Tab Agenti — include AgentDrawer, AgentDetails |
| `SalariiSubtab.tsx` | Sub-tab Salarii in Agenti |
| `SalaryDrawer.tsx` | Drawer detalii salariu per agent |
| `SalaryAgentBarChart.tsx` | Bar chart salarii per agent |
| `SalaryAreaChart.tsx` | Area chart evolutie salarii |
| `VisiteSubtab.tsx` | Tab Vizite — ASM accordion + drawer vizita cu poze |
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
| `visits_report` | `/api/visits-report` — citeste SQLite Platforma-Mobiup |
| `admin` | `/api/admin` |
| `agents` | `/api/agents` |
| `salarii` | `/api/salarii` |
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
  - `DELETE /api/ai/sessions/{session_id}` — șterge sesiunea din Hermes SQLite
  - `POST /api/ai/attachments`
  - `WS /api/ai/ws?token=...&device_id=...&session_id=...`

- Suport attachments: imagini (vision), `.txt`, `.md`, PDF (`pdftotext`), `.docx/.xlsx/.pptx`

- Grafice în chat: Hermes poate returna blocuri `\`\`\`chart` cu JSON spec; frontend-ul le randează via `ChartBlock` (recharts). Tipuri: `bar`, `line`, `pie`, `area`.

- Memorie cross-sesiune: Hermes citește/scrie `memory.md` în workspace (`/opt/Mobiup/unihub/data/uniai-workspace/`) la prima interacțiune din sesiune. Configurat în `/home/andrei/.hermes/SOUL.md`.

- Gotcha important:
  - bridge-ul trebuie sa creeze `AIAgent` cu `session_id` + `session_db`, iar payload-ul catre bridge trebuie sa includa `user_id`
  - `MainLayout.tsx`: tabul AI are `overflow-hidden` (nu `overflow-y-auto`) — scroll-ul e gestionat intern de messages area pentru a preveni saltul address bar-ului pe mobile

- Variabile de mediu:
  - `AI_BRIDGE_URL` — adresa bridge Hermes (default: `http://127.0.0.1:7777`)
  - `AI_BRIDGE_TIMEOUT` — timeout in secunde (default: `180`)

### Baza de date
- Schema unica: `backend/db/schema_v2.sql`
- Aplicata hash-based la boot via `ensure_schema_current()` in `backend/db/connection.py`
- **Nu modifica schema direct in DB** — editeaza `schema_v2.sql` si reporneste backend-ul
- Reporting pe agregate: `reporting_agent_*`, `reporting_item_*`, `reporting_focus_*`, `reporting_category_*`

### Integrare Platforma-Mobiup (vizite)
- SQLite read-only: `VISITS_DB_PATH` in `.env` (default: `/opt/Mobiup/Platforma-Mobiup/db/visit_reports.db`)
- Poze: `VISITS_IMAGES_DIR` in `.env` (default: `/opt/Mobiup/Platforma-Mobiup/local-data/visit-reports/images/`)
- Router `visits_report.py` citeste SQLite async via `run_in_executor` (non-blocking)
- Endpoint `/api/visits-report/photo/{visit_id}/{filename}` serveste pozele cu auth (`FileResponse`)
- Frontend: componenta `AuthImage` face fetch blob cu axios + `URL.createObjectURL` (nu `<img src>` direct)

### Hub Specials (incentive/promotii)
- Configuratie: `data/hub_specials.json`
- Logica: `backend/services/dashboard_specials.py`
- Arhitectura multi-luna: `incentives` si `promotions` sunt array-uri, fiecare entry are `month`
  - `parse_promotion_definition(config, month)` si `parse_incentive_definition(config, month)`
  - Returneaza `(None, None)` daca nu exista config pentru luna respectiva
  - Cardurile inactive se ascund automat in sectiunea Istoric
- Incentive per-produs: fisier Excel cu col A = cod produs, col C = valoare incentive
  - Calcul: `SUM(qty × reward_per_item)` in Python dupa fetch SQL
  - Cache invalidat la modificarea fisierului (tuple `(filepath, mtime)`)

### Targete magazine
- Tabel: `store_targets (site_code, import_month, target_value)`
- Format fisier nou per luna: `Regional, ASM, Firma, Locatie, Cod, Target` (sheet "target")
- **Nu** folosi `load_targets_dataframe()` pentru acest format — aceea e pentru `Istoric targete.xlsx`
- Pattern import: script Python direct cu `upsert_store_targets()`, rulat din `backend/` cu venv activat

---

## Reguli de lucru

### Nu citi din `sales_transactions` pentru raportare
Toate query-urile de raportare merg pe agregatele `reporting_*`. Exceptie: lookup-uri administrative punctuale.

### Modele Pydantic in `backend/models.py`
Orice camp returnat de un endpoint trebuie sa fie declarat explicit in modelul Pydantic corespunzator, altfel Pydantic il elimina din raspuns.

### Filtre in frontend
Filtrul global (firma, regional, asm, magazin) din `MainLayout` este shared intre Hub si Focus.
Modulul **Agenti** are filtrele sale proprii, independente.

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

## Ce sa nu faci

- Nu crea fisiere temporare in radacina proiectului (`fix.py`, `patch.txt`, etc.) — curata-le dupa
- Nu modifica schema direct in DB
- Nu reseta parolele utilizatorilor fara confirmare explicita
