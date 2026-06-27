# Design: Calculator Target

**Data:** 2026-05-27
**Status:** Implementat
**Zona:** `Management -> Calculator Target`

## Scop

Calculatorul transforma fluxul de planificare din Excel intr-un modul nativ
UniHub: propunere automata, ajustare manuala pe locatie, grafice pe manager,
drafturi auditabile, finalizare in targetele oficiale si export `.xlsx`.

Excel-ul furnizat initial este referinta functionala, nu o dependinta runtime.

## Interfata

- filtrarea pe manager este expusa prin butoane rapide pentru toti regionalii,
  plus optiunea `Toti managerii`;
- tabelul per locatie afiseaza lunile de referinta ale metodei selectate, atat
  targetul istoric, cat si realizatul si procentul realizat;
- coloanele perechilor sezoniere sunt evidentiate vizual, iar tabelul arata
  factorul folosit, factorul last-year, factorul multi-year si flag-urile
  principale pentru fiecare locatie;
- tabelul operational afiseaza valoarea `Calculat`, fara a expune separat
  coloane de floor/cap; limitele raman aplicate in algoritm si pastrate in export;
- interfata nu expune un selector de scenarii: exista un singur draft pentru
  fiecare luna tinta, iar recalcularea actualizeaza acelasi draft;
- rezumatul `Calculator si Final manager` este tabelar: finalul sub propunere
  este rosu, finalul egal sau pana la `+5%` este verde, iar finalul peste
  `+5%` este galben. Cardul include si cresterea propunerii fata de forecastul
  lunii curente, plus cresterea observata anul trecut intre luna baza si luna
  target;
- utilizatorul editeaza separat `Final manager`, fara a suprascrie propunerea;
  coloana si cardul ei sunt evidentiate ca zona care trebuie completata sau
  confirmata de manager. In drafturile noi, campul porneste gol si finalizarea
  este blocata pana cand toate locatiile au `Final manager` completat.
- zona `Target per locatie` are filtru multi-select pe locatie: dropdown cu
  bife, selectie/deselectie pentru una sau mai multe locatii si reset rapid la
  toate locatiile vizibile. Nu exista camp separat de cautare manuala.
- click pe numele unei locatii deschide un drawer lateral cu 16 luni de
  istoric. Graficul comuta intre `Vanzari`, `Bon2Acc` si `Focus/Acc`, iar
  drawer-ul include KPI-uri Retail si ponderea agentilor activi in luna
  cohortei. `Zile cu vanzari` se calculeaza din datele distincte
  `reporting_agent_day.sale_date`, cu fallback la agregatul lunar numai daca
  lipsesc randurile zilnice.
- cardul superior `Calculator Target`, cu parametrii si actiunea de calcul,
  este vizibil numai proprietarului configurat; acesta include switch-ul
  `Anul trecut` / `Multi-year`, cu multi-year implicit. Managerii incep direct
  cu documentul rezultat si completarile `Final manager`, iar singura lor
  actiune manuala asupra draftului este `Salveaza acum`.
- sub-tab-ul Management selectat este restaurat dupa refresh, astfel incat
  utilizatorul sa revina direct in `Calculator Target`.

## Regula de cohorta

Pentru o luna tinta, calculatorul include numai magazinele cu vanzari Retail
in ultima luna disponibila anterior lunii tinta. Exemplu: pentru target
`2026-06`, cand ultima luna incarcata este `2026-05`, cohorta este lista
magazinelor cu vanzari in `2026-05`.

Inainte de salvarea draftului, cohorta elimina intrarile active din
`target_calculator_store_exclusions`. Regula acopera magazine inchise in luna
de referinta, care inca au vanzari in acea luna dar nu trebuie sa primeasca
target pentru luna urmatoare. Primele intrari sunt `CRFVUL` (Mobiup Carrefour
Vulcan) si `CRFARENA` (MobiCell Grand Arena), effective din `2026-07`.

Apartenenta `firma`, `regional` si `asm` se salveaza in randul draftului la
momentul calculului, pentru ca filtrarea si exportul sa ramana reproductibile.

## Algoritm `seasonal_blended_multiyear_v1`

Parametri configurabili:

- `target_month`
- `total_target`
- `min_floor`
- `previous_month_floor_pct`
- `previous_month_cap_pct`
- `seasonality_years` (`1` pentru anul trecut, `3` pentru multi-year)

Perioadele folosite sunt derivate automat. Pentru fiecare an istoric se ia
perechea `luna anterioara targetului -> luna target`, iar luna curenta intra ca
forecast/baza operationala:

| Rol | Luna |
| --- | --- |
| Baza sezoniera Y-1 | `target_month - 13 luni` |
| Luna target Y-1 | `target_month - 12 luni` |
| Baza sezoniera Y-2 | `target_month - 25 luni` |
| Luna target Y-2 | `target_month - 24 luni` |
| Baza sezoniera Y-3 | `target_month - 37 luni` |
| Luna target Y-3 | `target_month - 36 luni` |
| Referinta curenta | `target_month - 1 luna` |

Exemplu: pentru targetul din `2026-07`, modul `Anul trecut` foloseste
`2025-06 -> 2025-07` si `2026-06`. Modul `Multi-year` adauga perechile
`2024-06 -> 2024-07` si `2023-06 -> 2023-07`, daca exista date.

Daca o perioada folosita la calcul este inca partiala, valoarea de vanzari
utilizata este forecastata din baza live cu aceeasi regula folosita in
Hub/CRM: `realizat_importat * zile_luna / ultima_zi_importata`. Draftul
salveaza atat realizatul importat, cat si forecast-ul si factorul folosit,
iar interfata si exportul le marcheaza explicit.

Pentru fiecare locatie:

```text
IS_magazin = weighted_average(target_istoric / baza_istorica)
IS_manager = weighted_average(total_manager_target_istoric / total_manager_baza_istorica)
IS_retea = weighted_average(total_retea_target_istoric / total_retea_baza_istorica)
IS_blended = 50% IS_magazin + 30% IS_manager + 20% IS_retea
estimare_bruta = forecast_luna_curenta * IS_blended_limitat * ajustare_trend
```

In multi-year, anii utilizabili primesc ponderi `70/30` pentru doi ani sau
`50/30/20` pentru trei ani, cu anul cel mai recent primul. Daca magazinul are
istoric slab, ponderile devin `30/40/30`; daca nu are factor de magazin,
formula foloseste `0/60/40`. Factorul sezonier este limitat implicit la
`0.70 - 1.70`, iar ajustarea de trend este mica si limitata.

Floor-ul per locatie este:

```text
max(min_floor, forecast_luna_curenta * previous_month_floor_pct)
```

Cap-ul per locatie este `forecast_luna_curenta * previous_month_cap_pct`, dar
nu poate cobori sub floor. Bugetul se distribuie proportional cu estimarile
brute. Magazinele care ar primi mai putin decat floor-ul sau mai mult decat
cap-ul sunt fixate la limita, iar diferenta ramasa se redistribuie iterativ
celorlalte magazine. Daca suma floor-urilor depaseste bugetul sau suma
cap-urilor este sub buget, documentul avertizeaza utilizatorul si nu poate fi
finalizat fara alinierea valorilor finale la totalul bugetat.

## Procedura lunara

Fluxul operational este unul singur, fara scenarii paralele:

1. Spre finalul lunii curente, utilizatorul finalizator alege luna tinta
   urmatoare si introduce targetul total.
2. Apasa `Calculeaza propunerea`. Backend-ul creeaza sau actualizeaza draftul
   unic pentru luna tinta, cu cohorta din ultima luna disponibila inaintea
   lunii tinta, minus excluderile active pentru Calculator Target.
3. Daca ultima luna disponibila este partiala, valorile acesteia intra in
   calcul ca forecast, dar UI-ul pastreaza separat realizatul importat,
   forecast-ul si factorul folosit.
4. Managerii completeaza `Final manager`. Salvarea este colaborativa si se
   face per rand, astfel incat valorile devin vizibile celorlalti manageri.
5. Inainte de finalizare, toate randurile trebuie sa aiba `final_target`
   completat, iar suma finala trebuie sa fie egala cu `total_target`.
6. `Finalizeaza` publica exact cohorta aprobata in `store_targets` pentru luna
   tinta. Orice target existent pentru acea luna in afara cohortei este eliminat.

Exemplu operational: pe `2026-06-27`, pentru targetul `2026-07`, cohorta este
lista magazinelor cu vanzari in `2026-06`; calculul foloseste `2025-06`,
`2025-07` si forecast/realizat `2026-06`, in functie de stadiul importului.

## Date si publicare

`target_scenarios` retine cate un singur document de lucru per luna tinta,
parametrii, lunile sursa, parametrii formulei, avertizarile si statusul `draft`
sau `finalized`.

`target_scenario_rows` retine snapshot-ul locatiei, istoricul folosit,
breakdown-ul formulei in `calculation_details`, propunerea calculata, floor-ul
si targetul final editabil. Coloana `final_target` este nullable: un `NULL`
inseamna ca managerul nu a completat inca valoarea finala.

Primul calcul pentru o luna creeaza imediat un `draft` in baza de date.
Recalcularea aceleiasi luni actualizeaza draftul existent si reseteaza
valorile finale/observatiile, dupa confirmarea utilizatorului.
O luna deja finalizata nu mai poate fi recalculata. Editarile
de `Final manager` si `Observatii` se salveaza automat numai pentru randurile
modificate; astfel doi manageri pot ajusta magazine diferite in acelasi draft
fara ca o salvare sa suprascrie randurile celuilalt. Clientul reincarca
periodic documentul cand nu are modificari locale nesalvate.
Cand interfata este filtrata pe un manager, actiunea de resetare la propunerea
calculatorului se aplica numai magazinelor vizibile ale managerului selectat.
Lansarea unui calcul pentru o alta luna declanseaza salvarea modificarilor
locale ramase in draftul curent inainte de navigare.

La finalizare, aplicatia inlocuieste setul de `store_targets` pentru luna tinta
cu exact randurile documentului finalizat. Astfel magazinele care nu mai sunt
active nu raman in targetul oficial al lunii. Finalizarea este respinsa daca
exista macar o locatie cu `final_target IS NULL` sau daca suma valorilor finale
nu este egala cu targetul total al documentului.
Managerii pot salva valorile finale, dar actiunile de calcul/recalculare si
`Finalizeaza` sunt disponibile si autorizate server-side numai pentru emailurile OIDC configurate in
`TARGET_CALCULATOR_FINALIZER_EMAILS` (implicit `aner.valens@gmail.com`).

Consecinta asumata a regulii de cohorta: un magazin nou, fara vanzari in luna
cohortei, nu este inclus automat in targetul final. Daca apare necesitatea de
a bugeta magazine inainte de prima vanzare, fluxul trebuie extins cu o
exceptie explicita de includere, nu prin targete introduse separat in
`store_targets`, deoarece finalizarea publica exact cohorta aprobata.

## API

| Metoda | Endpoint | Scop |
| --- | --- | --- |
| GET | `/api/target-calculator/context` | Sugestii de luna, cohorta, parametri initiali si permisiunea `can_finalize` |
| GET | `/api/target-calculator/scenarios` | Lista documentelor de target per luna, folosita la incarcare |
| POST | `/api/target-calculator/scenarios/calculate` | Creeaza sau recalculeaza draftul lunii, numai pentru proprietarul configurat |
| GET | `/api/target-calculator/scenarios/{id}` | Detalii, randuri si agregari pentru grafice |
| PATCH | `/api/target-calculator/scenarios/{id}/rows` | Salveaza targetele finale editate |
| GET | `/api/target-calculator/scenarios/{id}/stores/{site_code}` | Drawer detaliu locatie: 16 luni, KPI-uri si agenti |
| POST | `/api/target-calculator/scenarios/{id}/finalize` | Publica valorile in `store_targets`, numai pentru finalizatorii configurati |
| GET | `/api/target-calculator/scenarios/{id}/export` | Export Excel |

## Export

Workbook-ul exportat are trei foi:

- `Targete finale`: istoric per locatie, sezonalitate, trend, estimare bruta,
  floor, cap, propunere, Final manager, diferenta, flag-uri si observatii;
- `Rezumat manageri`: totaluri propuse si finale pe regional;
- `Parametri`: cohorta, formula, parametri si avertizari.
