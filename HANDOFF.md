# UniHub Handoff

Ultima actualizare: 2026-03-29

Acest document este handoff-ul tehnic complet pentru starea actuala a aplicatiei.

## 1. Rezumat executiv

Aplicatia este functionala local si ruleaza fara Docker.

Starea actuala:
- frontendul ruleaza pe Vite (port 3000)
- backendul ruleaza pe FastAPI + asyncpg (port 8000)
- PostgreSQL este singura baza de date
- importul de vanzari este tranzactional
- reporting-ul este pe agregate persistente
- login-ul local cu JWT este stabilizat
- geolocatia a fost eliminata din fisa de vizita
- tema light nu mai preia starea dark a sistemului
- modulul Agenti este complet implementat (backend + frontend)
- modulul Salarii este implementat si integrat in tab-ul Agenti
- MiniMax M2.7 este disponibil ca agent de coding subordinat via MCP

## 2. Ce face aplicatia

Aplicatia acopera cinci zone majore:

### Hub
Zona principala pentru:
- luna in curs
- istoric
- KPI operationali
- comparatie perioade
- top magazine si top agenti
- promo si incentive
- focus operational

### Focus
Separat de Hub, pentru:
- campanii in curs
- indicatorul permanent de focus products
- istoric focus

### Agenti
Modul complet implementat:
- tab separat intre `Focus` si `Vizite`
- filtre proprii, separate de `Hub` si `Focus`
- overview echipa: activi, noi, reactivati, plecati, retentie
- sanatate echipa: total unici, vechime medie, stabilitate, churn total
- grafic miscare de personal (luna per luna)
- acoperire magazine (covered / uncovered / closed)
- lista agenti paginata cu status si search
- profil detaliat per agent (career stats, storeuri, firme)
- istoric grafic per agent (vanzari, cantitate, prezenta)
- tab Salarii integrat in acelasi ecran

### Fisa de vizita
Formular operational per magazin pentru:
- observatii in teren
- analiza agenti
- poze
- status si completare

### Setari
Zona administrativa pentru:
- importuri
- utilizatori
- TL assignments
- focus products (via coding agent, nu din Settings)
- tema aplicatiei

## 3. Arhitectura aplicatiei

### Frontend
Frontendul este in `src/`.

Piese principale:
- `src/App.tsx`
  coordoneaza autentificarea, taburile si lunile disponibile
- `src/components/MainLayout.tsx`
  gestioneaza shell-ul principal, navigarea si filtrarea
- `src/components/Dashboard.tsx`
  ecranul Hub
- `src/components/Campaigns.tsx`
  ecranul Focus
- `src/components/Agents.tsx`
  ecranul Agenti — complet, include AgentDrawer, AgentDetails, SalariiSubtab
- `src/components/SalariiSubtab.tsx`
  sub-tab salarii integrat in ecranul Agenti
- `src/components/Visits.tsx`
  ecranul de vizite
- `src/components/Settings.tsx`
  zona administrativa
- `src/components/ErrorBoundary.tsx`
  componenta ErrorBoundary (mutata din radacina proiectului)

Observatii:
- taburile folosesc cache local in memorie pentru a evita reincarcari inutile
- componentele mari sunt lazy-loaded
- tema este controlata explicit din clasa CSS, nu din `prefers-color-scheme`
- ErrorBoundary este importat din `./ErrorBoundary`, nu din root

### Backend
Backendul este in `backend/`.

Punct de intrare:
- `backend/main.py`

Routere principale:
- `auth`
- `dashboard`
- `campaigns`
- `filters`
- `imports`
- `stores`
- `visits`
- `admin`
- `agents`  ← modul nou, complet implementat
- `salarii` ← modul nou, complet implementat

Servicii importante:
- `services/importer.py`
- `services/reporting_refresh.py`
- `services/dashboard_specials.py`
- `services/auth_service.py`
- `services/product_lists.py`

## 4. Cum este creata si gestionata baza de date

### 4.1 Sursa de adevar pentru schema

Schema principala este in:
- `backend/db/schema_v2.sql`

Nu exista Alembic sau un sistem formal de migratii in acest moment.

In schimb, baza este sincronizata astfel:
- `backend/db/connection.py` citeste continutul lui `schema_v2.sql`
- calculeaza un hash SHA-256 al fisierului
- compara hash-ul cu valoarea salvata in tabela `schema_meta`
- reaplica schema doar daca hash-ul s-a schimbat

Asta inseamna:
- schema nu se reaplica la fiecare boot
- deploy-ul local si startup-ul sunt mai rapide
- tot proiectul ramane ancorat intr-un singur fisier-sursa de schema

### 4.2 Tabele operationale

Tabelele brute ale aplicatiei sunt:

- `stores`
  master data pentru magazine
- `users`
  useri backend pentru JWT
- `tl_store_assignments`
  alocari TL pe magazine
- `focus_products`
  lista de produse focus
- `import_snapshots`
  jurnalul de import pe luna
- `sales_transactions`
  tranzactiile brute importate din Excel
- `store_targets`
  targete pe magazin si luna
- `visits`
  fisele de vizita
- `salary_records`
  salariile importate (migrat din SQLite la PostgreSQL)

### 4.3 Tabele agregate de reporting

Stratul de reporting este format din:

- `reporting_agent_day`
- `reporting_agent_month`
- `reporting_agent_lifecycle_month`
- `reporting_agent_profile`
- `reporting_item_day`
- `reporting_item_month`
- `reporting_focus_item_month`
- `reporting_category_month`

Rolul lor:
- scot dashboard-ul si istoricul din `sales_transactions`
- fac KPI-urile stabile si rapide
- permit filtrare pe firma, regional, asm, magazin si agent fara recalcul brut complet

### 4.4 Cum se alimenteaza reporting-ul

La fiecare import de vanzari:

1. se valideaza fisierul Excel
2. se determina luna
3. se creeaza un rand in `import_snapshots` cu status `processing`
4. se actualizeaza `stores`
5. se inlocuieste snapshot-ul completed anterior pentru luna respectiva
6. se insereaza datele brute in `sales_transactions`
7. se ruleaza `rebuild_reporting_month(import_month)`
8. snapshot-ul devine `completed`

Daca importul esueaza:
- snapshot-ul devine `failed`
- se pastreaza mesajul de eroare

### 4.5 Ce face `rebuild_reporting_month`

Serviciul din `backend/services/reporting_refresh.py`:
- sterge agregatele lunii respective
- construieste temporar agregatele pe bon pentru bucket-urile `1 / 2 / 3 / 4+`
- populeaza `reporting_agent_day`
- agrega in `reporting_agent_month`
- reconstruieste lifecycle-ul global in `reporting_agent_lifecycle_month`
- reconstruieste profilul global in `reporting_agent_profile`
- populeaza `reporting_item_day`
- agrega in `reporting_item_month`
- populeaza `reporting_focus_item_month`
- populeaza `reporting_category_month`
- ruleaza `ANALYZE` pe tabelele agregate

### 4.6 Starea actuala a agregatelor

Pe baza locala curenta:
- `reporting_agent_day`: `40,798`
- `reporting_agent_month`: `3,014`
- `reporting_agent_lifecycle_month`: `2,853`
- `reporting_agent_profile`: `381`
- `reporting_item_day`: `623,007`
- `reporting_item_month`: `409,009`
- `reporting_focus_item_month`: `27,215`
- `reporting_category_month`: `76,245`

Statusuri agent lifecycle:
- `active`: `174`
- `inactive_recent`: `12`
- `churned`: `195`

## 5. Cum sunt apelate datele de catre aplicatie

### Dashboard / Hub
In forma actuala:
- `summary`, `daily`, `stores`, `agents`, `history`
  citesc in principal din agregatele `reporting_*`
- `special cards`
  folosesc agregate pentru majoritatea metricilor
- a ramas intentionat un query brut doar pentru `COUNT(DISTINCT bon_nr)` la promotii, pentru a pastra bonurile exacte

### Focus / Campaigns
Foloseste:
- `reporting_focus_item_month`
- `reporting_agent_month`
- `reporting_category_month`

### Agenti
Endpointuri dedicate in `backend/routers/agents.py`:
- `GET /api/agents/overview` — snapshot luna + sanatate echipa
- `GET /api/agents/movement` — evolutie lunara activi/noi/reactivati/churned/net_growth
- `GET /api/agents/list` — lista paginata cu filtre
- `GET /api/agents/profile/{agent_name}` — profil detaliat agent
- `GET /api/agents/history/{agent_name}` — istoric lunar per agent
- `GET /api/agents/stores-coverage` — acoperire magazine

Toate folosesc `reporting_agent_lifecycle_month`, `reporting_agent_profile`, `reporting_agent_month`.

### Salarii
Endpointuri in `backend/routers/salarii.py`:
- `GET /api/salarii/overview` — total, per companie, span luni
- `GET /api/salarii/evolution` — evolutie lunara totala si pe companie
- `GET /api/salarii/agents` — lista agenti cu total si medie
- `GET /api/salarii/agent/{name}/history` — istoricul complet al unui agent
- Date din tabela `salary_records`

### Filters
Lunile si optiunile de filtrare nu mai citesc brut din tranzactii pentru raportare generala.

### Vizite
Vizitele raman operationale si se bazeaza pe:
- `visits`
- `stores`
- autentificare JWT si scope pe roluri

## 6. Bootstrap si autentificare

### JWT
Login-ul este:
- `POST /api/auth/login`
- `username + password`
- raspuns cu `access_token`

Roluri: `admin`, `management`, `tl`

### Useri impliciti
Backend-ul creeaza doar daca lipsesc:
- `admin`
- `management`

Nu reseteaza implicit parolele existente.

Reset explicit:

```powershell
python backend/scripts/reset_default_users.py
```

### TL users
TL-urile sunt definite in:
- `backend/bootstrap.py`

La boot:
- se asigura existenta conturilor TL
- alocarile TL se sincronizeaza doar daca flag-ul de env o cere

## 7. Fisiere si configurari importante

### In radacina
- `.env`
- `.env.example`
- `LOCAL_SETUP.md`
- `README.md`
- `HANDOFF.md`
- `CLAUDE.md` ← ghid pentru sesiunile Claude

### In `data/`
- fisiere Excel de vanzari
- fisiere Excel de target
- fisiere Excel de focus
- `hub_specials.json`
- fisierul de incentive referit din config

### Config special cards
Special cards se configureaza din:
- `data/hub_specials.json`

Cache-ul acestor configurari este preincalzit la startup.

## 8. Verificari si status actual

Verificari trecute:
- `pytest backend -q` -> `27 passed`
- `python backend/scripts/smoke_api.py` -> succes
- `npm run typecheck` -> succes
- `npm run build` -> succes

Verificare schema:
- `ensure_schema_current()` pe schema deja la zi -> `applied=False` in ~`6.8 ms`

## 9. Performanta actuala

Timpi live masurati, la cald:
- `dashboard/agents` -> ~`28.8 ms`
- `dashboard/special-cards` -> ~`41.4 ms`
- `dashboard/history` -> ~`178.7 ms`
- `campaigns/history` -> ~`88.5 ms`

Pentru `dashboard/all`:
- primul request dupa restart poate fi mai lent
- dupa warm-up se stabilizeaza in jur de `70-120 ms`

## 10. Limitari si datorie tehnica ramasa

Inca deschise:
- nu exista sistem formal de migratii versionate
- `import_month` este inca `TEXT`, nu tip temporal dedicat
- exista view-uri legacy (`v_agent_monthly`, `v_store_monthly`) care au ramas in schema, dar dashboard-ul nu mai depinde de ele pentru fluxurile principale
- exista cateva lookup-uri administrative care mai citesc din `sales_transactions`:
  - completare nume produs in `admin`
  - sincronizare focus products din `product_lists`
- nu exista suita de teste frontend

## 11. Recomandari pentru urmatoarea etapa

Ordinea recomandata:

1. imbunatatiri UX pe modulul Agenti (ex: sortare lista, chart interactiv, comparatie agent)
2. imbunatatiri pe Salarii (ex: grafic per agent, comparatie perioadele)
3. lucrul functional pe `Istoric` Hub si UX, acum ca reporting-ul este stabil
4. eventual adaugare target per agent (nu doar per magazin)
5. eventual mutare la migratii reale
6. eventual conversie `import_month` la un model temporal mai curat
7. eventual testare frontend end-to-end

## 12. Comenzi utile

Pornire frontend:

```powershell
npm run dev
```

Pornire backend:

```powershell
npm run dev:backend
```

Seed complet:

```powershell
python backend/scripts/seed.py
```

Rebuild reporting:

```powershell
python backend/scripts/rebuild_reporting.py
```

Smoke:

```powershell
python backend/scripts/smoke_api.py
```
