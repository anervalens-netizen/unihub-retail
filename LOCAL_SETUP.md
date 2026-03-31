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
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://192.168.0.23:3000
```

## 4. Instalare dependinte

Frontend:

```powershell
npm install
```

Backend:

```powershell
cd backend
python -m pip install -r requirements.txt
cd ..
```

## 5. Pornire dezvoltare

Frontend:

```powershell
npm run dev
```

Backend:

```powershell
npm run dev:backend
```

Aplicatia va fi disponibila pe:
- frontend: `http://127.0.0.1:3000`
- backend: `http://127.0.0.1:8000`
- health: `http://127.0.0.1:8000/health`

## 6. Acces de pe telefon, in aceeasi retea

Scripturile actuale pornesc pe `0.0.0.0`, deci frontendul si backendul sunt expuse si in LAN.

Exemplu:
- PC: `192.168.0.23`
- telefon: `http://192.168.0.23:3000`

Atentie:
- telefonul trebuie sa fie pe acelasi Wi-Fi
- firewall-ul Windows trebuie sa permita traficul local
- `CORS_ORIGINS` trebuie sa includa IP-ul folosit

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

```powershell
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

```powershell
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

```powershell
cd backend
python scripts/rebuild_reporting.py
cd ..
```

Sau pentru o luna anume:

```powershell
cd backend
python scripts/rebuild_reporting.py --month 2026-03
cd ..
```

### Sync focus products (optional — via coding agent)

Scriptul load_focus_products.py exista dar nu mai este accesibil din UI. Focus products se adauga prin coding agent direct in DB sau via seed.

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

```powershell
pytest backend -q
```

Smoke API:

```powershell
python backend/scripts/smoke_api.py
```

Frontend typecheck:

```powershell
npm run typecheck
```

Frontend production build:

```powershell
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
