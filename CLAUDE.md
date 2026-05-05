# CLAUDE.md — UniHub (retail)

## Overview

**Sursa de adevar** pentru vanzari + vizite in ecosistemul MobiUp. Platforma-Mobiup citeste de aici via VIEW-uri `v_platforma_*`. Module: Hub, Focus, Agenti (+Salarii), Vizite, Management (Echipa/Magazine/Tasks/HR), Setari, UniAI.

## Stack

- Frontend: React 19 + Vite + TypeScript
- Backend: FastAPI + asyncpg + PostgreSQL 18
- Realtime AI: WebSocket (UniHub) ↔ Hermes SSE bridge (`hermes-unihub-bridge`, systemd user)
- Test: pytest (backend), vitest (frontend)

## Deploy

- Path: `/opt/Mobiup/unihub-retail` (symlink logic: `/opt/Mobiup/unihub` — folosit in comenzi deploy)
- Service: `unihub-backend.service`
- URL public: `https://retail.unihub.ro/` (ex `unihub.astancu.eu`, eliminat 2026-04-19)
- Deploy standard:
  ```bash
  cd /opt/Mobiup/unihub
  git pull
  npm run build
  sudo systemctl restart unihub-backend
  ```
- Pentru UniAI / bridge Hermes:
  ```bash
  sudo -u andrei XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
    systemctl --user restart hermes-unihub-bridge
  ```

## Commands

```bash
npm run build               # frontend Vite build
npm run test                # vitest (formatters, viewCache)
pytest                      # backend tests
sudo journalctl -u unihub-backend -f   # logs live
```

## Structura

### Frontend `src/components/`
| Fisier | Rol |
|--------|-----|
| `App.tsx` | Tab routing + localStorage persistence tab activ |
| `MainLayout.tsx` | Shell principal, navigare, filtre globale |
| `Dashboard.tsx` | Tab Hub — Luna curenta + Istoric (4 tabele: RM/ASM/Magazine/Agenti) |
| `Campaigns.tsx` | Tab Focus — campanii, incentive per-produs, Top Agenti/Magazine |
| `Agents.tsx` + `AgentDrawer`, `AgentDetails` | Tab Agenti |
| `SalariiSubtab.tsx` + `SalaryDrawer`, `SalaryAgentBarChart`, `SalaryAreaChart` | Sub-tab Salarii |
| `VisiteSubtab.tsx` | Tab Vizite — ASM accordion + drawer cu poze |
| `Management.tsx` + 4 sub-taburi: `ASMSubtab`, `CRMSubtab`, `TasksSubtab`, `HRSubtab` | Management |
| `AIChat.tsx` | Tab AI — chat UI, sesiuni, attachments |
| `Settings.tsx` + `ErrorLogsTab` + `ErrorBoundary` | Setari + Erori sistem |

### Backend `backend/routers/`
| Router | Prefix |
|--------|--------|
| `dashboard` | `/api/dashboard` |
| `campaigns` | `/api/campaigns` |
| `filters` | `/api/filters` |
| `imports` | `/api/imports` |
| `stores` | `/api/stores` |
| `visits_report` | `/api/visits-report` (SQLite `data/visits/visits.db`) |
| `agents` | `/api/agents` |
| `salarii` | `/salarii` (**fara** prefix `/api`) |
| `tasks` | `/api/tasks` |
| `hr` | `/api/hr` (PG + `visits_snapshot`, NU mai citeste SQLite direct) |
| `crm` | `/api/crm` |
| `ai` | `/api/ai` (WS proxy + sesiuni + attachments pentru Hermes bridge) |
| `errors` | `/api/errors` (public, rate limit) + `/api/admin/error-logs` |

Helperele de filtre/scope → `services/filters.py`. Forecast shared CRM/HR → `services/forecast.py`. Dashboard greu → `services/dashboard/{utils,queries,specials_data}.py`.

**Regula import cross-router:** alte routere importa direct din `services.dashboard.queries` — **niciodata** din `routers.dashboard`.

### UniAI — sesiuni persistente cross-sesiune

- Frontend: `src/components/AIChat.tsx` + `src/api/ai.ts` (WS) + `src/api/aiSessions.ts` (REST)
- Backend: `backend/routers/ai.py` (WS `/api/ai/ws` + REST sesiuni/attachments)
- Hermes bridge: `/home/andrei/.hermes/hermes-agent/unihub_bridge.py` + `unihub_session_store.py`
- `device_id` in `localStorage` (`unihub_ai_device_id`), transcript in Hermes `SessionDB` (SQLite)
- Sesiuni active per-device mapate in `~/.hermes/sessions/unihub_active_sessions.json`
- `memory.md` cross-sesiune in `/opt/Mobiup/unihub/data/uniai-workspace/`, config in `/home/andrei/.hermes/SOUL.md`
- Attachments: imagini (vision), `.txt`, `.md`, PDF (`pdftotext`), `.docx/.xlsx/.pptx`
- Charts in chat: Hermes returneaza blocuri ```chart cu JSON spec; randat de `ChartBlock` (recharts: bar/line/pie/area)
- Env: `AI_BRIDGE_URL` (default `http://127.0.0.1:7777`), `AI_BRIDGE_TIMEOUT` (default 180s)

### Tab Management — dependente cheie

`hr.py` importa `get_forecast_factor` din `crm.py` → la modificari CRM verifica si HR.
`get_forecast_factor(conn, month)` = factor extrapolat (`zile_luna / ultima_zi_vanzari`); 1.0 daca luna e finalizata.

## Baza de date

- Schema unica: `backend/db/schema_v2.sql`
- Aplicata hash-based la boot via `ensure_schema_current()` in `backend/db/connection.py`
- **Nu modifica schema direct in DB** — editeaza `schema_v2.sql` si reporneste backend-ul

### Tabele principale
| Tabel | Continut |
|-------|----------|
| `sales_transactions` | Tranzactii detaliate 2023-09 → prezent |
| `historical_annual_sales` | Agregate anuale: 2022 complet, 2023 Ian-Aug |
| `incentive_campaigns` + `incentive_products` | Campanii incentive + produse eligibile |
| `store_targets` | Targete lunare per magazin |
| `stores` | Magazine: site_code, locatie, firma, asm, regional |
| `reporting_agent_month` / `reporting_item_month` | Agregate lunare (sursa dashboard) |
| `tasks` | Task-uri per agent/magazin (`source` = `manual` / `crm_alert`) |
| `leave_requests` / `attendance_records` | HR |
| `store_scores` | Scoruri CRM per magazin/luna |
| `visits_snapshot` | Agregat vizite sync din SQLite la boot |
| `error_logs` | Erori backend + frontend cu `seen` flag |

### VIEW-uri pentru Platforma-Mobiup
- `v_platforma_dashboard` — agregat agent (`reporting_agent_month` JOIN `stores`)
- `v_platforma_import_meta` — metadata import
- `v_platforma_raw_sales` — tranzactii brute (`bon_nr` aliased ca `nr`)
- `v_platforma_store_targets` — targete JOIN stores

### Acoperire date
| Perioada | Sursa | Granularitate |
|----------|-------|---------------|
| 2022 | `historical_annual_sales` | anual/magazin |
| 2023 Ian-Aug | `historical_annual_sales` | anual/magazin (derivat) |
| 2023 Sep → prezent | `sales_transactions` | tranzactie |

2023-2024 nu aveau coloana `Agent` (prezenta din 2025) → `agent = '-'`. Raport per-ASM/magazin ramane corect.

## Conventions

**Nu citi din `sales_transactions` pentru raportare.** Toate query-urile merg pe agregatele `reporting_*`. Exceptie: lookup-uri administrative.

**Pydantic silent-drop.** Orice camp returnat de endpoint trebuie declarat in modelul Pydantic din `backend/models.py`. Modelele cu `ConfigDict(from_attributes=True)` sunt deosebit susceptibile — SQL poate calcula campul, dar daca nu e in model, dispare din raspuns fara eroare.

**Filtre shared.** `MainLayout` (`hubFilters`) e shared Hub+Focus. Agenti foloseste `agentsFilters` (independent). `SalariiSubtab` primeste `globalFilters: AppFilters` care sunt de fapt `agentsFilters`, nu `hubFilters`.

**Salarii case-insensitive join.** `salary_records.company_name` (`'Mobicell'`/`'Mobiup'`) difera ca majuscule de `stores.firma` (`'MobiCell'`/`'MobiUp'`) → folosește `LOWER()` la JOIN.

**Salarii LEFT JOIN conditionat.** `LEFT JOIN stores` doar cand `regional` sau `asm` sunt prezente (evita JOIN inutil).

## Integrare Platforma-Mobiup

- Importul de vanzari se face **o singura data**, in UniHub — Platforma citeste via VIEW-uri. Ruta `/api/v2/intermediate-import` din Platforma returneaza 410 Gone.
- Vizite: sursa = `data/visits/visits.db` + `data/visits/images/`
  - Platforma citeste acelasi SQLite (hardcoded la `/opt/Mobiup/unihub/data/visits/visits.db`)
  - `visits_report.py` citeste async via `run_in_executor`
  - `/api/visits-report/photo/{visit_id}/{filename}` serveste pozele cu auth → `FileResponse`
  - Frontend: `AuthImage` face fetch blob cu axios + `URL.createObjectURL` (nu `<img src>` direct)
  - `hr.py` foloseste PG `visits_snapshot` (sync la boot), **nu** SQLite

## Hub Dashboard — structura tabele

**Luna in curs** si **Istoric** afiseaza amandoua 4 tabele: RM, ASM, Magazine, Agenti.

- Magazine: Magazin / Firma / Target / Vanzari / Procent / **Incentive** / Cantitate / Nr bonuri / Agenti / Zile active / Medie zilnica
- RM / ASM / Agenti: fara `promo_qty` in Istoric (filtrat la render)
- `incentive_qty` la Magazine calculat in `_enrich_store_stats_with_campaign()` din `dashboard.py` (query pe `reporting_item_month` grupat pe `site_code`). **Daca lipseste functia, valorile apar 0.**

### Pattern enrichment campanie (RM/ASM/Magazine/Agenti)
1. Incarca `promotion_codes` + `incentive_codes` din config/DB
2. Niciun cod activ → seteaza 0 si returneaza
3. Query `reporting_item_month` grupat pe cheia relevanta
4. Join pe rows si ataseaza `promo_qty` + `incentive_qty`

### Incentive vs Promotii
- **Incentive:** stocate complet in DB (`incentive_campaigns` + `incentive_products`). `hub_specials.json` are doar `promotions`, sectiunea `incentives` goala. Logica: `backend/services/incentive_db.py` → `get_incentive_campaign(conn, month)`. Dashboard citeste reward_map din DB, nu Excel.
- **Promotii:** `data/hub_specials.json` → array `promotions` cu `item_codes`, `start_date`, `end_date`
- Cardurile inactive se ascund automat in Istoric

### Import campanie incentive noua
```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
python3 scripts/import_incentive_campaign.py \
    --month 2026-05 \
    --title "Incentive Mai 2026" \
    --file "NumeFisier.xlsx" \
    --sheet Sheet1 \
    [--header 1]
```

## Targete magazine

- Tabel: `store_targets (site_code, import_month, target_value)`
- Format fisier nou per luna: coloane `Regional, ASM, Firma, Locatie, Cod, Target` (sheet `target`)
- **Nu** folosi `load_targets_dataframe()` pentru acest format (aceea e pentru `Istoric targete.xlsx`)
- Import: script Python direct cu `upsert_store_targets()`, din `backend/` cu venv activat

## Scripts utile (`backend/scripts/`)
| Script | Scop |
|--------|------|
| `import_historical.py` | Import batch fisiere vechi 2023/2024 (fara Agent/Categorie) |
| `import_annual_summary.py` | Import rezumat anual `vanzari 2022 si 2023.xlsx` |
| `import_incentive_campaign.py` | Import campanie incentive din Excel in DB |
| `rebuild_reporting.py` | Reconstruieste agregatele reporting (toate lunile / una anume) |
| `seed.py` | Seed complet din `data/` |

## Backup

- Locatie unica: `/opt/Mobiup/backups/` — `postgres/`, `visits/`, `platforma-mobiup/`, `backup.log`
- Script: `/opt/Mobiup/scripts/backup.sh`
- Timer: `mobiup-backup.timer` (zilnic 03:00, retentie 30 zile)
- Restore PG: `pg_restore -h localhost -U unihub -d unihub --clean <dump>`

## Error Tracking intern

**Backend:** `DBErrorHandler` in `logging_config.py` — `logging.ERROR+` → `error_logs` via `asyncio.create_task` (non-blocking). Atasat in `main.py` dupa `init_db_pool()`.

**Frontend:**
- `window.onerror` + `window.onunhandledrejection` in `src/main.tsx`
- `ErrorBoundary.componentDidCatch` pentru crash-uri React
- Toate → `POST /api/errors` (public, rate limit 10 req/min/IP)

**Vizualizare:** Settings → "Erori sistem" (`ErrorLogsTab.tsx`). Filtre sursa/seen, modal traceback, buton "Marcheaza toate ca vazute".

**Badge:** `App.tsx` poll `/api/admin/error-logs/unseen-count` la 60s.

**Cleanup auto:** la boot, intrari > 30 zile sterse (`delete_old_logs`).

## JSON structured logging

`LOG_FORMAT=json` → fiecare linie log = obiect JSON cu `ts`, `level`, `logger`, `message`, `exc_info`. Implicit: format text uvicorn. Util pentru `jq` / Grafana Loki.

## Skills

- `/graphify` — knowledge graph din cod + docs (HTML + JSON + `GRAPH_REPORT.md`). Versiunat in `.claude/skills/graphify/SKILL.md`. Necesita `graphifyy` (Python 3.10+): `python3 -m venv ~/.venvs/graphify && ~/.venvs/graphify/bin/pip install graphifyy`. Output → `graphify-out/` (gitignored).

## Gotchas

- **UniAI bridge session partitioning:** `BRIDGE_USER_ID = "default"` (constanta in `ai.py`) — nu exista auth per-user
- **Mobile address-bar jump fix:** tabul AI are `overflow-hidden` (nu `overflow-y-auto`) in `MainLayout.tsx` — scroll-ul e gestionat intern de messages area
- **Promo_qty calculat dar neafisat:** SQL-ul returneaza `promo_qty` si pentru Istoric, dar componenta filtreaza la render pe RM/ASM/Agenti
- **2023-2024 `agent = '-'`:** nu e bug, e lipsa coloana Agent in fisierele sursa

## Ce sa nu faci

- Nu crea fisiere temporare in radacina (`fix.py`, `patch.txt`) — curata-le
- Nu modifica schema direct in DB — editeaza `schema_v2.sql`
- Nu importa campanii incentive din Excel manual — foloseste `import_incentive_campaign.py`
