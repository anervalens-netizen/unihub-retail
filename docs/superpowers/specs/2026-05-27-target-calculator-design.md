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
- tabelul per locatie afiseaza, pentru fiecare dintre cele trei luni de
  referinta, atat targetul istoric, cat si realizatul si procentul realizat;
- coloanele celor doua luni consecutive din anul precedent sunt evidentiate
  vizual, pentru citirea sezonalitatii fata de luna tinta;
- tabelul operational afiseaza valoarea `Calculat`, fara a expune separat
  coloana de floor; floor-ul ramane aplicat in algoritm si pastrat in export;
- interfata nu expune un selector de scenarii: exista un singur draft pentru
  fiecare luna tinta, iar recalcularea actualizeaza acelasi draft;
- rezumatul `Calculator si Final manager` este tabelar: finalul sub propunere
  este rosu, finalul egal sau pana la `+5%` este verde, iar finalul peste
  `+5%` este galben;
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
  este vizibil numai proprietarului configurat; managerii incep direct cu
  documentul rezultat si completarile `Final manager`, iar singura lor
  actiune manuala asupra draftului este `Salveaza acum`.
- sub-tab-ul Management selectat este restaurat dupa refresh, astfel incat
  utilizatorul sa revina direct in `Calculator Target`.

## Regula de cohorta

Pentru o luna tinta, calculatorul include numai magazinele cu vanzari Retail
in ultima luna disponibila anterior lunii tinta. Exemplu: pentru target
`2026-06`, cand ultima luna incarcata este `2026-05`, cohorta este lista
magazinelor cu vanzari in `2026-05`.

Apartenenta `firma`, `regional` si `asm` se salveaza in randul draftului la
momentul calculului, pentru ca filtrarea si exportul sa ramana reproductibile.

## Algoritm `weighted_floor_forecast_v2`

Parametri configurabili:

- `target_month`
- `total_target`
- `min_floor`
- `previous_month_floor_pct`

Perioadele folosite sunt derivate automat:

| Rol | Luna |
| --- | --- |
| Luna anterioara din anul precedent | `target_month - 13 luni` |
| Aceeasi luna din anul precedent | `target_month - 12 luni` |
| Referinta floor | `target_month - 1 luna` |

Exemplu: pentru targetul din `2026-06`, tabelul si calculul folosesc
`2025-05`, `2025-06` si `2026-05`. Aceasta combinatie permite compararea
evolutiei mai-iunie din anul anterior cu nivelul disponibil din mai curent.

Daca o perioada folosita la calcul este inca partiala, valoarea de vanzari
utilizata este forecastata din baza live cu aceeasi regula folosita in
Hub/CRM: `realizat_importat * zile_luna / ultima_zi_importata`. Draftul
salveaza atat realizatul importat, cat si forecast-ul si factorul folosit,
iar interfata si exportul le marcheaza explicit. Factorul este comun tuturor
magazinelor aceleiasi luni; prin urmare ajusteaza valoarea proiectata, dar nu
schimba substantial ponderea relativa dintre magazine in acea perioada.

Pentru fiecare perioada si locatie, ponderea este media dintre ponderea in
targetul total si ponderea in valoarea de vanzari utilizata a cohortei
(`realizat` pentru luni inchise sau `forecast` pentru luni partiale).
Ponderea finala este media perioadelor care au date disponibile.

Floor-ul per locatie este:

```text
max(min_floor, target_luna_anterioara * previous_month_floor_pct)
```

Bugetul se distribuie proportional cu ponderile. Magazinele care ar primi
mai putin decat floor-ul sunt fixate la floor, iar diferenta ramasa se
redistribuie iterativ celorlalte magazine. Daca suma floor-urilor depaseste
bugetul, documentul avertizeaza utilizatorul si nu poate fi finalizat fara
alinierea valorilor finale la totalul bugetat.

## Date si publicare

`target_scenarios` retine cate un singur document de lucru per luna tinta,
parametrii, lunile sursa, avertizarile si statusul `draft` sau `finalized`.

`target_scenario_rows` retine snapshot-ul locatiei, istoricul folosit,
propunerea calculata, floor-ul si targetul final editabil. Coloana
`final_target` este nullable: un `NULL` inseamna ca managerul nu a completat
inca valoarea finala.

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

- `Targete finale`: istoric per locatie, floor, propunere, Final manager,
  diferenta si observatii;
- `Rezumat manageri`: totaluri propuse si finale pe regional;
- `Parametri`: cohorta, formula, parametri si avertizari.
