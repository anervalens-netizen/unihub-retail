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
| 042 | `042_fieldops_visits_web_authority.sql` | `371692161ff24c8877dc2e31c72bef772c190ffe41b9bf4eef63c78a33028e9c` | impune unicul ACL tabelar web owner-issued SELECT-only la sursa PostgreSQL FieldOps, fără PUBLIC/DML tabelar ori columnar sau însușirea sursei externe |

Aplicarea se face numai prin `unihub-retail-migrate.service`, cu `MIGRATION_DATABASE_URL`, backup/read-only reconciliation și verificarea checksumului. Nu edita 032–036 după aplicare; corecția este o migrare nouă.

Migrațiile nu activează singure TVA live sau importul salarial live. Promotion pointer-ul P&L și batchul salary sunt contracte de audit/recovery; apply-ul financiar și reconcilierea HR rămân explicit blocate la P0.

## Cutover P1-A și recovery

040 creează grupurile de autoritate, iar 041 preia ownershipul. La upgrade,
ambele se aplică o singură dată cu identitatea administrativă existentă, înainte
de schimbarea DSN-urilor. Invocarea de cutover setează numai pentru acel proces
`UNIHUB_DB_AUTHORITY_CUTOVER_BOOTSTRAP=1`, fără
`UNIHUB_DB_PROCESS_AUTHORITY`; flagul nu se scrie în `.env*` sau în unități.
Runnerul acceptă excepția numai pentru un superuser autentificat direct, pe o
bază existentă cu checksums complete până la 039 și exact 040/041 restante.
Refuză fresh bootstrap, alt set restant, role switch, principal neprivilegiat
sau reutilizarea după 041. Apoi operatorul creează separat cele patru LOGIN-uri
de proces și rulează `provision_runtime_database_role.py --apply` pentru exact
un contract per LOGIN. Provisionerul nu creează LOGIN, nu setează/parcurge
parole și nu acordă privilegii pe obiecte; refuză orice grant direct, default
ACL sau obiect deținut de LOGIN și verifică toate membershipurile
directe/tranzitive, opțiunile lor și toate flagurile privilegiate. Schimbarea
membershipurilor este tranzacțională și un contract inexact nu lasă granturi
parțiale. Nu se creează
LOGIN Finance; principalul rezervat pentru acel lot viitor este
`unihub_finance_import_worker`.

`fieldops_visits` rămâne sursă externă. Dacă ownerul DB este diferit de
`unihub_schema_owner`, el acordă explicit `SELECT` către `unihub_web_read`
înainte de 042. Migrarea restricționată verifică grantul și refuză fail-closed
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
