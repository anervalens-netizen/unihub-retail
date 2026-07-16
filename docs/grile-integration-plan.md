# Integrarea Grile în UniHub Retail

Acesta este contractul canonic curent pentru integrarea Grile. Planul istoric de
cutover a fost închis; implementarea activă rulează nativ în Retail, fără proxy
către aplicația Grile veche și fără schimbarea linkurilor permanente Google.

## Surse de adevăr

- arhitectură și boundary-uri: `APP_ARCHITECTURE.md`;
- idempotency, manifest și reset: `docs/engineering/h11-grile-monthly-idempotency.md`;
- siguranța formulelor: `docs/engineering/h12-spreadsheet-formula-safety.md`;
- schema curentă: migrările din `backend/db/migrations/` și manifestul lor;
- runtime: `backend/routers/grile.py` → servicii → repositories;
- UI: `src/components/GrileSubtab.tsx` și `src/components/GrileMonthlyPanel.tsx`.

`backend/db/schema_v2.sql` este un baseline înghețat pentru instalări noi. Orice
evoluție de schemă se face prin migrare expand/migrate/switch/contract, fără
rescrierea baseline-ului sau a migrărilor aplicate.

## Contractul verificării

`POST /api/grile/run` rezervă și pune în coadă exclusiv o verificare read-only.
Jobul citește valorile și metadatele Google necesare, compară cu starea Retail și
persistă rezultatul verificării; nu modifică `agent_targets` și nu scrie în
Google Sheets.

Pentru fiecare lună poate exista cel mult un run `queued` sau `running`.
Rezervarea PostgreSQL precedă enqueue-ul, heartbeat-ul menține lease-ul, iar o
rezervare abandonată devine auditabil `failed` înainte de o nouă încercare.

Scope-urile clientului de verificare sunt strict read-only:

- `spreadsheets.readonly` pentru valorile grilei;
- `drive.metadata.readonly` pentru metadatele necesare monitorizării.

## Targete agent: diff și sincronizare

Citirea targetelor agent este separată în două operații:

1. dry-run/diff calculează schimbările propuse și dovedește prin hash că starea
   completă `agent_targets` a rămas identică;
2. sync rulează numai în worker și necesită grupul OIDC dedicat, CSRF, rate
   limit, audit și identitatea stabilă OIDC `sub`.

Un utilizator autentificat obișnuit poate verifica Grile, dar primește 403 la
sync. Apply este fail-closed dacă un sheet activ nu poate fi citit complet,
există target invalid sau mapping ambiguu, ori starea s-a schimbat față de
diff-ul aprobat. Retry-ul concurent este rezervat în DB și nu poate dubla apply.

## Finalizare, arhivare și reset

Operațiile lunare sunt joburi distincte, rezervate în PostgreSQL înainte de
enqueue. Finalizarea validează strict toate valorile numerice, registry-ul,
magazinele și agenții așteptați. Orice eroare, timeout, răspuns Google incomplet,
agent lipsă sau coverage incomplet marchează operația `failed`; un artefact
parțial nu primește calea oficială.

Manifestul persistent conține luna și operația, coverage așteptat/procesat,
totaluri de control, zero erori, hashurile SHA-256 ale artefactelor,
`requested_by_sub`, `approved_by_sub` și statusul verificabil. Arhivarea aprobă
numai cea mai nouă finalizare verificată.

Resetul live acceptă numai cel mai nou manifest de arhivă verificat și aprobat.
Înainte de orice clear păstrează sursa recuperabilă și checkpointul per magazin.
Un checkpoint `uncertain` blochează retry-ul automat până la reconcilierea
manuală. La eșec, valorile sunt restaurate și verificate; zero efecte destructive
neconfirmate este condiție de succes.

## Date și identitate

- cheia magazinului este `site_code`; linkul Google permanent nu se recreează;
- ierarhia și valorile expected provin din Retail DB;
- lunile API/DB folosesc `YYYY-MM`;
- auditul de autorizare persistă OIDC `sub`, nu emailul;
- logurile nu includ nume de agenți, salarii, identificatori personali sau date
  comerciale;
- verificările live sunt read-only în afara unui rollout și approval explicit.

## Operare și verificare

Workerul Retail serializează joburile grele. După o schimbare Grile se rulează
secvențial testele API, worker, autorizare, efect DB, fail-closed și retry din
suitele `backend/tests/test_grile_*`, urmate de gate-urile complete din
`AGENTS.md`.

Deployul folosește numai artefactul verificat din CI și approval-ul local
one-time legat de run/SHA/hash. Înaintea unei migrări sau operații destructive
se verifică backupul și rollbackul. Nu se folosesc date live pentru testare.
