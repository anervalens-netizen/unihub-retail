# UniHub

UniHub este o aplicatie de operare comerciala pentru retail, construita pentru monitorizarea vanzarilor, a targetelor, a focus products, a promotiilor, a fiselor de vizita din magazine si a operatiunilor de management (echipa, CRM, tasks, HR).

Aplicatia este gandita pentru lucru local, fara Docker, cu:
- frontend React + Vite
- backend FastAPI
- PostgreSQL ca singura baza de date
- fisiere Excel/JSON din `data/` ca sursa operationala de import

## Module functionale

### Hub
Hub este zona principala de analiza pentru luna in curs si istoric.

Expune:
- status luna curenta
- overview operational
- comparatie perioade
- promo si incentive
- top categorii si top branduri
- top magazine
- panou agenti
- istoric pe mai multe luni

### Focus
Focus este separat in:
- campanii active
- indicator permanent de focus products
- istoric focus

### Fisa de vizita
Permite inregistrarea si urmarirea vizitelor in magazine:
- selectie magazin
- checklist operational
- analiza per agent
- poze
- status si completare

Geolocatia a fost eliminata complet din arhitectura aplicatiei.

### Management
Tab dedicat rolurilor `admin` si `management`, cu 4 sub-taburi:

- **Echipa (ASM)** — performanta ASM combinata din PostgreSQL (vanzari) + SQLite (vizite) + factor de forecast din CRM. Router: `/api/hr`
- **Magazine (CRM)** — scoruri magazine per luna, alerte automate, recalculare manuala. Alertele pot fi convertite direct in Tasks. Router: `/api/crm`
- **Tasks** — task-uri per agent/magazin cu deadline si status. Sursa poate fi manuala sau generata automat din alerte CRM (`source_meta` JSONB). Router: `/api/tasks`
- **HR** — cereri concediu (creare, aprobare/respingere), pontaj zilnic, istoric performanta ASM. Router: `/api/hr`

**Dependenta cross-router:** `hr.py` importa `get_forecast_factor` din `crm.py`.

Tabele noi in `schema_v2.sql`: `tasks`, `leave_requests`, `attendance_records`, `store_scores`.

### UniAI
Asistent de analiză vânzări integrat, alimentat de Hermes AI Agent:
- chat cu memorie persistentă cross-sesiune
- query SQL read-only pe baza de date UniHub
- grafice interactive (bar, line, pie, area) randare în chat
- tabele markdown
- suport atașamente (imagini, PDF, Word, Excel)
- istoric sesiuni cu posibilitate de ștergere

### Setari
Zona administrativa pentru:
- tema
- importuri
- management useri
- focus products (via coding agent, nu din Settings)

## Arhitectura

### Frontend
Codul frontend este in `src/`.

Elemente importante:
- `src/App.tsx` coordoneaza autentificarea, taburile si starea principala
- `src/components/` contine ecranele majore
- `src/api/` contine clientul API si tipurile frontend
- `src/lib/` contine helper-ele comune pentru filtre, cache si formatare

### Backend
Codul backend este in `backend/`.

Punct de intrare:
- `backend/main.py`

Zone importante:
- `backend/routers/` pentru API
- `backend/services/` pentru import, auth, reporting si helpers
- `backend/db/` pentru conexiune si schema
- `backend/scripts/` pentru operare locala

### Baza de date
Nu se foloseste ORM. Accesul la DB se face direct cu `asyncpg`.

Avantaje ale abordarii curente:
- control total pe SQL
- performanta buna pe agregari mari
- usor de optimizat pe rapoarte si istoric

## Cum functioneaza datele

Aplicatia are trei straturi de date:

### 1. Stratul operational brut
Tabelele brute sunt sursa de adevar pentru audit si import:
- `stores`, `users`, `tl_store_assignments`, `focus_products`
- `import_snapshots`, `sales_transactions`, `store_targets`
- `incentive_campaigns`, `incentive_products` — campanii incentive per-produs (importate cu `import_incentive_campaign.py`)
- `tasks`, `leave_requests`, `attendance_records`, `store_scores` — date operationale Management tab

### 2. Stratul agregat de reporting
Acesta este stratul principal folosit de dashboard-uri:
- `reporting_agent_day`, `reporting_agent_month`
- `reporting_item_day`, `reporting_item_month`
- `reporting_focus_item_month`, `reporting_category_month`

Scopul lui este sa evite raportarea direct din `sales_transactions` pentru fiecare request.

### 3. Stratul de date istorice
Pentru perioadele fara tranzactii individuale (2022, 2023 Jan–Aug):
- `historical_annual_sales` — agregate anuale per magazin/firma, importate din `vanzari 2022 si 2023.xlsx`

Acoperirea completa a datelor:
| Perioada | Sursa |
|----------|-------|
| 2022 (integral) | `historical_annual_sales` |
| 2023 Ian–Aug (derivat) | `historical_annual_sales` (`is_partial_year=True`) |
| 2023 Sep–Dec | `sales_transactions` (tranzactii) |
| 2024 Ian–Dec | `sales_transactions` (tranzactii) |
| 2025–prezent | `sales_transactions` (tranzactii) |

Nota: datele 2023-2024 nu au informatii per-agent individual (campul `agent` este `'-'`).

## Fluxul de import

La import:

1. se citeste fisierul Excel
2. se valideaza si normalizeaza coloanele
3. se creeaza un snapshot de import
4. se inlocuieste snapshot-ul completed anterior pentru luna respectiva
5. se insereaza liniile brute in `sales_transactions`
6. se reconstruieste reporting-ul pentru luna respectiva
7. snapshot-ul devine `completed`

Implementarea este in:
- `backend/services/importer.py`
- `backend/services/reporting_refresh.py`

## Integrare Platforma-Mobiup

Platforma-Mobiup (aplicatia veche) citeste datele de vanzari direct din PostgreSQL UniHub via VIEW-uri de compatibilitate. Importul zilnic se face **o singura data**, in UniHub.

VIEW-uri disponibile in `schema_v2.sql`:
- `v_platforma_dashboard` — agregat lunar per agent
- `v_platforma_import_meta` — metadata per luna (is_partial, period_end)
- `v_platforma_raw_sales` — tranzactii brute cu campuri aliasate pentru compatibilitate
- `v_platforma_store_targets` — targete magazine cu detalii firma/asm/regional

**Vizite**: UniHub este sursa de adevar pentru vizite. Ambele aplicatii citesc din acelasi SQLite:
`/opt/Mobiup/unihub/data/visits/visits.db` (configurat via `VISITS_DB_PATH` in `.env`).

## Backup

Backup-urile automate sunt configurate in crontab zilnic la ora 02:00:
- Script: `/opt/Mobiup/scripts/backup.sh`
- Destinatie: `/opt/Mobiup/backups/`
  - `postgres/` — dump PostgreSQL (`pg_dump -Fc`)
  - `visits/` — copie SQLite visits
- Retentie: 30 zile

Restore PostgreSQL:
```bash
pg_restore -d unihub /opt/Mobiup/backups/postgres/<fisier.dump>
```

## Gestionarea schemei DB

Schema principala este in:
- `backend/db/schema_v2.sql`

La startup:
- backend-ul deschide pool-ul
- calculeaza hash-ul fisierului de schema
- compara hash-ul cu valoarea salvata in `schema_meta`
- reaplica schema doar daca s-a schimbat

Asta inseamna:
- nu mai exista reexecutie completa a schemei la fiecare boot
- schema ramane sincronizata cu codul
- startup-ul este mult mai rapid si mai sigur

## Reporting si performanta

Istoricul si dashboard-ul au fost mutate pe agregate persistente.

Rezultatul practic:
- `dashboard/history` este acum rapid si stabil
- `campaigns/history` este rapid
- `filters/months` si `filters/options` sunt foarte rapide
- `dashboard/all` are un prim request mai lent dupa restart, apoi se stabilizeaza

## Bootstrap utilizatori

La startup se asigura:
- existenta userilor core `admin` si `management`
- existenta userilor TL
- optional sincronizarea alocarilor TL

Resetul parolelor default nu este automat. Se face explicit cu scriptul dedicat.

## Rulare locala

Setup-ul complet este in [LOCAL_SETUP.md](./LOCAL_SETUP.md).

Comenzi rapide:

```bash
npm install
npm run dev
npm run dev:backend
```

## Testare

Comenzi importante:

```bash
pytest backend -q
python backend/scripts/smoke_api.py
npm run typecheck
npm run build
```

## Scripturi utile

| Script | Utilizare |
|--------|-----------|
| `backend/scripts/import_incentive_campaign.py` | Import campanie incentive per-produs din Excel in DB |
| `backend/scripts/import_historical.py` | Import date istorice 2023 Q4 + 2024 (tranzactii) |
| `backend/scripts/import_annual_summary.py` | Import agregate anuale 2022/2023 din `vanzari 2022 si 2023.xlsx` |
| `backend/scripts/seed.py` | Seed complet din `data/` |
| `backend/scripts/rebuild_reporting.py` | Rebuild agregate reporting |
| `backend/scripts/reset_default_users.py` | Reset parole utilizatori default |
| `backend/scripts/smoke_api.py` | Smoke test API |
| `/opt/Mobiup/scripts/backup.sh` | Backup zilnic PostgreSQL + SQLite |

## Documente suplimentare

- setup local: [LOCAL_SETUP.md](./LOCAL_SETUP.md)
