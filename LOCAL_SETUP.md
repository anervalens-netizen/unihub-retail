## Setup Local UniHub

Acest proiect ruleaza local, fara Docker.

Stack:
- frontend: React 19 + Vite
- backend: FastAPI + asyncpg
- baza de date: PostgreSQL
- fisiere de business: Excel/JSON din `data/`

## 1. Cerinte

Ai nevoie de:
- Node.js 20+
- Python 3.12+ sau 3.14
- PostgreSQL local

## 2. Pregatire PostgreSQL

Aplicatia foloseste implicit:

```env
DATABASE_URL=postgresql://unihub:unihub_dev_password@localhost:5432/unihub
```

Daca pornesti de la zero, intra in `psql` cu utilizatorul tau de admin PostgreSQL si ruleaza:

```sql
CREATE ROLE unihub WITH LOGIN PASSWORD 'unihub_dev_password';
CREATE DATABASE unihub OWNER unihub;
GRANT ALL PRIVILEGES ON DATABASE unihub TO unihub;
```

Important:
- nu se sterge baza la boot
- schema este verificata la startup si se reaplica doar daca `backend/db/schema_v2.sql` s-a schimbat
- starea schemei este urmarita in tabela `schema_meta`

## 3. Configurare `.env`

In radacina proiectului exista `.env` si `.env.example`.

Valorile locale relevante:

```env
DATABASE_URL=postgresql://unihub:unihub_dev_password@localhost:5432/unihub
JWT_SECRET=change_me_local_only
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=9999
DEFAULT_MANAGEMENT_USERNAME=management
DEFAULT_MANAGEMENT_PASSWORD=9999
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## 4. Instalare dependinte

Frontend:

```bash
npm install
```

Backend:

```bash
cd backend
python -m pip install -r requirements.txt
cd ..
```

## 5. Pornire dezvoltare

Frontend:

```bash
npm run dev
```

Backend:

```bash
npm run dev:backend
```

Aplicatia va fi disponibila pe:
- frontend: `http://127.0.0.1:3000`
- backend: `http://127.0.0.1:8000`
- health: `http://127.0.0.1:8000/health`

## 6. Acces de pe telefon, in aceeasi retea

Scripturile actuale pornesc pe `0.0.0.0`, deci frontendul si backendul sunt expuse si in LAN.

Adauga IP-ul masinii tale de dev in `.env`:
```env
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://<IP-PC>:3000
```

Atentie:
- telefonul trebuie sa fie pe acelasi Wi-Fi
- firewall-ul trebuie sa permita traficul local pe portul 3000

## 7. Bootstrap utilizatori si login

La startup, backend-ul:
- initializeaza pool-ul PostgreSQL
- verifica schema
- creeaza userii core daca lipsesc
- nu reseteaza automat parolele existente

Credentiale locale implicite:

```text
admin / 9999
management / 9999
```

Daca login-ul nu merge pentru ca userul exista deja cu alta parola, ruleaza reset explicit:

```bash
cd backend
python scripts/reset_default_users.py
cd ..
```

Optional, doar pentru debug local, poti forta resetul la fiecare boot:

```env
RESET_DEFAULT_USERS_ON_BOOT=true
```

Implicit, acest flag trebuie sa ramana dezactivat.

## 8. Seed, import si rebuild reporting

### Seed complet din `data/`

```bash
cd backend
python scripts/seed.py
cd ..
```

Ce face:
- importa fisierele de vanzari
- importa targetele
- sincronizeaza focus products
- reconstruieste agregatele de reporting
- sincronizeaza utilizatorii TL si alocarile lor

### Rebuild agregate reporting

```bash
cd backend
python scripts/rebuild_reporting.py
cd ..
```

Sau pentru o luna anume:

```bash
cd backend
python scripts/rebuild_reporting.py --month 2026-03
cd ..
```

### Grile salariale

Subtab-ul `Management -> Grile` foloseste Google Sheets permanente si datele
din Retail DB.

Pentru verificari sunt necesare:

- tabela `grile_sheets` populata cu `site_code -> sheet_id`;
- `backend/config/google/service-account.json` (gitignored), share-uit pe
  grilele permanente.

Inchiderea de luna ruleaza nativ in Retail, prin worker:

- finalizare salarii;
- arhiva XLSX/ZIP;
- reset dry-run/live.

Output-urile locale sunt in `backend/outputs/grile` si sunt gitignored.
Repo-ul vechi `/opt/Mobiup/grile-salarii` nu mai este runtime public; ramane
doar pentru CLI-uri istorice si reparatii punctuale.

### Sync focus products (optional — via coding agent)

Scriptul load_focus_products.py exista dar nu mai este accesibil din UI. Focus products se adauga prin coding agent direct in DB sau via seed.

### Import date istorice (one-time, deja rulat pe productie)

Date tranzactii 2023 Q4 + 2024:
```bash
cd backend
python scripts/import_historical.py
cd ..
```

Agregate anuale 2022 + 2023 Jan–Aug:
```bash
cd backend
python scripts/import_annual_summary.py
cd ..
```

### Import campanie incentive per-produs

Campaniile de incentive sunt stocate in DB (tabelele `incentive_campaigns` si `incentive_products`).
Import dintr-un fisier Excel:

```bash
cd backend
python scripts/import_incentive_campaign.py \
    --month 2026-04 \
    --title "Incentive Aprilie 2026" \
    --file "../data/incentive-apr-2026.xlsx" \
    [--header 1]   # daca headerul e pe rand 2 (0-indexed)
    [--dry-run]
cd ..
```

Coloane Excel detectate automat (alias-uri acceptate):
- Cod produs: `Cod`, `ItemCode`, `cod_produs`, `code`, `sku`
- Valoare incentive: `Incentive`, `Valoare`, `Bonus`, `Reward`, `valoare_incentive`
- Nume produs (optional): `ItemName`, `Denumire`, `name`

### Configurare promo si concursuri

Promotiile speciale si concursurile live sunt in JSON-uri din `data/`, iar
directorul `data/` este gitignored. Asta inseamna ca aceste fisiere trebuie
pastrate/sincronizate operational pe server, separat de commit:

- `data/hub_specials.json` — promotii speciale folosite de cardurile Hub si
  tabul Focus -> Promo.
- `data/contests.json` — concursuri config-driven folosite de
  `/api/contests/active?month=YYYY-MM`.

Pentru campania iunie 2026, `hub_specials.json` contine 47 coduri si perioada
`2026-06-01` - `2026-06-30`. Regula de masurare este co-purchase, implementata
in `backend/services/promo_copurchase.py`: bon calificat = acelasi
`(sale_date, site_code, agent, bon_nr)` cu cel putin un produs din lista promo
si cel putin doua unitati pozitive non-cartela.

Metrici importante:
- `promo_qty` ramane agregatul simplu din reporting pentru KPI-uri/tabele Hub.
- `promo_qualifying_bons`, `promo_discounted_units`, `promo_active_stores` si
  `promo_active_agents` sunt metricile corecte pentru tabul Focus -> Promo si
  trebuie sa corespunda cardului Hub special.
- unitatea redusa co-purchase se exclude din incentive doar cand exista promo
  activa pe luna respectiva.

Lunile afisate in UI vin exclusiv din `import_snapshots.status='completed'`.
Nu forta luni configurate dar fara import in `/api/filters/months`; iunie 2026
apare automat dupa primul import de vanzari iunie.

### Import targete reale per agent din Grile Salarii

Pilotul curent importa targete per agent din `/opt/Mobiup/grile-salarii`,
doar pentru managerul Andrei Stancu. Scriptul citeste
`store_metadata.json` si `outputs/monitor_output.json`, apoi scrie in tabela
`agent_targets`. Implicit ruleaza dry-run:

```bash
python backend/scripts/import_grile_agent_targets.py --month 2026-05
python backend/scripts/import_grile_agent_targets.py --month 2026-05 --apply
```

Hub foloseste targetul din `agent_targets` doar pentru agentii mapati; restul
raman pe fallback-ul vechi `target magazin / agenti activi`.

### Management -> Grile

Integrarea Grile din Retail este fluxul activ pentru verificare si inchidere
de luna. Verificarea citeste Google Sheets si Retail DB; inchiderea de luna
ruleaza nativ prin worker pentru finalizare salarii, arhiva XLSX/ZIP si reset
lunar guarded. Output-urile se scriu in `backend/outputs/grile`.

`/opt/Mobiup/grile-salarii` este doar arhiva/CLI pentru reparatii punctuale si
fallback operational, nu runtime public.

### Note UI Hub

- Filtrele Hub, Focus si Agenti se salveaza in `localStorage`, ca refresh-ul
  paginii sa pastreze selectia curenta.
- Tabelele curente `RM` si `Magazine` afiseaza `Forecast%` dupa `Procent`.
  Valoarea vine din backend (`forecast_target_pct`) si proiecteaza vanzarile
  pana la finalul lunii cand luna importata este partiala.
- Cardul `Comparatie perioade` afiseaza delte doar pentru vanzari, bonuri si
  cantitate; medie zilnica ramane doar in tabelul de comparatie.
- Cardul `Comparatie perioade` este like-for-like: pentru luna analizata,
  magazinele cu vanzari Retail sunt tratate ca magazine deschise, iar
  comparatia cu luna trecuta/anul trecut foloseste strict aceleasi
  `site_code`.
- Daca este selectat un RM sau o firma, acea selectie stabileste cohorta din
  luna analizata; vanzarile istorice ale acelor magazine se pastreaza chiar
  daca magazinul apartinea anterior altui RM sau altei firme.

### Note Vizite

- FieldOps scrie vizitele in `data/visits/visits.db`, cu codul magazinului in
  coloana `magazin`.
- Retail imbogateste vizitele cu mapping-ul curent din `stores`; filtrele RM
  si firma nu trebuie aplicate direct pe coloanele `regional`/`firma` din
  SQLite, pentru ca randurile istorice pot avea valori vechi sau goale.

## 9. Cum sunt gestionate datele

Fluxul standard este:

1. se importa Excel-ul unei luni
2. se creeaza un `import_snapshot`
3. se inlocuieste snapshot-ul completed anterior pentru luna respectiva
4. se insereaza liniile brute in `sales_transactions`
5. se reconstruieste stratul de reporting pentru luna respectiva
6. snapshot-ul devine `completed`

Dashboard-urile si istoricul nu mai citesc in principal din `sales_transactions`, ci din tabele agregate:
- `reporting_agent_day`
- `reporting_agent_month`
- `reporting_item_day`
- `reporting_item_month`
- `reporting_focus_item_month`
- `reporting_category_month`

## 10. Verificari utile

Backend tests:

```bash
pytest backend -q
```

Smoke API:

```bash
python backend/scripts/smoke_api.py
```

Frontend typecheck:

```bash
npm run typecheck
```

Frontend production build:

```bash
npm run build
```

## 11. Troubleshooting rapid

### Backend-ul nu porneste
- verifica PostgreSQL
- verifica `DATABASE_URL`
- verifica `JWT_SECRET`

### Login-ul `admin / 9999` nu merge
- ruleaza `python backend/scripts/reset_default_users.py`

### Aplicatia nu are date
- ruleaza `python backend/scripts/seed.py`
- sau importa manual fisierele din `data/`

### Istoricul sau dashboard-ul par goale
- verifica sa existe luni `completed` in `import_snapshots`
- ruleaza `python backend/scripts/rebuild_reporting.py`

### Vrei sa confirmi schema
- la startup, `ensure_schema_current()` verifica hash-ul din `schema_meta`
- daca schema este deja la zi, nu reaplica tot SQL-ul

### Incentive per-produs nu apar in dashboard
- verifica ca exista campanie importata: `SELECT * FROM incentive_campaigns;`
- luna din request trebuie sa coincida cu `month` din campanie (ex: `2026-04`)
- reimporta cu `import_incentive_campaign.py` daca e nevoie

### Promo/concurs iunie nu apar in selector
- verifica `SELECT import_month, status FROM import_snapshots ORDER BY import_month DESC LIMIT 5;`
- daca `2026-06` nu are import `completed`, comportamentul este corect: luna nu
  apare in selector pana la primul import
- verifica separat config-urile live: `data/hub_specials.json` si
  `data/contests.json`
