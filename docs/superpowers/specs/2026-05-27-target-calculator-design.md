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
  confirmata de manager.
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
propunerea calculata, floor-ul si targetul final editabil.

Primul calcul pentru o luna creeaza imediat un `draft` in baza de date.
Recalcularea aceleiasi luni actualizeaza draftul existent si reseteaza
valorile finale/observatiile la noul rezultat, dupa confirmarea utilizatorului.
O luna deja finalizata nu mai poate fi recalculata. Editarile
de `Target final` si `Observatii` se salveaza automat numai pentru randurile
modificate; astfel doi manageri pot ajusta magazine diferite in acelasi draft
fara ca o salvare sa suprascrie randurile celuilalt. Clientul reincarca
periodic documentul cand nu are modificari locale nesalvate.
Cand interfata este filtrata pe un manager, actiunea de resetare la propunerea
calculatorului se aplica numai magazinelor vizibile ale managerului selectat.
Lansarea unui calcul pentru o alta luna declanseaza salvarea modificarilor
locale ramase in draftul curent inainte de navigare.

La finalizare, aplicatia inlocuieste setul de `store_targets` pentru luna tinta
cu exact randurile documentului finalizat. Astfel magazinele care nu mai sunt
active nu raman in targetul oficial al lunii.
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
| POST | `/api/target-calculator/scenarios/{id}/finalize` | Publica valorile in `store_targets`, numai pentru finalizatorii configurati |
| GET | `/api/target-calculator/scenarios/{id}/export` | Export Excel |

## Export

Workbook-ul exportat are trei foi:

- `Targete finale`: istoric per locatie, floor, propunere, target final,
  diferenta si observatii;
- `Rezumat manageri`: totaluri propuse si finale pe regional;
- `Parametri`: cohorta, formula, parametri si avertizari.
