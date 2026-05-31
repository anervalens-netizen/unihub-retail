# UniHub

UniHub este o aplicatie de operare comerciala pentru retail, construita pentru monitorizarea vanzarilor, a targetelor, a focus products, a promotiilor, a fiselor de vizita din magazine si a operatiunilor de management (echipa, CRM, tasks, HR, calculator target).

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

Reguli importante in Hub:
- comparatia perioade foloseste aceeasi fereastra calendaristica pentru luna curenta, luna trecuta si aceeasi luna anul trecut; daca luna curenta este partiala, cutoff-ul este ultima zi cu vanzari importate
- comparatia perioade este like-for-like: include in toate cele trei coloane doar magazinele cu vanzari Retail in luna analizata; la filtre RM/firma, istoricul urmareste aceleasi magazine chiar daca au fost realocate intre timp
- KPI-urile de vanzari, cantitate, bonuri si medii exclud categoria `Cartele`
- randul `Cartele` este informativ si este calculat separat din tranzactiile brute
- magazinele/locatiile de distributie cu nume `TR ...` sunt excluse din calculele Retail
- filtrul ASM nu mai este afisat in Hub; nivelul operational ramas este RM -> magazine -> agenti
- filtrele de magazin si agent suporta selectie multipla
- cand este selectat un magazin, filtrul de magazin are prioritate peste firma/RM, astfel istoricul ramane corect chiar daca magazinul a fost mutat intre RM-uri

### Focus
Focus este separat in 4 sub-sectiuni:
- **Incentive** — campanii incentive per-produs din DB (`incentive_campaigns`, `incentive_products`), cu target multipliers si excluderi specifice campaniilor active.
- **Promo** — promotii speciale definite in `data/hub_specials.json`; pentru campania iunie 2026 se masoara bonuri co-purchase, nu cantitate simpla.
- **Concurs** — leaderboard config-driven din `data/contests.json`, scoped server-side si independent de filtrele globale.
- **Focus** — indicator permanent de focus products si istoric focus.

Regula curenta pentru promotia iunie 2026 este implementata in
`backend/services/promo_copurchase.py`: bon calificat =
`(sale_date, site_code, agent, bon_nr)` cu cel putin un produs din lista promo
si cel putin doua unitati pozitive non-cartela pe acelasi bon. Unitatea redusa
este produsul din lista cu cel mai mic `unit_price`, maxim una per bon.

Atentie la metrici: `promo_qty` din summary/tabele Hub ramane agregatul simplu
din reporting, folosit pentru compatibilitate operationala. Tabul **Focus ->
Promo**, cardul Hub special si concursul folosesc campurile co-purchase
dedicate (`promo_qualifying_bons`, `promo_discounted_units`,
`promo_active_stores`, `promo_active_agents`).

### Fisa de vizita
Permite inregistrarea si urmarirea vizitelor in magazine:
- selectie magazin
- checklist operational
- analiza per agent
- poze
- status si completare

Geolocatia a fost eliminata complet din arhitectura aplicatiei.

### Management
Tab dedicat rolurilor `admin` si `management`, cu 5 sub-taburi:

- **Echipa (ASM)** — performanta ASM combinata din PostgreSQL (vanzari) + SQLite (vizite) + factor de forecast din CRM. Router: `/api/hr`
- **Magazine (CRM)** — scoruri magazine per luna, alerte automate, recalculare manuala. Alertele pot fi convertite direct in Tasks. Router: `/api/crm`
- **Tasks** — task-uri per agent/magazin cu deadline si status. Sursa poate fi manuala sau generata automat din alerte CRM (`source_meta` JSONB). Router: `/api/tasks`
- **HR** — cereri concediu (creare, aprobare/respingere), pontaj zilnic, istoric performanta ASM. Router: `/api/hr`
- **Calculator Target** — un document de target per luna, calcul automat, ajustare finala pe locatie, analiza pe manager si export Excel. Router: `/api/target-calculator`

**Serviciu comun:** CRM, HR si Calculator Target folosesc `services/forecast.py`
pentru calculul unitar al forecast-ului pe lunile partiale.

Tabele Management in `schema_v2.sql`: `tasks`, `leave_requests`, `attendance_records`, `store_scores`, `target_scenarios`, `target_scenario_rows`.

#### Calculator Target

Calculatorul este implementat nativ in aplicatie; fisierul Excel initial este doar
referinta de business, nu sursa de executie. Pentru fiecare luna tinta exista
un singur draft, care retine:

- luna pentru care se pregateste targetul;
- cohorta de magazine active, determinata din ultima luna cu vanzari disponibila inaintea lunii tinta;
- targetul total, pragul minim absolut si floor-ul procentual fata de luna anterioara;
- propunerea automata si targetul final editabil per locatie.

Formula `weighted_floor_forecast_v2` foloseste trei perioade de referinta derivate automat
din luna tinta: luna anterioara din anul trecut, aceeasi luna din anul trecut
si luna anterioara curenta. Pentru un target din iunie 2026, acestea sunt
mai 2025, iunie 2025 si mai 2026. Targetul este distribuit dupa ponderile istorice, apoi
redistribuit iterativ pana cand toate magazinele respecta floor-ul. Daca
bugetul este mai mic decat suma floor-urilor, documentul ramane draft si
afiseaza o avertizare.

Daca ultima referinta este o luna neinchisa, calculatorul foloseste forecast-ul
derivat din importul live (`realizat * zile_luna / ultima_zi_importata`), la
fel ca Hub si CRM. Draftul si exportul pastreaza separat realizatul importat
si forecast-ul efectiv folosit la calcul.

Procedura lunara recomandata este:

1. Spre finalul lunii curente, se alege luna tinta urmatoare si se introduce
   targetul total.
2. `Calculeaza propunerea` creeaza sau actualizeaza draftul unic al lunii.
   Cohorta se ia din ultima luna cu vanzari disponibila inaintea lunii tinta.
3. Managerii completeaza `Final manager`; valorile se salveaza automat si sunt
   vizibile pentru toti utilizatorii autentificati care deschid documentul.
4. Inainte de publicare, `Ramas de distribuit` trebuie sa fie `0`, iar toate
   locatiile trebuie sa aiba `Final manager` completat.
5. `Finalizeaza` scrie targetele oficiale in `store_targets` pentru luna tinta.
   Din acel moment Hub si CRM le folosesc cand apar importuri pentru luna
   respectiva.

Exemplu: pentru targetul din iulie 2026, calculul foloseste `2025-06`,
`2025-07` si `2026-06`. Daca in 27 iunie 2026 luna `2026-06` este inca
partiala, referinta `2026-06` este forecastata automat.
Recalcularea unei luni actualizeaza draftul acesteia si reseteaza ajustarile
manuale dupa confirmarea utilizatorului; nu sunt create versiuni alternative
in interfata.

`target_scenarios` si `target_scenario_rows` pastreaza documentul de lucru si
auditul calculului per luna. Randurile noi pornesc cu `Final manager` gol:
managerii trebuie sa completeze explicit valorile finale, iar finalizarea este
blocata pana cand toate locatiile au o valoare. Doar actiunea de finalizare
inlocuieste targetele oficiale ale lunii din `store_targets`, strict cu
magazinele din cohorta aprobata. Exportul Excel contine targetele finale,
rezumatul pe manager si parametrii documentului.
Crearea propunerii salveaza imediat un draft comun, iar modificarile de
`Final manager` sunt salvate automat per locatie si devin vizibile celorlalti
manageri care deschid sau reincarca acelasi draft.
Coloana `Final manager` este evidentiata ca zona de completat de manageri.
Calculul/recalcularea propunerii si butonul `Finalizeaza`, care publica
targetele oficiale, sunt afisate si acceptate de backend numai pentru
emailurile configurate in
`TARGET_CALCULATOR_FINALIZER_EMAILS` (implicit `aner.valens@gmail.com`).
Cardul superior cu parametrii de calcul este ascuns integral pentru ceilalti
manageri; acestia vad documentul calculat, completeaza `Final manager` si au
ca actiune operationala numai `Salveaza acum`.

Modelul curent de securitate este autentificare OIDC plus control explicit
doar pentru actiunile de finalizare din Calculator Target. Majoritatea
modulelor nu au inca RBAC pe grupuri sau scope per manager; conturile din
Authentik trebuie acordate doar utilizatorilor interni de incredere. Tabul
Salarii expune CNP si valori salariale utilizatorilor autentificati.
Tabelul per locatie are filtru multi-select pe locatie. Click pe numele unei
locatii deschide un drawer lateral cu 16 luni de vanzari versus target, KPI-uri
Retail (cantitate, bonuri, Bon2Acc, Focus/Acc, cartele, agenti activi) si
ponderea agentilor din luna cohortei. Graficul din drawer comuta intre
`Vanzari`, `Bon2Acc` si `Focus/Acc`. KPI-ul `Zile cu vanzari` este numarat din
datele distincte din `reporting_agent_day.sale_date`, nu din maximul pe agent,
pentru ca zilele active per agent pot subestima zilele reale ale magazinului.
Prin regula actuala, un magazin fara vanzari in luna cohortei nu intra in
targetul final; o viitoare exceptie pentru magazine planificate inainte de
deschidere trebuie modelata explicit in calculator.

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
- `tasks`, `leave_requests`, `attendance_records`, `store_scores`, `target_scenarios`, `target_scenario_rows` — date operationale Management tab

### 2. Stratul agregat de reporting
Acesta este stratul principal folosit de dashboard-uri:
- `reporting_agent_day`, `reporting_agent_month`
- `reporting_item_day`, `reporting_item_month`
- `reporting_focus_item_month`, `reporting_category_month`

Scopul lui este sa evite raportarea direct din `sales_transactions` pentru fiecare request.

Agregatele de reporting sunt construite pentru analiza Retail:
- exclud `is_cartela = true` din totaluri
- exclud locatiile de distributie `stores.locatie ILIKE 'TR %'`
- trebuie regenerate cu `backend/scripts/rebuild_reporting.py` dupa schimbari de reguli de raportare

Exceptie: cardurile care afiseaza explicit volumul de `Cartele` citesc separat din `sales_transactions`, fara sa contamineze totalurile Retail.

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

### Salarii

Salariile afisate in tabul **Agenti -> Salarii** sunt citite din tabela
`salary_records`.

Sursa operationala pentru salarii este setul de fisiere HR din:

```text
/opt/Mobiup/docs/comisioane/
```

Formatul curent este cate un fisier lunar per firma:
- `MOBIUP COMISIOANE AGENTI <LUNA>.xls`
- `COMISIOANE AGENTI Mobicell <luna>.xls`

Istoricul initial folosit pentru popularea bazei este arhivat in:

```text
/opt/Mobiup/docs/comisioane/salarii-istoric.zip
```

Regula de venit folosita in aplicatie este:

```text
salary_records.total_salary = TOTAL SALARIU + BONURI MASA
```

Coloane HR folosite:
- `CNP` -> `salary_records.cnp`
- `Nume Prenume` -> `salary_records.full_name`
- `Denumire locatie` -> `salary_records.locatie` si, cand maparea este sigura, `salary_records.site_code`
- `TOTAL SALARIU` + `BONURI MASA` -> `salary_records.total_salary`

Acoperire curenta in `salary_records`:
- 2025 integral
- 2026 ianuarie-aprilie

Observatii de calitate a datelor:
- unele randuri Mobiup nu au `site_code` cand locatia HR nu poate fi mapata sigur la un magazin Retail;
- randurile fara `site_code` intra in totaluri si in istoricul agentilor, dar nu intra corect in filtrele pe magazin/regional/ASM;
- cateva randuri istorice Mobicell au CNP gol in sursa initiala; acestea sunt pastrate pentru totalurile lunare, dar pot afecta numararea distincta pe agenti.

Cardul **Salarii vs Vanzari** foloseste endpointul `/salarii/summary`.
Pentru afisare, randurile sunt consolidate pe `locatie + company_name`, nu pe
`site_code`. Motivul este ca in istoricul HR pot exista contracte duble,
part-time sau coduri istorice diferite pentru aceeasi locatie. Consolidarea se
face doar in query-ul de citire; tabela `salary_records` ramane nemodificata.

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
- Script: `/opt/Mobiup/ops/scripts/backup.sh`
- Destinatie: `/opt/Mobiup/ops/backups/`
  - `postgres/` — dump PostgreSQL (`pg_dump -Fc`)
  - `visits/` — copie SQLite visits
- Retentie: 30 zile

Restore PostgreSQL:
```bash
pg_restore -d unihub /opt/Mobiup/ops/backups/postgres/<fisier.dump>
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

Reguli de filtrare pentru dashboard:
- frontend-ul trimite multi-select ca lista comma-separated (`site_code=A,B`, `agent=X,Y`)
- backend-ul traduce filtrele in SQL cu `ANY(string_to_array(...))`
- daca `site_code` este prezent, acesta ignora filtrele parinte `firma`, `regional`, `asm`
- aceeasi regula se aplica in summary, daily, history, period comparison, mixuri, promo/incentive si special cards
- selectorul global de luni listeaza doar `import_snapshots.status='completed'`; lunile configurate dar fara import de vanzari nu apar in UI pana la primul import finalizat

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
| `/opt/Mobiup/ops/scripts/backup.sh` | Backup zilnic PostgreSQL + SQLite |

## Documente suplimentare

- setup local: [LOCAL_SETUP.md](./LOCAL_SETUP.md)
- arhitectura: [APP_ARCHITECTURE.md](./APP_ARCHITECTURE.md)
- note Codex/agent: [CODEX.md](./CODEX.md)
- handover campanii iunie 2026: [docs/HANDOVER-campanii-iunie-2026.md](./docs/HANDOVER-campanii-iunie-2026.md)
