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
| Deploy | runnerul formal nu putea lua lockul global si entrypointul instalat omitea workerul de import | sudoers minim pentru `acquire/release`, entrypoint root aliniat la sursa si gate CI |

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

## Inchidere productie

- commit aplicatie: `0e05004254f6626390f2a0c51547ac7d3f0cc9e2`;
- CI final: run `29877961589`, backend/frontend/E2E verde si artefact cu SHA-256
  `cf012a04c0fcfa4fd436b830680c0b3348e96f4d8ed7a500028411256885eadd`;
- deploy formal: run `29896945061`, attempt 2, finalizat la
  `2026-07-22T06:34:13Z`; aprobarea one-time a fost consumata;
- backup `20260722_093307`: 9 fisiere, 118.010.001 bytes, checksum si sync NAS
  verificate;
- migrarea activa este `030_import_snapshot_finished_at.sql`, checksum
  `04cabecd64b54e0b6f973984d4d9eccc104d0f4a8c235d7677084452c457d67a`;
- backend, worker Grile si worker import sunt `active/running`; health si
  readiness locale sunt OK, fara erori de startup;
- public serveste `assets/index-CPhZifln.js`; `/health` raspunde 200, iar
  `/metrics`, `/docs`, `/redoc` si `/openapi.json` raman 404;
- rollback handle:
  `/opt/Mobiup/ops/backups/retail-deploy/20260722T063307Z-f98af1c6db01-to-0e05004254f6-40b9e57afe6b3584`.

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

## Reaudit 2026-07-27

- frontendul public transfera initial aproximativ 202 KiB Brotli; chunkul
  `charts` ramane lazy, aproximativ 121 KiB Brotli, iar assetele cu hash au
  cache `immutable` si sunt servite prin Cloudflare;
- in ultimele 7 zile, Prometheus a masurat Dashboard p50 467 ms / p95 1,27 s
  si Promo/Incentive p50 519 ms / p95 2,25 s; ruta Agent Evaluation v2 ramane
  cea mai lenta, cu p95 8,54 s pe fereastra de 7 zile si 2,28 s pe 24 ore;
- iowait p95 pe 24 ore este 2,88%, dar swapul a ramas activ; varful iowait de
  28,9% pe 7 zile include presiunea anterioara remedierilor de host;
- RUM era prezent in bundle, dar CSP bloca `errors.unihub.ro`; originul este
  acum permis explicit si acoperit de testul headerului de securitate;
- Promo/Incentive reevalua aceleasi promotii in sumar si in proiectia
  detaliata. Contextul request-local reutilizeaza acum evaluarile complete si
  pe perioade: 9 evaluari devin 3;
- A/B pe hostul de productie, aceeasi luna si acelasi scope: mediana a scazut
  de la 2.806 ms la 2.526 ms (-10,0%), iar raspunsul canonic a ramas identic,
  SHA-256
  `80d677d28870937a50d27bc4c3e43facbfe1622f939d32b0eab35c7ddb98d93b`;
- auditul npm runtime si `pip-audit` nu raporteaza vulnerabilitati. Lockfile-ul
  foloseste patchurile disponibile pentru `brace-expansion` si `fast-uri`;
  auditul complet pastreaza doar alerta build-only din lantul
  `vite-plugin-pwa`/`workbox-build`, fara remediere upstream non-breaking.
  Updateurile minore disponibile nu sunt amestecate cu aceasta optimizare fara
  benchmark sau beneficiu operational demonstrat.

Prioritatile urmatoare sunt profilarea Agent Evaluation v2 pe scope-urile lente,
inchiderea SLO-urilor din RUM dupa trafic suficient si reducerea swapului activ.

### Agent Evaluation v2 follow-up

Profilarea scope-ului implicit, agregat din ianuarie 2025, a confirmat ca
evaluarea foliilor premium citea 333.587 linii din `sales_transactions` si le
deduplica dupa joinul multi-model. Evaluarea foloseste acum agregatul canonic
`reporting_item_month.positive_quantity` si view-ul unic per produs
`v_premium_glass_products`.

- `EXPLAIN ANALYZE`: 922 ms -> 721 ms (-21,8%);
- A/B intercalat pe productia curenta, n=4: mediana 822 ms -> 740 ms (-9,9%);
- aceleasi 153 randuri si acelasi hash canonic pentru istoricul complet si
  pentru ultima luna;
- frontendul cere doar modul vizibil; nu mai ruleaza implicit si evaluarea
  legacy de aproximativ 290-310 ms cand utilizatorul vede scorul V2.

Validarea finala: 1.302 teste backend trecute, 234 teste frontend trecute,
mypy, TypeScript, ESLint, build PWA si verificarea artefactului RUM verzi.

### Promo same-model follow-up 2026-07-28

Raportul operational a confirmat o regresie reala, nu doar asteptare in coada:
Promo/Incentive p95 a ajuns la 4,775 s, iar `special_cards` la 4,663 s.
Profilarea aceleiasi luni si aceluiasi scope a izolat joinul
`same_model_screen_camera`: planul generic reunea de mii de ori aceleasi
randuri intermediare si consuma 0,6-1,9 s per subperioada, desi citirea
filtrata din `sales_transactions` dura aproximativ 10 ms.

Evaluatorul citeste acum o singura data randurile filtrate de cod/perioada si
face potrivirea bounded pe cheia canonica a bonului in memorie. Selectia ramane
identica: acelasi model, o singura unitate camera per bon, apoi pret/cod/ID
crescator. Comparatia read-only pe productia curenta a pastrat exact hashul
canonic
`8b55dede6d14b009803172f6dafe5eef65af3c97988c0a9246a58c0953c54f39`.
Pe trei rulari consecutive, mediana Promo/Incentive a scazut de la 2.781 ms la
312 ms (-88,8%); candidatul a ramas intre 291 si 894 ms. Gate-ul tintit are 62
teste si mypy verzi.

### P2.3 PostgreSQL si export spool 2026-08-03

`backend/scripts/report_pg_stat_statements.py` produce acum un raport JSON
read-only, limitat la baza si utilizatorul curent, ordonat dupa timpul total si
cu `calls`, mean, rows, shared buffers si temp buffers. Rularea read-only pe
productia `5586ff614ece00ed20bed27f21401a63b7418095`, la
`2026-08-03T02:02:33+03:00`, a confirmat extensia activa. Cea mai costisitoare
semnatura observata avea 22 apeluri, 8.686,307 ms total si 394,832 ms mean;
acesta este baseline operational, nu autorizatie de indexare fara
`EXPLAIN (ANALYZE, BUFFERS)` si A/B cu hash business.

Downloadul configurabil XLSX foloseste un spool bounded (8 MiB in memorie,
apoi fisier temporar) si raspuns chunked de 256 KiB cu cleanup la final. Calea
compatibila ce intoarce `bytes` ramane doar pentru apeluri in-process si teste;
routerul public nu o mai foloseste. Writerul OpenPyXL si randurile raportului
nu sunt inca complet streaming, deci benchmarkul de export maxim si impactul
asupra p95 Dashboard raman deschise pentru fereastra post-deploy.
