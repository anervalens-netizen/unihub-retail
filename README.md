# UniHub

**Versiune curenta:** `v2.0.0` — detalii in
[`docs/releases/v2.0.0.md`](docs/releases/v2.0.0.md).

UniHub este o aplicatie de operare comerciala pentru retail, construita pentru
monitorizarea vanzarilor, targetelor, produselor Focus, promotiilor, fiselor de
vizita si operatiunilor de management (manageri, calculator target, salarii si
P&L).

Starea curenta a planului de dezvoltare si drumul pana la urmatoarea versiune
sunt sintetizate in
[`docs/engineering/development-plan-status.md`](docs/engineering/development-plan-status.md).

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
- AI Forecast pentru monitorizarea forecasturilor salvate pe luna curenta si 12 luni

Reguli importante in Hub:
- comparatia perioade foloseste aceeasi fereastra calendaristica pentru luna curenta, luna trecuta si aceeasi luna anul trecut; daca luna curenta este partiala, cutoff-ul este ultima zi cu vanzari importate
- comparatia perioade este like-for-like: include in toate cele trei coloane doar magazinele cu vanzari Retail in luna analizata; la filtre RM/firma, istoricul urmareste aceleasi magazine chiar daca au fost realocate intre timp
- KPI-urile de vanzari, cantitate, bonuri si medii exclud categoria `Cartele`;
  cantitatea Retail este neta (vanzari minus retururi), iar `Medie produs`
  inseamna `vanzari nete / cantitate neta` pe acelasi scope
- retururile raman monitorizate separat prin numarul de bonuri de retur, dar
  nu umfla volumele, Focus/Acc sau distributiile RM/magazin/agent
- randul `Cartele` este informativ si este calculat separat din tranzactiile brute
- magazinele/locatiile de distributie cu nume `TR ...` sunt excluse din calculele Retail
- in Hub exista un singur layer operational de management; rapoartele pastreaza
  coloanele `Regional` si `ASM`, dar pentru magazinele active curente acestea
  trebuie sa reprezinte acelasi manager
- filtrele de magazin si agent suporta selectie multipla
- cand este selectat un magazin, filtrul de magazin are prioritate peste firma/RM, astfel istoricul ramane corect chiar daca magazinul a fost mutat intre RM-uri
- sectiunea Istoric foloseste magazinele active alocate managerului curent,
  nu managerul istoric din luna respectiva; magazinele inchise sunt ascunse
  implicit si pot fi incluse din checkbox-ul `Include magazine inchise`
- cardul `Evolutie lunara` in modul standard afiseaza ultimele 13 luni
  finalizate plus luna curenta forecastata, cand luna curenta este partiala
- in detaliul de performanta pe agent, scorul foloseste targetul efectiv al
  agentului, iar forecastul lunii curente foloseste media zilnica a agentului
  inmultita cu 15 zile lucrate estimate
- in acelasi detaliu, Bon2Acc este notat pe praguri: sub 20% critic scazut,
  20-29% scazut, 30-35% ok, peste 35% foarte bine; Focus este scazut sub 6%, ok
  intre 6-8% si bun peste 8%
- subsectiunea `AI Forecast` afiseaza forecasturi salvate, nu ruleaza modelul
  in request; are comutatoare pentru `Luna curenta / 12 luni` si
  `Valoare / Bucati`
- modul `Luna curenta` compara la nivel de retea, RM si magazin forecastul
  cumulat la zi cu realizatul importat; modul `12 luni` afiseaza prognoza
  lunara pe urmatoarele 12 luni

Forecasturile AI sunt salvate in tabelele `ai_forecast_runs`,
`ai_forecast_store_month` si `ai_forecast_store_day`. Importul operational se
face cu `backend/scripts/import_ai_forecast.py`, dupa rularea externa TimesFM
XReg. Fiecare rulare este marcata prin `metric` (`sales_value` sau `units`) si
`horizon` (`current_month` sau `rolling_12m`). Curba zilnica se genereaza doar
pentru `current_month` si foloseste distributia pe zile din aceeasi luna a
anului precedent pentru acelasi magazin, aliniata pe calendarul lunii
forecastate prin ordinalul zilei din saptamana.

Backtestul comparativ se face inainte de schimbari de model, ca sa compare
baseline-uri simple cu TimesFM/XReg pe aceeasi fereastra istorica:

```bash
backend/venv/bin/python -u backend/scripts/run_ai_forecast_backtest.py \
  --start-month 2025-07 \
  --end-month 2026-06 \
  --history-start-month 2018-01 \
  --metric sales_value \
  --models seasonal_naive,seasonal_moving_average,seasonal_last3
```

Cand serviciul TimesFM este disponibil, acelasi script poate rula si modelele
remote:

```bash
TIMESFM_API_KEY=... backend/venv/bin/python -u backend/scripts/run_ai_forecast_backtest.py \
  --start-month 2025-07 \
  --end-month 2026-06 \
  --history-start-month 2018-01 \
  --metric sales_value \
  --models all
```

Outputurile comparative sunt scrise in `backend/outputs/ai_forecast/` ca
`backtest_comparison_*`, cu randuri per magazin/luna/model, sumar lunar si
metrici pe retea/RM/ASM/magazin.

Backtestul XReg operational si rularea batch lunara se fac cu:

```bash
TIMESFM_API_KEY=... backend/venv/bin/python -u backend/scripts/run_ai_forecast_xreg.py \
  --start-month 2025-07 \
  --end-month 2026-06 \
  --history-start-month 2018-01 \
  --metric sales_value
```

Scriptul foloseste XReg pentru magazinele cu cel putin 33 luni de context si
fallback sezonier pentru magazinele prea noi. Outputurile CSV/JSON sunt scrise
in `backend/outputs/ai_forecast/`; CSV-ul operational se importa apoi cu
`backend/scripts/import_ai_forecast.py`. Magazinele inchise in luna sursa pot
fi excluse cu `--exclude-site-code`; implicit sunt excluse inchiderile din
iunie 2026: `CRFVUL` si `CRFARENA`.

Decizie operationala actualizata 2026-07-09: pentru iulie 2026 aplicatia
foloseste profilul `xreg_timesfm v2`, importat ca
`monthly_xreg_v2_excl_closed` pentru valoare si
`monthly_xreg_units_v2_excl_closed` pentru bucati. Forecastul curent este
3.943.570 RON si 42.724 bucati pe 74 magazine active. Profilul `v1`
(`monthly_xreg_standard_v2_excl_closed`, 3.884.172 RON si 42.114 bucati) ramane
benchmark stabil pentru analiza de final de iulie. Pe backtestul
2025-07..2026-06, `v1` a ramas mai stabil decat `v2` pe valoare, iar `v3` a
fost practic identic cu `v1`.

Pentru forecast operational pe urmatoarele 12 luni se ruleaza multi-step din
ultima luna istorica sigura si se importa doar lunile care trebuie afisate:

```bash
TIMESFM_API_KEY=... backend/venv/bin/python -u backend/scripts/run_ai_forecast_xreg.py \
  --start-month 2026-07 \
  --end-month 2027-07 \
  --source-month 2026-06 \
  --operational \
  --history-start-month 2018-01 \
  --metric units

backend/venv/bin/python backend/scripts/import_ai_forecast.py \
  --csv backend/outputs/ai_forecast/xreg_backtest_store_units_2026-07_to_2027-07.csv \
  --start-month 2026-08 \
  --end-month 2027-07 \
  --source-month 2026-06 \
  --anchor-month 2026-07 \
  --metric units \
  --horizon rolling_12m \
  --variant rolling_12m_xreg_units_v1_excl_closed \
  --replace
```

### Focus
Focus este separat in 4 sub-sectiuni:
- **Incentive** — campanii incentive per-produs din DB (`incentive_campaigns`, `incentive_products`), cu target multipliers si excluderi specifice campaniilor active.
- **Promo** — promotii speciale definite in `data/hub_specials.json`; tabul poate comuta intre mai multe promotii active prin butoane separate. Pentru campaniile iunie 2026 se masoara bonuri co-purchase, nu cantitate simpla.
- **Concurs** — leaderboard config-driven din `data/contests.json`, scoped server-side si independent de filtrele globale; raspunsul include magazinul/firma principala a agentului pentru afisarea in FieldOps.
- **Focus** — indicator permanent de focus products si istoric focus.

Regulile pentru promotiile iunie 2026 sunt implementate in
`backend/services/promo_copurchase.py`. Promotia actuala foloseste regula
existenta: bon calificat =
`(sale_date, site_code, agent, bon_nr)` cu cel putin un produs din lista promo
si cel putin doua unitati pozitive non-cartela pe acelasi bon. Unitatea redusa
este produsul din lista cu cel mai mic `unit_price`, maxim una per bon.

In acelasi helper exista si regulile pentru campaniile adaugate pe 10.06.2026:
- folie ecran + folie camera pentru acelasi model de telefon, cu modelele
  extrase din anexele Excel;
- capac Cellara + husa universala Cellara, cu husa cea mai ieftina de pe bon
  considerata unitate redusa.

Atentie la metrici: `promo_qty` din summary/tabele Hub ramane agregatul simplu
din reporting, folosit pentru compatibilitate operationala. Tabul **Focus ->
Promo**, cardul Hub special si concursul folosesc campurile co-purchase
dedicate (`promo_qualifying_bons`, `promo_discounted_units`,
`promo_active_stores`, `promo_active_agents`).

Pentru incentive, unitatile reduse din toate promotiile active ale lunii sunt
excluse din cantitate si valoare, indiferent ce promotie este selectata in
tabul Promo.
In raspunsul Focus, `top_stores.qty` reprezinta unitati incentive nete pentru
cardul **Top Magazine — Incentive**, iar `top_stores.promo_bons` reprezinta
bonuri co-purchase pentru cardul **Top Magazine — Promo**.

### Fisa de vizita
Permite inregistrarea si urmarirea vizitelor in magazine:
- selectie magazin
- checklist operational
- analiza per agent
- poze
- status si completare

Geolocatia a fost eliminata complet din arhitectura aplicatiei.

### Agenti
Tabul principal Agenti include `Prezentare Generala`, `Grile` si
`Analiza agenti`. Prezentarea generala are navigare interna persistenta intre
`Echipa`, `Acoperire magazine` si `Lista agentilor`, fara a dubla datele.

- **Grile** — verificarea grilelor salariale permanente, antet desktop sticky,
  grupuri manager/Team Leader memorate local, statusul pe magazine
  si operatiunile lunare controlate. Operatiunile privilegiate raman autorizate
  separat in backend.

- **Analiza agenti** — evaluare agenti pe agentii activi curent, cu alocarea
  curenta de firma/magazin/manager. Scorul 0-100 (`/api/agents/evaluation-v2`)
  este modul implicit; evaluarea veche (`/api/agents/evaluation`) ramane numai
  ca vedere de comparatie.

Pe mobil, filtrele Analizei agentilor sunt intr-un drawer, rezultatele sunt
carduri responsive, iar comparatia veche ramane un mod secundar. Hub Istoric
foloseste `Sumar / Trend / Detalii`, Grile foloseste un selector compact de
stare, iar Salarii afiseaza carduri pentru magazine si agenti in locul
tabelelor late.

### Management
Tab dedicat rolurilor `admin` si `management`, cu sub-taburi operationale:
subtaburile sunt afisate in bara interna a ecranului, la fel ca in Agenti si
Focus; sidebar-ul contine numai intrarea principala Management.

- **Manageri** — overview operational pe structura Retail curenta: numar de
  magazine si agenti, fluxul agentilor fata de luna precedenta, magazine fara
  agent raportat si sanatatea operationala din Vizite. Cardurile expandate
  prezinta acoperirea pe magazine, fara evaluarea de vanzari duplicata din Hub.
  Pentru Mihai Condorateanu ramane disponibila grila salariala, protejata de
  acelasi RBAC ca Salarii. Router: `/api/hr`
- **Calculator Target** — un document de target per luna, ghidat vizual prin
  Configurare, Verificare, Ajustari manageri si Finalizare; revizia si starea
  salvarii raman vizibile in timpul editarii. Router: `/api/target-calculator`
- **Salarii** — vederi separate `Overview`, `Magazine` si `Agenti`, evolutie,
  raport salarii versus vanzari si istoric pe agent. Regula mediei eligibile
  ramane permanent vizibila, iar accesul este limitat server-side.
- **P&L** — sumar financiar pe magazin, evolutii lunare si anuale si structura
  de cost, vizibil numai utilizatorilor cu capabilitatea P&L verificata de
  backend. Intervalul initial este anul calendaristic curent (year-to-date),
  iar regiunea/RM, compania si magazinul filtreaza autoritativ toate cardurile
  si graficele.
  Cand este ales un magazin, identitatea lui canonica domina compania in
  istoricul P&L, astfel incat mutarile intre entitati nu rup evolutia.
  Pentru fiecare firma-luna, existenta unui import Finance face ca raportarea
  sa ignore toate estimarile acelei firme-luni si sa insumeze integral
  centrele de profit `actual`, inclusiv aliasurile aceluiasi magazin.

Endpointurile backend pentru Tasks, cereri de concediu si alerte CRM raman
compatibile cu datele istorice si integrarile, dar nu au subtab-uri in
navigatia V2. Componentele frontend legacy inaccesibile au fost eliminate ca
sa nu existe o a doua interfata neintretinuta.

Evaluarea din **Agenti -> Analiza agenti** foloseste 6 segmente, fiecare cu 0-3 puncte:
Target valoare, Medie zilnica, Valoare reper, % Bonuri, Focus si Folii Premium.
Pragurile sunt:

- Target valoare: 3p >=100%, 2p 90-99%, 1p 80-89%, 0p <80%.
- Medie zilnica: 3p peste media colegilor din locatie; 0p sub medie sau fara comparatie.
- Valoare reper: 3p >=100 lei, 2p 95-99 lei, 1p 90-94 lei, 0p <90 lei.
- % Bonuri: 3p >=35%, 2p 30-34%, 1p 25-29%, 0p <25%.
- Focus: 3p >=8%, 2p 7-7,9%, 1p 6-6,9%, 0p <6%.
- Folii Premium: 3p >=50%, 2p 40-49%, 1p 30-39%, 0p <30%.

Evaluarea noua din acelasi subtab este o subsectiune separata, nu o extensie a
scorului vechi. Foloseste scor 0-100 strict pentru evaluare, fara componenta de
bonus, si calculeaza separat: target, productivitate zilnica, Bon2Acc, Focus,
Folii Premium, valoare reper si trend. Pentru luni partiale marcheaza scorul ca
provizoriu prin flaguri de incredere si reduce greutatea targetului. Agentii cu
volum insuficient de zile/bonuri raman vizibili, dar sunt marcati `insuficient`
si nu trebuie folositi ca reper de leaderboard. Productivitatea compara mai intai
cu colegii din magazin, apoi cu istoricul locatiei si abia la final cu media
managerului. Targetul se calculeaza pe zile lucrate: `target magazin / zile cu vanzare
in locatie * zile cu vanzare agent`. Punctajul de target se calculeaza lunar si
apoi se mediaza ponderat; daca selectia include o luna partiala, luna partiala
intra in target cu ponderea zile disponibile / zile luna, nu schimba toata
selectia pe regula de luna partiala. Ponderile standard sunt Target 25p,
Productivitate 20p, Bon2Acc 15p, Focus 15p, Folii Premium 10p si Valoare reper
15p; doar cand este selectata o singura luna partiala se folosesc ponderile
provizorii Target 10p, Productivitate 25p, Bon2Acc 20p, Focus 20p, Folii
Premium 10p si Valoare reper 15p.

Folii Premium sunt calculate pe aceeasi baza ca in Focus: produse din categoria
`Folii Sticla`, raportate la totalul foliilor eligibile pentru aceleasi modele
tinta din `v_premium_glass_item_models`. Pentru foliile de ecran, premium
inseamna nume produs cu `SAPPHIRE`, `CERAMIC` sau `CORNING`. Pentru foliile de
camera, premium vine din lista operationala `data/folii premium camera.xlsx`,
coloana `Premium` (`Da`/`nu`), nu din regex. Samsung S26 Plus este eligibil
doar pentru foliile de camera, nu pentru foliile de ecran. Indicatorul este materializat in
tabela indexata `premium_glass_item_models`; view-urile
`v_premium_glass_item_models` si `v_premium_glass_products` sunt doar
compatibilitate de citire. Nu reintroduce calculul prin regex direct in
request-uri, pentru ca produce timeout-uri pe filtre combinate manager+magazin.

**Serviciu comun:** CRM, HR si Calculator Target folosesc `services/forecast.py`
pentru calculul unitar al forecast-ului pe lunile partiale.

Tabele Management in `schema_v2.sql`: `tasks`, `leave_requests`, `attendance_records`, `store_scores`, `target_scenarios`, `target_scenario_rows`.

#### Calculator Target

Calculatorul este implementat nativ in aplicatie; fisierul Excel initial este doar
referinta de business, nu sursa de executie. Pentru fiecare luna tinta exista
un singur draft, care retine:

- luna pentru care se pregateste targetul;
- cohorta de magazine active, determinata din ultima luna cu vanzari disponibila inaintea lunii tinta si filtrata de excluderile active pentru Calculator Target;
- targetul total, pragul minim absolut si floor-ul procentual fata de forecastul lunii curente;
- propunerea automata si targetul final editabil per locatie.

Formula `seasonal_blended_multiyear_v1` porneste de la forecastul lunii
curente si aplica sezonalitatea reala dintre luna anterioara si luna tinta.
Finalizatorul poate comuta in cardul de calcul intre:

- `Anul trecut`: foloseste doar perechea `M-13 -> M-12`;
- `Multi-year`: foloseste pana la trei ani, cu ponderi mai mari pentru anul cel
  mai recent. Anii fara date suficiente sunt sariti automat.

Factorul sezonier folosit pentru un magazin combina sezonalitatea magazinului,
a managerului curent si a retelei. Pentru date stabile ponderile sunt
`50% magazin / 30% manager / 20% retea`; pentru date slabe sau magazin nou,
formula muta greutatea spre manager si retea. Targetul total ramane top-down:
bugetul este impartit proportional cu estimarile brute, apoi redistribuit
iterativ pana cand respecta pragul minim, floor-ul fata de forecastul lunii
curente si cap-ul configurat. Daca bugetul este mai mic decat suma floor-urilor
sau mai mare decat suma cap-urilor, documentul ramane draft si afiseaza o
avertizare.

Cardul de manageri arata, pe langa propunere si `Final manager`, doua repere
rapide: cresterea propunerii fata de forecastul lunii curente si cresterea
observata anul trecut intre luna baza si luna target (de exemplu `Iul 2025 vs
Iun 2025` pentru targetul de iulie 2026).

Daca ultima referinta este o luna neinchisa, calculatorul foloseste forecast-ul
derivat din importul live (`realizat * zile_luna / ultima_zi_importata`), la
fel ca Hub si CRM. Draftul si exportul pastreaza separat realizatul importat
si forecast-ul efectiv folosit la calcul.

Procedura lunara recomandata este:

1. Spre finalul lunii curente, se alege luna tinta urmatoare si se introduce
   targetul total.
2. `Calculeaza propunerea` creeaza sau actualizeaza draftul unic al lunii.
   Cohorta se ia din ultima luna cu vanzari disponibila inaintea lunii tinta,
   excluzand magazinele cu intrari in `target_calculator_store_exclusions`
   active pentru luna tinta.
3. Managerii completeaza `Final manager`; valorile se salveaza automat si sunt
   vizibile pentru toti utilizatorii autentificati care deschid documentul.
4. Inainte de publicare, `Ramas de distribuit` trebuie sa fie `0`, iar toate
   locatiile trebuie sa aiba `Final manager` completat.
5. `Finalizeaza` scrie targetele oficiale in `store_targets` pentru luna tinta.
   Din acel moment Hub si CRM le folosesc cand apar importuri pentru luna
   respectiva.

Exemplu: pentru targetul din iulie 2026, modul `Anul trecut` foloseste
`2025-06 -> 2025-07` si forecastul `2026-06`. Modul `Multi-year` adauga, daca
exista date, perechile `2024-06 -> 2024-07` si `2023-06 -> 2023-07`. Daca in
27 iunie 2026 luna `2026-06` este inca partiala, referinta curenta este
forecastata automat.
Recalcularea unei luni actualizeaza draftul acesteia si reseteaza ajustarile
manuale dupa confirmarea utilizatorului; nu sunt create versiuni alternative
in interfata.

`target_scenarios` si `target_scenario_rows` pastreaza documentul de lucru si
auditul calculului per luna. Randurile noi pornesc cu `Final manager` gol:
managerii trebuie sa completeze explicit valorile finale, iar finalizarea este
blocata pana cand toate locatiile au o valoare. Doar actiunea de finalizare
inlocuieste targetele oficiale ale lunii din `store_targets`, strict cu
magazinele din cohorta aprobata. Exportul Excel contine targetele finale,
rezumatul pe manager cu indicatorii de crestere, parametrii documentului si breakdown-ul de calcul
sezonier per locatie.
Crearea propunerii salveaza imediat un draft comun, iar modificarile de
`Final manager` sunt salvate automat per locatie si devin vizibile celorlalti
manageri care deschid sau reincarca acelasi draft.
Coloana `Final manager` este evidentiata ca zona de completat de manageri.
Calculul/recalcularea propunerii si butonul `Finalizeaza`, care publica
targetele oficiale, sunt afisate si acceptate de backend numai pentru grupurile
OIDC dedicate configurate pentru capabilitatea Calculator Target.
Cardul superior cu parametrii de calcul este ascuns integral pentru ceilalti
manageri; acestia vad documentul calculat, completeaza `Final manager` si au
ca actiune operationala numai `Salveaza acum`.

Modelul curent de securitate este Authentik OIDC cu BFF, sesiune criptata in
Valkey, cookie HttpOnly si RBAC backend centralizat. Browserul nu stocheaza si
nu transmite tokenuri OIDC; requesturile de scriere necesita si tokenul CSRF
al sesiunii.
Management, salariile, importurile si actiunile privilegiate au politici
server-side dedicate; autorizarea privilegiata nu foloseste adrese email.
Contractele publice Salarii expun numai `person_id`, niciodata CNP.
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

Aplicatia are patru straturi de date:

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
- agrega cantitatile net, inclusiv retururile negative; bonurile exclusiv de
  retur nu intra in `receipt_count`, iar produsele Focus returnate se scad din
  numaratorul si denominatorul Focus/Acc
- trebuie regenerate cu `backend/scripts/rebuild_reporting.py` dupa schimbari de reguli de raportare

Exceptie: cardurile care afiseaza explicit volumul de `Cartele` citesc separat din `sales_transactions`, fara sa contamineze totalurile Retail.

### 3. Stratul semantic de organizatie

Structura manageriala curenta este separata de istoricul importat.

- `store_org_assignments` tine asignarile magazinelor la RM/ASM pe intervale lunare.
- Structura oficiala curenta incepe in `2026-05`.
- Din `2026-05`, RM/regional si ASM sunt aceiasi 6 manageri activi.
- `site_code` ramane cheia unica de magazin; nu se deduplica magazine dupa coduri sau nume asemanatoare.

Pentru analize comerciale normale, foloseste view-urile `current_org`:
- `v_retail_agent_month_current_org`
- `v_retail_store_month_current_org`
- `v_retail_item_month_current_org`
- `v_retail_targets_current_org`

Pentru analize "cum era atunci", foloseste explicit view-urile `historical_org`:
- `v_retail_agent_month_historical_org`
- `v_retail_store_month_historical_org`
- `v_retail_item_month_historical_org`

Contractul complet pentru agenti este in `docs/retail-org-analysis.md`.

### 4. Stratul de date istorice
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

Salariile afisate in tabul **Management -> Salarii** sunt citite din tabela
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
- 2026 ianuarie-mai

Observatii de calitate a datelor:
- unele randuri Mobiup nu au `site_code` cand locatia HR nu poate fi mapata sigur la un magazin Retail;
- randurile fara `site_code` intra in totaluri si in istoricul agentilor, dar nu intra corect in filtrele pe magazin/regional/ASM;
- cateva randuri istorice Mobicell au CNP gol in sursa initiala; read model-ul foloseste numele normalizat ca fallback si elimina duplicatele complet identice.

Filtrele de analiza salvate pentru zona Agenti sunt reutilizate de
**Management -> Salarii** pe toate cardurile. Filtrul de magazin este transmis
ca `site_code` catre overview, evolutie, summary, trend si lista de agenti.

API-ul public si repository-urile runtime folosesc identificatorul opac
`person_id`. CNP-ul retinut este izolat pentru import si matching intern: nu
este returnat browserului, folosit in URL-uri sau expus in contractele publice.
Matcherul offline poate scrie un link confirmat numai impreuna cu `person_id`;
potrivirile manuale fara identitate salariala unica raman `review` pana cand
exista o inregistrare HR rezolvabila.
Media salariala din overview, tabelul pe locatii si trendul lunar este calculata
unitar pe valorile agent-luna de cel putin `2.000 RON`. Identitatea principala
este `person_id`. Daca acelasi agent are mai multe randuri de plata in aceeasi luna,
valorile se insumeaza inainte de aplicarea pragului. Valorile sub prag sunt
excluse numai din medii; totalurile, numarul de agenti si istoricul raman
complete.

Cardul **Salarii vs Vanzari** foloseste endpointul `/salarii/summary`.
Pentru afisare, randurile sunt consolidate pe `locatie + company_name`, nu pe
`site_code`. Motivul este ca in istoricul HR pot exista contracte duble,
part-time sau coduri istorice diferite pentru aceeasi locatie. Consolidarea se
face doar in query-ul de citire; tabela `salary_records` ramane nemodificata.

Codurile de agent din raportarea Retail sunt legate de numele salariale prin
`agent_salary_links` (`agent_code + site_code -> salary_full_name`). Maparile
confirmate manual si cele automate sunt persistente; cazurile neclare se
marcheaza `unknown`, ca sa poata fi completate dupa importuri viitoare. Drawerul
din **Hub -> Luna in curs -> Overview -> Agenti** citeste aceasta mapare si
afiseaza sumarul salarial doar pentru utilizatorii cu acces la Salarii.

Importul lunar se ruleaza cu scriptul dedicat, intai dry-run si apoi `--apply`:

```bash
backend/venv/bin/python backend/scripts/import_salary_records.py \
  --year 2026 \
  --month 5 \
  --mobiup-file "/opt/Mobiup/docs/comisioane/MOBI COMISIOANE AGENTI MAI.xls" \
  --mobicell-file "/opt/Mobiup/docs/comisioane/COMISIOANE AGENTI Mobicell mai.xls"

backend/venv/bin/python backend/scripts/import_salary_records.py \
  --year 2026 \
  --month 5 \
  --mobiup-file "/opt/Mobiup/docs/comisioane/MOBI COMISIOANE AGENTI MAI.xls" \
  --mobicell-file "/opt/Mobiup/docs/comisioane/COMISIOANE AGENTI Mobicell mai.xls" \
  --apply
```

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

## View-uri de compatibilitate pentru FieldOps

Aplicatia Platforma-Mobiup a fost dezafectata. View-urile cu prefix
`v_platforma_*` raman active deoarece FieldOps le foloseste ca interfata de
raportare peste baza Retail. Importul se face o singura data, in Retail.

VIEW-uri disponibile in `schema_v2.sql`:
- `v_platforma_dashboard` — agregat lunar per agent
- `v_platforma_import_meta` — metadata per luna (is_partial, period_end)
- `v_platforma_raw_sales` — tranzactii brute cu campuri aliasate pentru compatibilitate
- `v_platforma_store_targets` — targete magazine cu detalii firma/asm/regional

**Vizite**: Retail este sursa de adevar pentru fisierul SQLite partajat:
`/opt/Mobiup/unihub-retail/data/visits/visits.db`, configurat prin
`VISITS_DB_PATH`.

## Backup

Backup-urile automate ruleaza prin `mobiup-backup.timer`, zilnic in jurul
orei 03:00:
- Script: `/opt/Mobiup/ops/scripts/backup.sh`
- Destinatie primara: `/storage/backups/db/`
- Copie locala SSD: `/opt/Mobiup/ops/backups/`
- Copie NAS: `/storage/backups/server-68/` pe NAS, prin rsync
- Retentie: 30 zile

Restore PostgreSQL:
```bash
pg_restore -d unihub /storage/backups/db/postgres/<fisier.dump>
```

## Gestionarea schemei DB

Schema principala este in:
- `backend/db/schema_v2.sql`

`schema_v2.sql` este baseline-ul inghetat pentru instalari noi. Orice schimbare
ulterioara foloseste un fisier SQL nou si imutabil plus checksum in
`backend/db/migrations/manifest.json`.

Inaintea unui restart cu schimbari DB:

```bash
sudo systemctl start unihub-retail-migrate.service
sudo systemctl status unihub-retail-migrate.service --no-pager
```

Runnerul foloseste advisory lock PostgreSQL, tranzactii per migration si
checksum-uri persistente, preferand credentialul owner din
`MIGRATION_DATABASE_URL`. Backend-ul web nu executa DDL/DML de schema; la
startup face numai verificarea read-only si refuza sa porneasca daca exista
drift sau migrations neaplicate. La un DB nou, baseline-ul DDL este urmat de
seed-urile de date desemnate explicit de runner.

Asta inseamna ca doua instante web nu pot concura pentru schema, fisierele
istorice modificate sunt detectate, iar release-ul DB este separat de runtime.

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
- aceeasi regula se aplica in summary, daily, history, period comparison, mixuri, focus/campaigns history, promo/incentive si special cards
- selectorul global de luni listeaza doar `import_snapshots.status='completed'`; lunile configurate dar fara import de vanzari nu apar in UI pana la primul import finalizat

## Autentificare

Authentik OIDC este singura sursa de identitate. Backend-ul termina fluxul
Authorization Code + PKCE, valideaza tokenurile
RS256 prin JWKS; nu exista utilizatori locali, parole implicite sau secret JWT
HMAC al aplicatiei.

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
backend/scripts/run_tests_isolated.sh
python backend/scripts/smoke_api.py
npm run typecheck
npm run typecheck:strict
npm run lint
npm run test
npm audit --omit=dev --audit-level=high
npm run build
npm run test:e2e
```

`run_tests_isolated.sh` creeaza un PostgreSQL 18 temporar si refuza orice
conectare a testelor la baza Retail de productie.
Suita Playwright porneste singura preview-ul Vite si include smoke-uri de
accesibilitate WCAG A/AA pentru Hub si Management. CI ruleaza aceleasi gate-uri
frontend, inclusiv auditul dependentelor runtime la severitate `high`.

Probe runtime:

- `/livez` confirma doar procesul;
- `/readyz` confirma PostgreSQL si sesiunea BFF din Valkey;
- `/health` ramane alias compatibil pentru `/readyz`.

Contractul, SLO-urile si alertele sunt documentate in
[docs/operations/retail-slo-readiness.md](./docs/operations/retail-slo-readiness.md).

## Stare release V2

Versiunea V2 este acceptata operational din 13 iulie 2026. Acceptarea finala
include CI backend/frontend pe merge ref, teste PostgreSQL izolate, pragurile de
coverage critice, typecheck strict, lint, build, Playwright/WCAG, rollout
controlat backend/worker si probe locale/publice de liveness/readiness. Starea
executiva si backlogul neblocant sunt mentinute in
[development-plan-status.md](./docs/engineering/development-plan-status.md),
iar probele de performanta in
[performance-baseline-v2.md](./docs/engineering/performance-baseline-v2.md).

## Scripturi utile

| Script | Utilizare |
|--------|-----------|
| `backend/scripts/import_incentive_campaign.py` | Import campanie incentive per-produs din Excel in DB |
| `backend/scripts/import_historical.py` | Import date istorice 2023 Q4 + 2024 (tranzactii) |
| `backend/scripts/import_annual_summary.py` | Import agregate anuale 2022/2023 din `vanzari 2022 si 2023.xlsx` |
| `backend/scripts/seed.py` | Seed complet din `data/` |
| `backend/scripts/rebuild_reporting.py` | Rebuild agregate reporting |
| `backend/scripts/run_tests_isolated.sh` | Teste backend pe PostgreSQL temporar |
| `backend/scripts/smoke_api.py` | Smoke test API read-only; token Authentik optional |
| `/opt/Mobiup/ops/scripts/backup.sh` | Backup zilnic PostgreSQL + SQLite |

## Documente suplimentare

- setup local: [LOCAL_SETUP.md](./LOCAL_SETUP.md)
- arhitectura: [APP_ARCHITECTURE.md](./APP_ARCHITECTURE.md)
- reguli Codex: [AGENTS.md](./AGENTS.md)
- plan activ refactoring: [docs/refactoring-plan-current.md](./docs/refactoring-plan-current.md)
- runbook campanii promo, incentive si concursuri: [docs/RUNBOOK-campanii-promo-incentive-concursuri.md](./docs/RUNBOOK-campanii-promo-incentive-concursuri.md)
- arhiva de planuri si rapoarte inchise: [docs/archive/README.md](./docs/archive/README.md)
