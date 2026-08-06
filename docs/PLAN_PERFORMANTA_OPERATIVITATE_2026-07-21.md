# Plan istoric: performanță și operativitate Retail

> **HISTORICAL / SUPERSEDED — 2026-08-06.** Dovezile măsurate rămân valide ca
> istoric. Singurul plan activ este
> [`PLAN_UNIC_UNIHUB_RETAIL_PESTE_9_2026-08-06.md`](PLAN_UNIC_UNIHUB_RETAIL_PESTE_9_2026-08-06.md).

Stare: **implementare si deploy inchise; observatie SLO in curs**. Planul nu folosește estimări calendaristice; fiecare
etapă se închide numai după criteriile măsurabile de acceptare.

## Stare execuție 2026-07-21

- P0 implementat: limite cgroup Retail/Astra, alertă pentru fiecare request
  peste 3 s, I/O wait, swap activ, latență Valkey și backlog import; RUM Sentry
  include Web Vitals, trasee API și clasa conexiunii;
- P1 implementat: parse/render Excel în thread, spool SHA-256 în loc de bytes
  în Valkey, worker/coadă import separată, Valkey fără AOF pentru sesiuni și
  rate-limit;
- P2 implementat: `reporting_cartela_day`, batch istoric maximum 12 luni cu
  concurență 2 și PWA shell-only; chunkul charts nu mai este precached;
- cache backend suplimentar amânat intenționat: agregatul persistent elimină
  scanarea mare, iar un cache nou nu se justifică înainte de măsurătorile live
  post-deploy și ar adăuga încă o invalidare la import.

## Actualizare 2026-07-22

- cache-ul opțiunilor de filtre este single-flight și versionat prin snapshot;
- History folosește `/api/dashboard/history-details-batch`, iar bugetul global
  Dashboard păstrează capacitate DB pentru readiness și alte requesturi;
- requesturile grele Dashboard, Focus, Agenți, P&L, Grile, AI Forecast și
  Vizite propagă anularea TanStack până la `fetch`;
- Vizite este lazy și citește arborele unei singure luni prin interval indexabil;
- exporturile fără metrici de campanie sar motorul Promo și rulează evoluțiile
  lunară/zilnică independent, cu concurență maximă 2;
- PWA folosește `CacheFirst` numai pentru assetele Vite cu hash; API-ul privat
  rămâne `no-store`;
- verificări locale: 233 teste frontend, 1291 backend, strict typecheck, lint,
  build PWA, mypy integral și audit npm verde.
- deploy formal inchis pe `0e05004` prin runul `29896945061` (attempt 2):
  backup verificat si sincronizat NAS, migrarea 030 aplicata, toate cele trei
  servicii active, health/readiness si bundle public confirmate;
- sudoers-ul runnerului permite strict entrypointul de artefact si
  `acquire/release` pentru lockul global; configuratia este validata in CI.

Rezultatele și recomandările rămase sunt în
`docs/PERFORMANCE_REVIEW_2026-07-22.md`. Țintele pe 7 zile rămân deschise până
la suficient trafic real post-deploy; ele nu pot fi declarate din teste locale.

## Baseline verificat

- frontendul, backendul și workerul sunt funcționale, iar CI este verde;
- latența publică de rețea/Cloudflare este aproximativ 46-58 ms;
- Dashboard răspunde uzual în 280-588 ms, dar presiunea hostului a produs
  vârfuri individuale de peste 9 s;
- hostul principal are 4 nuclee și 16 GiB RAM și rulează simultan producția,
  Astra/Codex, observabilitatea și containerele auxiliare;
- SSD-urile și PostgreSQL sunt sănătoase; cauza dominantă este concurența pe
  CPU, I/O și swap, amplificată de câteva căi sincrone din aplicație;
- Dell este standby DR read-only și rămâne indisponibil pentru sarcini active
  până când o arhitectură evacuabilă, separată de DR, trece preflightul.

## P0 - stabilizare host și observabilitate

- protejează Retail, PostgreSQL și Valkey prin priorități systemd explicite;
- limitează Astra/Codex și sarcinile de build/repetiție astfel încât să nu poată
  monopoliza hostul de producție;
- adaugă metrici și alerte pentru requesturi individuale lente, backlogul
  workerului, swap, I/O wait și latența Valkey la trafic redus;
- adaugă RUM în browser pentru TTFB, LCP, INP, duratele API și clasa conexiunii,
  corelate prin request ID;
- păstrează health/readiness și rollbackul actuale.

## P1 - eliminarea blocajelor backend și worker

- mută parsarea Excel promo și generarea exporturilor în afara event loopului;
- nu mai transportă fișierul brut de vânzări în payloadul Valkey: folosește
  spool local verificat prin hash și ștergere controlată după terminare;
- separă sesiunea/rate-limit de coada persistentă sau demonstrează o izolare
  echivalentă a latenței;
- separă clasele de joburi ori adaugă cozi și priorități astfel încât un job
  Google/Grile să nu blocheze importurile și exporturile;
- controlează memoria proceselor grele fără a pierde lease-urile și auditul.

## P2 - Dashboard și frontend

- înlocuiește fan-out-ul multi-lună cu un contract batch backend, limitat și
  cu concurență controlată;
- profilează și optimizează interogările Dashboard lente pe date reale;
- introduce cache numai pentru rezultate stabile, cu invalidare după import;
- restrânge precache-ul PWA la shell și folosește runtime cache pentru
  ecranele lazy;
- preîncarcă inteligent numai rutele probabile și numai când rețeaua permite.

## Criterii de închidere

- Dashboard warm: p50 sub 400 ms, p95 sub 1 s, fără requesturi peste 3 s timp
  de șapte zile de trafic real;
- auth/session p95 sub 100 ms și zero căderi readiness dependente de Valkey;
- I/O wait p95 sub 10% și fără swap activ semnificativ în intervalul de lucru;
- mobil: LCP sub 2,5 s și INP sub 200 ms pe profil 4G;
- importurile și exporturile nu cresc p95 Dashboard cu mai mult de 20%;
- hashurile și totalurile business rămân identice înainte și după optimizare.

## Decizie arhitecturală Dell

Se cercetează folosirea capacității Dell pentru Astra/Codex, fără schimbarea
rolului său de unic standby DR. Varianta acceptabilă trebuie să respecte toate
condițiile:

1. replicile PostgreSQL, volumele DR, porturile și markerii de promovare rămân
   izolate și autoritative;
2. workloadurile Astra/Codex rulează într-un slice/container separat, cu limite
   CPU, memorie și I/O;
3. un gate automat oprește și verifică workloadurile auxiliare înainte de
   `dell-dr-activate --check`, prepare, drill sau promovare;
4. starea Astra/Codex activă are backup separat și nu este confundată cu
   generațiile DR read-only;
5. o promovare poate evacua workloadurile auxiliare fără intervenții asupra
   bazelor replicate și fără creșterea RTO;
6. există rollback demonstrat la hostul principal sau la o a treia destinație.

Până la validarea acestor gates, Dell rămâne pasiv și nu primește trafic Astra
sau Codex activ.

Research-ul și designul recomandat au fost consemnate în documentul canonic DR
`/opt/Mobiup/ops/standby/dell/DELL_COMPUTE_ASTRA_CODEX_PLAN_2026-07-21.md`.
Direcția aleasă este Astra/Codex ca workload de producție separat și evacuabil
pe Dell, nu reutilizarea directoarelor mirror și nu un runner SSH improvizat.
