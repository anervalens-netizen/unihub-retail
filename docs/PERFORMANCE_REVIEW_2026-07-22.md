# Review tehnic si performanta Retail - 2026-07-22

## Verdict

Aplicatia pastreaza invariabilele Retail si are acum cai mai predictibile sub
concurenta. Schimbarile sunt optimizari masurate sau corectii fail-closed; nu au
fost schimbate formulele de target, identitatea bonului, multiplicitatea
randurilor, scope-ul Team Leader pentru Vizite sau excluderile Cartele/TR.

## Invariabile protejate

- raportarea operationala citeste `reporting_*`; Cartele si `TR %` raman in
  afara KPI Retail;
- un `site_code` explicit domina ierarhia curenta in istorice si exporturi;
- randurile identice din Excel raman fapte distincte;
- Promo calificat si cantitate Incentive raman metrici diferite;
- `fieldops_visits` este autoritatea Vizite, grupata dupa snapshotul autorului
  Team Leader si imbogatita cu ierarhia curenta a magazinului;
- importul lunar ramane tranzactional, admin-only, serializat in worker si
  reconstruieste agregatele dupa inlocuirea snapshotului.

## Probleme inchise

| Zona | Problema | Rezolvare |
| --- | --- | --- |
| CI | verificarea unitatii systemd esua numai in fake-root | `/usr/bin/timeout` este inclus in rootul CI |
| Filtre | TTL local putea servi optiuni vechi dupa import sau stampede | cheie `(luna, snapshot_id)`, single-flight, generation guard |
| Import | durata nu era auditabila; COPY dubla memoria DataFrame | `finished_at` real si iterator lazy pentru `copy_records_to_table` |
| Promo | actuals invalid putea deveni implicit zero sau putea supraestima Incentive | evaluator unic `complete/partial/invalid`, Incentive si exporturi fail-closed |
| Dashboard | 15 componente per luna si batch istoric complet | proiectie History fara cele 4 familii nefolosite; buget global adaptat poolului |
| Browser | requesturile vechi continuau dupa schimbarea filtrului | `AbortSignal` TanStack propagat pana la `fetch` pe ecranele grele |
| Export | motorul Promo rula si cand nu era cerut; conexiune imbricata; scope istoric incorect | gate SQL, fara conexiune retinuta, scope `site_code` dominant, agent fail-closed |
| Granularitate | campanii zilnice puteau afisa zero/cantitati neconfirmate | campaniile raman oficiale total/lunar, selectia zilnica este respinsa |
| Vizite | arborele incarca toate lunile si `to_char` impiedica indexul | payload pe luna si interval de date indexabil |
| PWA | validare de retea inutila pentru chunk-uri cu hash | `CacheFirst` pentru assete; datele API raman in afara cache-ului |

## Dovezi

- frontend: 32 fisiere / 233 teste; typecheck normal si strict; ESLint zero
  warnings; build PWA verde;
- backend: 1291 teste trecute, 9 skip-uri intentionate; mypy verde pe 265
  fisiere;
- dependinte runtime npm: 0 vulnerabilitati raportate;
- migrarea 030 trece runnerul izolat si checksumul este
  `04cabecd64b54e0b6f973984d4d9eccc104d0f4a8c235d7677084452c457d67a`;
- query-ul Vizite pentru iulie foloseste `ix_fieldops_visits_report_date`,
  64 randuri, 6 buffer hits si 0,091 ms pe standby-ul read-only;
- chunk Dashboard: 135,75 kB -> 117,75 kB; Vizite este chunk separat de
  aproximativ 19,11 kB; `charts` nu este precached.

## Recomandari de refactoring ramase

Acestea nu sunt buguri corectate speculativ in aceasta livrare. Cer masurare
post-deploy sau schimbare explicita de contract:

1. Mutarea agregarii multi-luna History din `Dashboard.tsx` intr-un contract
   backend agregat. Proiectia curenta reduce munca, dar browserul inca combina
   raspunsurile lunare; trebuie validat un hash business inainte de mutare.
2. Separarea `services/exports.py` in validare, query plan, agregare si writer.
   Preview-ul poate primi un plan SQL cu count+limit, iar downloadul mare poate
   folosi un fisier temporar spooled in loc de un obiect `bytes` unic.
3. Separarea monolitilor `grile_monthly.py`, `TargetCalculatorSubtab.tsx` si
   `Campaigns.tsx` numai pe boundary-uri deja acoperite de teste; nu amesteca
   aceasta munca cu modificari de formule salariale sau Google Sheets.
4. Evaluarea partitionarii tabelelor `reporting_item_day` si
   `reporting_item_month` pe `import_month`. Volumul curent este aproximativ
   1,56 milioane, respectiv 0,89 milioane randuri; decizia cere benchmark de
   import, export si backup/restore, nu doar economie teoretica.
5. Inchiderea criteriilor SLO dupa sapte zile de trafic real: Dashboard p50/p95,
   RUM LCP/INP, I/O wait, swap si impactul import/export asupra Dashboard.

## Regula pentru optimizari viitoare

Orice optimizare care atinge SQL-ul business trebuie comparata pe aceeasi luna
si acelasi scope, cu rezultat canonic identic sau cu schimbarea contractului
aprobata explicit. Nu se adauga cache fara sursa de versiune/invalidation si
nu se transforma date incomplete in zero.
