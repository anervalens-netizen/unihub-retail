# db/migrations/

Numbered SQL migrations aplicate exclusiv de runnerul separat
`scripts/run_migrations.py`. Web-ul verifica read-only ca DB-ul este curent si
refuza startup-ul daca exista drift sau migrations neaplicate.

## Convenție

- Numele: `NNN_descriere_scurta.sql` (3 cifre obligatorii, lowercase + underscore).
- Exemplu valid: `001_add_store_index.sql`, `042_rename_agent_col.sql`.
- Fiecare fisier ruleaza intr-o tranzactie si este tracked in
  `schema_migrations` impreuna cu checksum-ul SHA-256.
- Migrations sunt **imutabile** după ce au rulat în producție. Dacă greșești,
  adaugi o migration nouă care corectează, nu editezi istoric.
- `manifest.json` este gate-ul Git pentru baseline si toate migrations.

## Când folosești migration vs schema_v2.sql

- **`schema_v2.sql`** = baseline inghetat pentru instalare noua. Nu se mai
  modifica dupa H-02.
- **`migrations/NNN_*.sql`** = delta pentru DB-uri existente (dev & prod).
  Orice `ALTER TABLE`, `CREATE INDEX`, backfill DML merge aici.

Workflow tipic pentru schimbare de schemă:
1. Adaugi migration `NNN_add_column_foo.sql` cu `ALTER TABLE ... ADD COLUMN ...`
2. Actualizezi `manifest.json` cu checksum-ul fisierului nou.
3. Rulezi unitatea `unihub-retail-migrate.service` inainte de restartul web.
   Unitatea citeste exclusiv `.env.migrations`, fisier root-protected care
   contine `MIGRATION_DATABASE_URL` pentru `unihub_migration_runner`. Runnerul
   este NOINHERIT și activează ownerul NOLOGIN numai cu `SET LOCAL ROLE` în
   tranzacția migrației. Web și workerii folosesc loginurile lor non-owner.
4. Instalarile noi aplica baseline-ul inghetat, marcheaza migrations deja
   incorporate, apoi ruleaza toate delta-urile ulterioare.

## Migrațiile aditive P0–P1.3

Baseline-ul `schema_v2.sql` și migrațiile 001–031 rămân imutabile. Manifestul
release-ului `v2.1.0` include:

| ID | Fișier | SHA-256 | Contract |
| --- | --- | --- | --- |
| 032 | `032_store_pnl_shadow_generations.sql` | `a75f77c1a85fef1b39d5db11b9007d23114943b96554988566bb63e30a4923f5` | shadow generations, candidate/pre-image și pointer CAS; nu este citit de runtime |
| 033 | `033_sales_generation_staging_and_fencing.sql` | `b6e10b7198e01d7893fefe66f28879d8b363956e3a87be11f63e875df9193cb1` | staging, generation head și audit promote/rollback cu fencing |
| 034 | `034_salary_import_batch_provenance.sql` | `93dae9fa15c1b891e6484a8ddecc189e3bc412f2913066619288d0fd8938ec7f` | batch HR, source-line provenance și agregare per person_id |
| 035 | `035_grile_observation_fencing.sql` | `4afd71ef2c8e0f215bb2687d28d07ae5a7b76ebc2625b05fe3c638a315293b5f` | observații Grile append-only, claim/CAS per magazin și proiecție curentă separată |
| 036 | `036_target_rule_registry.sql` | `d722b1ef480b067651c37464c3462565ea2c9b4e5651c869e08932cd0c37b193` | registry Target append-only, snapshot/hash per scenariu și override auditabil |
| 037 | `037_sales_generation_stage_integrity.sql` | `739d3da3974a247a3169e5d0bc6af57519bfbed5dff1ddaf28f15339bf207167` | digest staging, CAS și fencing sales |
| 038 | `038_retire_replace_month_snapshot.sql` | `bac85ae88b6118e877e73ad444ed3895051a432069b460d802dc2b1144735488` | elimină bypassul legacy al snapshotului lunar |
| 039 | `039_store_pnl_authoritative_generations.sql` | `4d9f3224195bc63b09be6a4642fb585f5a8b8f3c370c76ca799f0f8620f55b9d` | generații Finance immutable, scope/head/ledger și pre-image |
| 040 | `040_db_authority_append_only.sql` | `59a15b051d73fdbbce2ce8d465b6d7a9f41ffdc7abe45744e1de6ae1db69bce9` | matrice ACL explicită, ledgers/staging/shadow append-only și head/pointer numai prin SQL/CAS |
| 041 | `041_schema_owner_handoff.sql` | `a14a3d170fce29ca9326144e358ce6ead054999cbb31599b3bde092924f00311` | owner NOLOGIN stabil, migration runner NOINHERIT și default ACL fail-closed |
| 042 | `042_fieldops_visits_web_authority.sql` | `6e120625c69ff8528bec5074782e822ba8b7c8828ed1dbb71dc1c97919013cb4` | impune unicul ACL tabelar web owner-issued SELECT-only la sursa PostgreSQL FieldOps, fără PUBLIC/DML tabelar ori columnar sau însușirea sursei externe |
| 043 | `043_sales_source_artifact_lifecycle.sql` | `28a5673b5559e773e4a94d3a52392fb3d5b3887e0b51cb4cb60b4361cdffba65` | leagă starea terminală și head-ul sales de artefactul sursă reținut și verificat |
| 044 | `044_grile_monthly_recovery_fencing.sql` | `762c6352f8a00deb6989bd24ffac5ebefc9d537817233507d92e8dd4422d7a1c` | adaugă lease/epoch, checkpointuri și clasificarea deterministă a recovery-ului Grile |
| 045 | `045_salary_approval_replay_fence.sql` | `2be9541709f7e8a9e6dfa031e8e1330e4c75779109030078a4add64e92551011` | leagă aprobarea salarială semnată de batch și interzice replay-ul artifactului |
| 046 | `046_revoke_legacy_grile_authority.sql` | `0cadf58076c820856c801c8c7bbf7c38b38e80ff26794ceb24178442c7207432` | retrage privilegiile legacy asupra stării și secvențelor Grile |
| 047 | `047_insight_reporting_read_models.sql` | `3e920d96b1f4deb81e591085b14361ae54dba058bf54fad2e1c9928e9431e9f9` | read-model-uri Insight v1 cu snapshot/versionare, P&L promovat și compensare agregată; păstrează temporar ACL N-1 până la revocarea coordonată |
| 048 | `048_insight_sales_day_read_model.sql` | `4e75756277b6d1f0351dcd456d72eb78d0531c95474a145847c1ffc038bbca79` | granularitate sales zilnică aprobată pentru inspect și export Insight |
| 049 | `049_insight_visits_team_leader_read_model.sql` | `5b24cd25bf0a79a6a4ea37e370b4ab5249724726f1dc78692526c338d6be3c5c` | read-model Visits v2 pe Team Leader autor și magazin |
| 050 | `050_insight_visits_completion_semantics.sql` | `681a2e396f3d14713d4c1d40b8c93351329390a980320b6ac2e56db597963b0d` | semantică de completare Visits canonică și fail-closed |
| 051 | `051_insight_planning_promotion_read_model.sql` | `1f7fafe8d3889d77affb2602502d0411d4bb28df0ab31a897c796e3ddf4f3bb0` | head și ledger Planning cu CAS, snapshot v3 și scenariu v2 fără promovare implicită |
| 052 | `052_insight_planning_hash_acl.sql` | `3cb4411dba9ef15723ee82df7dff7dbb75f58efa61c9dbe751000ce1986aec4d` | bridge definer îngust pentru verificarea read-only a digestului forecast promovat |
| 053 | `053_insight_campaign_publication.sql` | `bf3a4f5ae58dee480a224acc4664f2c294aa3f0d9d09f9339fcee44910f58ad2` | generații Campanii immutable, CAS/ledger, publisher canonic Focus/Promo/Incentive pe magazin+agent, `reporting_source_snapshot_v4` și `reporting_campaign_month_v2`; v1/v3 rămân rollback |
| 054 | `054_campaign_reporting_publisher_acl.sql` | `8b04375c053ca1d1e081ba17d06e3049e0b48035f547c32b8743ef7237608db8` | grant read-only minim pentru evaluatorul Incentive folosit de publisherul izolat |
| 055 | `055_durable_export_operations.sql` | `69e02b01dbfab1caf207b30a46b7abf2b1dcbeb7f51e26bcfabc5c1ec0c63b28` | operații XLSX complexe owner-bound, rezervare înainte de ARQ, lease/epoch fencing, artifact privat hash-uit, auto-download revendicat atomic și retry explicit până la TTL |
| 056 | `056_fieldops_visits_operations_authority.sql` | `36c2bda0adf6b2e15298403e164e99b75d78e46369b44510c500fdf7dcd838db` | autoritate operațională minimă pentru snapshotul local Visits, fără extinderea accesului la sursa FieldOps |
| 057 | `057_insight_contest_grile_campaign_v3.sql` | `b66ba6287f2e842be7e6be2047cf6c23e6048f92419044f0b45d639e6a83bc8e` | Campaign v3 cu variantă canonică, Concurs v1 publicat immutable, Grile v1 fenced și snapshot Insight v5; v2/v4 rămân N-1 |
| 058 | `058_insight_grile_historical_v2.sql` | `c2d369aab988931e35e32b91d90a4df650a801b1b5a9f14fa13d4f5fe3d9d4ec` | Grile v2: o singură sursă pe perioadă, proiecția fenced curentă nenulă sau, determinist, ultimul full run finalizat immutable; v1/v5 rămân N-1 |
| 059 | `059_insight_full_visibility_read_models.sql` | `e587202acff59b7d98f2d8d23dc3c0a917b583c616f97c1b6bf8af8ebcad7ed8` | read-model-uri Insight complete pentru Compensation și Finance, fără expunerea CNP |
| 060 | `060_insight_finance_v2_performance.sql` | `67975c4e926996b26a650e6cbac46d597a4c5a0f915979a7180568d4d1489e09` | materializare per-query a contractului Finance v2 fără schimbare semantică |
| 061 | `061_insight_finance_v2_period_pushdown.sql` | `7dff26f8268923cf644dcd00a1d5292f53f34b3338952d0b4be645f8bcd4b4eb` | pushdown pe perioadă pentru Finance v2 cu precedența actual/estimat păstrată |
| 062 | `062_grile_v2_read_contract.sql` | `146ac39fc6c2ec7d3f0ddc599d60e43bdbe76ad0344fe837e4439841ebb05ccc` | contractul read-only Grile V2 folosit de pilotul separat |
| 063 | `063_leave_request_date_contract.sql` | `dba80346ea5fe02213a0e39ebf9c3f408168b9b048efba75e78fff6544487df4` | contract strict pentru datele calendaristice ale cererilor de concediu |
| 064 | `064_ai_forecast_cutoff_read_model.sql` | `3fe8d8f32d51ec8a25450d3fc45bc7d64f8bdfb663949054862ea41a1805b6f4` | cutoff oficial al generației sales promovate pentru forecast, fără evidence expus webului |
| 065 | `065_salary_export_evidence.sql` | `c6bf02313f4dfeeebe3796cdf6607a1e5e797ca6aa0d76b4ee654a5773cd42bf` | export salarial durabil owner-bound, cu request/actor immutable, artefact în namespace separat și row count real atestat de worker |
| 066 | `066_salary_export_authority.sql` | `ab13ccc87b3da126f9935f1bb4ee66773afcc01417e08e3193242ddc2ed88fa5` | autoritate DB dedicată exporturilor salariale, granturi column-level și RLS care separă operațiile salariale de workerul generic |
| 067 | `067_grile_v2_operations_read_authority.sql` | `06b3c857983669677a741d6f743b47de370ce5195df33ba69d7c1f5c6b13057a` | acces SELECT minim pentru workerul Grile V2 la actuals, cartele, forecast și proiecția Campaigns versionată |
| 068 | `068_grile_v2_forecast_digest_authority.sql` | `766e550ddf03474979c2bf8c26067d5dc3a79a1e501a705a6988ae9fc47afa79` | EXECUTE minim pentru digestul de integritate folosit tranzitiv de read-model-ul Campaigns, fără acces la tabelele Planning |
| 069 | `069_ai_cohort_and_transactional_outbox.sql` | `0dc10e3e14cec4a44b9b0ac0ccf1c69abf0e9cfacd0920540a7b5097e2875fa0` | cohortă AI istorică immutable și outbox tranzacțional ordonat/idempotent; schema este inertă până la Release B |

Aplicarea se face numai prin `unihub-retail-migrate.service`, cu `MIGRATION_DATABASE_URL`, backup/read-only reconciliation și verificarea checksumului. Nu edita 032–036 după aplicare; corecția este o migrare nouă.

### Campaigns v2 publication (053–054)

După aplicarea 053, pornește imports workerul cu codul care conține
`publish_campaign_reporting_background`, apoi rulează întâi read-only:

```bash
cd backend
python3 scripts/publish_campaign_reporting.py --month YYYY-MM
```

Backfill-ul scrie numai cu `--apply`, `CAMPAIGN_REPORTING_DATABASE_URL` al
imports workerului și actor/motiv explicit. El publică prin funcția CAS
`publish_campaign_reporting_generation`; nu face `UPDATE`/`DELETE` pe
business data. `reporting_source_snapshot_v4` semnalizează explicit
`campaign_reporting_not_published` până la primul head, iar v1/v3 rămân
ancorele rollback N-1.

### Campaigns v3, Concurs și Grile (057)

Migrarea 057 păstrează contractele v2/v4 pentru N-1 și adaugă
`reporting_source_snapshot_v5`, `reporting_campaign_month_v3`,
`reporting_contest_month_v1` și `reporting_grile_month_v1`. După migrare,
republică lunile necesare cu același script controlat; acesta publică atât
Campaigns v3, cât și rezultatul canonic `ContestsService`, exclusiv prin
funcțiile CAS. Pentru sursele Promo POS agregate, identitatea de bon nu este
reconstruibilă: `promo_qualifying_bons` rămâne `NULL`, iar unitățile și
discountul materializat rămân disponibile cu warning explicit.

Migrațiile nu activează singure TVA live sau importul salarial live. Promotion pointer-ul P&L și batchul salary sunt contracte de audit/recovery; apply-ul financiar și reconcilierea HR rămân explicit blocate la P0.

### Grile istoric (058)

Migrarea 058 păstrează `reporting_source_snapshot_v5` și
`reporting_grile_month_v1` N-1. Contractele noi
`reporting_source_snapshot_v6` și `reporting_grile_month_v2` aleg exact o
sursă pentru fiecare lună: întreaga proiecție fenced curentă numai când are cel
puțin o observație eligibilă; altfel, full run-ul `completed` cel mai recent,
ordonat stabil după instantul terminal și `id`. Nu completează găurile unei
proiecții curente cu rânduri dintr-un run vechi. Full run-ul este final/immutable
dar poate rămâne `partial` pentru acoperire, erori sau diferențe Grilă; o
proiecție curentă rămâne explicit nefinală. Pentru fallback, populația este
setul auditat al run-ului (fence dacă există, altfel rândurile immutable), nu
lista actuală de foi: închiderea ulterioară a unui magazin nu șterge istoria.
TR și cartele rămân excluse.

### Compensation și Finance complete (059)

Migrarea 059 păstrează contractele v1 și snapshot v6 ca ancore N-1 și adaugă
`reporting_source_snapshot_v7`, `reporting_compensation_person_month_v2`,
`reporting_compensation_month_v2` și `reporting_finance_month_v2`. Compensation
publică fiecare rând salarial Retail, inclusiv rândurile legacy fără batch, fără
prag salarial sau de cohortă; CNP nu intră în contract. Finance aplică aceeași
precedență actual/estimat ca repository-ul Retail și păstrează explicit
rândurile estimate, nemapate și nealocate. Rolul Insight primește SELECT numai
pe view-urile versionate, niciodată pe sursele raw.

Migrarea 060 păstrează neschimbat contractul Finance v2 și materializează o
singură dată setul său de rânduri în fiecare interogare. Citirea P&L nu mai
reexpandează snapshoturile cross-domain doar pentru a repeta metadata.

Migrarea 061 optimizează suplimentar aceeași interfață fără schimbarea
semanticii: precedența actual/estimat și metadata sunt calculate cu ferestre pe
perioadă, iar `period_date` permite pushdown indexat pentru luna sau intervalul
cerut. Lunile fără legătură nu mai sunt scanate de interogarea Insight.

## Cutover P1-A și recovery

040 creează grupurile de autoritate, iar 041 preia ownershipul. La upgrade,
ambele se aplică o singură dată cu identitatea administrativă existentă, înainte
de schimbarea DSN-urilor. Invocarea de cutover setează numai pentru acel proces
`UNIHUB_DB_AUTHORITY_CUTOVER_BOOTSTRAP=1`, fără
`UNIHUB_DB_PROCESS_AUTHORITY`; flagul nu se scrie în `.env*` sau în unități.
Runnerul acceptă excepția numai pentru un superuser autentificat direct, pe o
bază existentă cu checksums complete până la 039 și toate migrările de la 040
încolo restante. Invocarea bootstrap aplică exclusiv 040/041 și se oprește,
chiar dacă manifestul conține 042 sau migrări ulterioare. Refuză fresh
bootstrap, istoric parțial, o migrare post-039 deja aplicată, role switch,
principal neprivilegiat sau reutilizarea după 041. Apoi operatorul creează
separat cele patru LOGIN-uri de proces și rulează
`provision_runtime_database_role.py --apply` pentru exact un contract per
LOGIN. Ownerul FieldOps acordă SELECT după ce 040 a creat autoritatea, iar 042
rulează ulterior prin identitatea restricționată de migrare. Provisionerul nu
creează LOGIN, nu setează/parcurge
parole și nu acordă privilegii pe obiecte; refuză orice grant direct, default
ACL sau obiect deținut de LOGIN și verifică toate membershipurile
directe/tranzitive, opțiunile lor și toate flagurile privilegiate. Schimbarea
membershipurilor este tranzacțională și un contract inexact nu lasă granturi
parțiale. Nu se creează
LOGIN Finance; principalul rezervat pentru acel lot viitor este
`unihub_finance_import_worker`.

`fieldops_visits` rămâne sursă externă. Dacă ownerul DB este diferit de
`unihub_schema_owner`, el acordă explicit `SELECT` către `unihub_web_read`
înainte de 042 și către `unihub_operations` înainte de 056. Migrarea 056 acordă
workerului numai `INSERT, DELETE` pe proiecția Retail `visits_snapshot`; nu îi
acordă SELECT, UPDATE sau TRUNCATE. Migrările restricționate verifică granturile și refuză fail-closed
dacă lipsește. Refuză grant option, alt grantor, orice ACL `PUBLIC`, orice ACL
columnar pentru web/PUBLIC și orice DML efectiv, inclusiv moștenit; nu schimbă
ownerul și nu cere superuser.

Cu backendul și ambii workeri opriți, `retire_legacy_database_login.py --apply`
refuză orice sesiune sau membru rămas și setează exclusiv `unihub_runtime`
`NOLOGIN`. `--rollback` poate restaura doar flagul LOGIN, fără schimbarea
credentialului; nu face un manifest vechi compatibil după 040/041.

Instalările noi fac preflightul administrativ pentru DB/schema/extensii, aplică
baselineul și 001–042 fără flagul de cutover, apoi trec definitiv runnerul la
`unihub_migration_runner`; runnerul restricționat refuză bootstrapul gol.

După aplicarea unei migrații, down migration și rollbackul la un manifest mai
vechi sunt interzise. Dacă switchul de aplicație eșuează după 040/041, handle-ul
de backup rămâne `recovery_required`, datele/headurile bune rămân neschimbate și
se face roll-forward pe același SHA sau pe un candidat corectiv verificat. Un
rollback de cod este permis numai înainte să pornească serviciul de migrare ori
către un artefact cu manifest identic. Rollbackul business rămâne CAS/inverse
generation, nu editare directă sau DELETE al evidence-ului.

## Idempotență

Migrations ar trebui să fie idempotente când e posibil (`IF NOT EXISTS`,
`CREATE INDEX CONCURRENTLY IF NOT EXISTS`). Tracking-ul în
`schema_migrations` ne acoperă pentru operațiuni care nu pot fi (DML seed,
UPDATE unic).

## Testare locală

```bash
cd backend
source venv/bin/activate
scripts/run_tests_isolated.sh -v --tb=short tests/test_migrations.py tests/test_migration_runner_db.py
```
