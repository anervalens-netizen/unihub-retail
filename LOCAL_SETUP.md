# UniHub Retail - setup local

## Principii

- dezvoltarea si testele nu folosesc niciodata baza de productie;
- autentificarea este exclusiv Authentik OIDC/JWKS RS256;
- nu exista utilizatori locali, parole implicite sau `JWT_SECRET` al
  aplicatiei;
- fisierele `.env`, tokenurile Authentik si cheile Google raman neversionate;
- importurile si seed-urile se ruleaza numai pe o baza locala dedicata.

## Cerinte

- Node.js 20+
- Python 3.12+ sau 3.14
- Docker pentru testele backend izolate
- PostgreSQL local numai daca rulezi aplicatia cu date persistente de
  dezvoltare

## Configurare

Copiaza `.env.example` in `.env` si foloseste credite locale proprii:

```env
DATABASE_URL=postgresql://unihub:change_me_local_only@127.0.0.1:5432/unihub
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
UNIHUB_ENV=development
```

Exemplu de baza locala:

```sql
CREATE ROLE unihub WITH LOGIN PASSWORD 'change_me_local_only';
CREATE DATABASE unihub OWNER unihub;
GRANT ALL PRIVILEGES ON DATABASE unihub TO unihub;
```

Nu reutiliza utilizatorul, parola, hostul sau baza de productie.

La startup, backend-ul:

1. valideaza configuratia;
2. initializeaza pool-ul asyncpg;
3. verifica hash-ul `backend/db/schema_v2.sql`;
4. aplica migrarile neexecutate;
5. porneste integrarile runtime.

## Dependinte

Frontend:

```bash
npm ci
```

Backend:

```bash
cd backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cd ..
```

## Pornire dezvoltare

```bash
npm run dev
npm run dev:backend
```

Endpointuri implicite:

- frontend: `http://127.0.0.1:3000`
- backend: `http://127.0.0.1:8000`
- health: `http://127.0.0.1:8000/health`

Pentru acces din LAN, adauga explicit origin-ul de dezvoltare in
`CORS_ORIGINS` si limiteaza accesul prin firewall.

## Authentik OIDC

Backend-ul BFF foloseste providerul Authentik `unihub-retail`; browserul nu
primeste tokenurile OIDC.

- callback-ul local trebuie permis explicit in provider;
- backend-ul valideaza issuer, expirare si semnatura RS256 prin JWKS, audienta
  API pentru access token si client ID-ul pentru ID token;
- grupul de variabile `SESSION_*`/`OIDC_CLIENT_*` din `.env.example` ramane gol
  in development; configureaza-l complet numai cand testezi login-ul BFF;
- grupul distributed rate-limit (`TRUSTED_PROXY_CIDRS`, header mode, Valkey,
  cheia HMAC si failure mode) ramane de asemenea complet gol in development;
- rolurile si scope-ul provin din grupurile Authentik;
- `offline_access` ramane activ conform politicii comune UniHub;
- nu adauga fallback cu username/parola.

## Teste backend izolate

Ruleaza:

```bash
backend/scripts/run_tests_isolated.sh
```

Scriptul:

1. porneste un PostgreSQL 18 temporar fara port public fix;
2. seteaza o baza `unihub_test`;
3. aplica schema si migrarile;
4. ruleaza testele;
5. elimina containerul prin `trap`, inclusiv la eroare.

Pentru argumente pytest suplimentare:

```bash
backend/scripts/run_tests_isolated.sh -v --tb=short
backend/scripts/run_tests_isolated.sh tests/test_target_calculator.py -q
```

Protectia din `backend/db/connection.py` refuza testele daca:

- lipseste opt-in-ul `UNIHUB_TEST_DATABASE=1`;
- hostul nu este loopback;
- portul este portul Retail de productie `5432`;
- numele bazei nu incepe cu `test_` si nu se termina in `_test`.

Nu rula direct testele de integrare cu `.env` de productie.

## Verificari frontend

Ruleaza secvential:

```bash
npm run typecheck
npm run test
npm run build
```

Typecheck-ul si build-ul nu se ruleaza in paralel, deoarece build-ul regenereaza
`dist/`.

## Smoke API

Health check-ul nu necesita token:

```bash
UNIHUB_API_URL=http://127.0.0.1:8000 \
python backend/scripts/smoke_api.py
```

Pentru endpointurile protejate, foloseste temporar un access token Authentik:

```bash
UNIHUB_API_URL=http://127.0.0.1:8000 \
UNIHUB_SMOKE_TOKEN='<token-temporar>' \
python backend/scripts/smoke_api.py
```

Scriptul este read-only. Tokenul nu se salveaza in fisiere sau documentatie.

## Date si importuri

Seed complet, numai pe baza locala dedicata:

```bash
cd backend
venv/bin/python scripts/seed.py
```

Rebuild reporting:

```bash
cd backend
venv/bin/python scripts/rebuild_reporting.py
venv/bin/python scripts/rebuild_reporting.py --month 2026-03
```

Fluxul standard de import:

1. creeaza `import_snapshot`;
2. inlocuieste snapshot-ul anterior al lunii;
3. insereaza tranzactiile;
4. reconstruieste tabelele `reporting_*`;
5. marcheaza snapshot-ul `completed`.

Dashboardurile folosesc stratul de reporting. Accesul direct la
`sales_transactions` ramane exceptie documentata.

## Configuratii operationale neversionate

- `data/hub_specials.json` - promotii active;
- `data/contests.json` - concursuri;
- `backend/config/google/service-account.json` - Google service account;
- `.env.worker` - configuratia Valkey pentru worker.

Aceste fisiere sunt incluse in backupul operational, nu in Git.

## Productie

- frontend-ul vizibil este `dist/`, deci modificarile UI necesita build;
- modificarile backend necesita restart `unihub-backend.service`;
- modificarile worker necesita restart `unihub-worker.service`;
- dupa deploy se verifica health local si public;
- joburile grele raman in worker, in afara timeouturilor HTTP/Cloudflare.

Comenzile si procedurile de productie sunt documentate in `AGENTS.md`,
`APP_ARCHITECTURE.md` si runbook-urile relevante.
