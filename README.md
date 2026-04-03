# UniHub

UniHub este o aplicatie de operare comerciala pentru retail, construita pentru monitorizarea vanzarilor, a targetelor, a focus products, a promotiilor si a fiselor de vizita din magazine.

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

Aplicatia are doua straturi majore de date:

### 1. Stratul operational brut
Tabelele brute sunt sursa de adevar pentru audit si import:
- `stores`
- `users`
- `tl_store_assignments`
- `focus_products`
- `import_snapshots`
- `sales_transactions`
- `store_targets`
- `visits`

### 2. Stratul agregat de reporting
Acesta este stratul principal folosit de dashboard-uri:
- `reporting_agent_day`
- `reporting_agent_month`
- `reporting_item_day`
- `reporting_item_month`
- `reporting_focus_item_month`
- `reporting_category_month`

Scopul lui este sa evite raportarea direct din `sales_transactions` pentru fiecare request.

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

Vizitele din Platforma-Mobiup sunt citite de UniHub via SQLite read-only (`VISITS_DB_PATH`).

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

## Documente suplimentare

- setup local: [LOCAL_SETUP.md](./LOCAL_SETUP.md)
