# Retail privileged deployment source

## Rolul acestei căi

Acesta este mecanismul obligatoriu pentru orice modificare runtime. Conform
`../docs/adr/006-verified-runtime-delivery.md`, codul, frontendul, migrările,
workers și configurația operațională intră live numai din artefactul CI al
SHA-ului exact. Conversația autorizează execuția autonomă, dar nu înlocuiește
CI-ul, digestul sau deploy workflow-ul. Calea fără artefact este limitată la
documentație non-runtime și break-glass strict.

`deploy-retail-artifact.sh` and `approve-retail-release.sh` are the reviewed
sources for the root-owned production boundary. CI must never install them.
Provisioning is a separate privileged operation that copies the reviewed files
to `/opt/Mobiup/ops/scripts/`, makes the files and parent directory root-owned
and non-writable by the runner, and verifies the installed SHA-256 values match
the reviewed sources exactly.

Același boundary instalează, din artefactul exact-main verificat,
`provision-retail-service-identities.sh` și
`provision-retail-salary-export-database.sh`. Prima execuție autorizată este:

```bash
sudo /opt/Mobiup/ops/scripts/provision-retail-service-identities.sh apply
sudo /opt/Mobiup/ops/scripts/provision-retail-salary-export-database.sh apply
sudo /opt/Mobiup/ops/scripts/provision-retail-service-identities.sh verify
sudo /opt/Mobiup/ops/scripts/provision-retail-salary-export-database.sh verify
```

Provisioning-ul OS creează numai conturile nologin/grupurile exacte și securizează
fișierele `.env*`; nu schimbă încă artefactele persistente. Provisioning-ul DB
creează/normalizează autoritatea NOLOGIN `unihub_salary_export`, LOGIN-ul unic,
membershipul fără `SET ROLE`, credentialul aleator și DSN-ul root-protected,
fără output secret. Tranziția ownershipului pentru spool/promo/Grile/export se
face de deploy abia după backup verificat și stop runtime. Astfel rollbackul
vechilor unități `User=andrei` rămâne posibil prin grupurile partajate.

The deploy also owns the versioned Retail runtime assets: six long-running
systemd units plus the migration one-shot and legacy rollback tombstone,
the detected Prometheus bridge environment, and the rendered Retail scrape
fragment. The shared observability stack is provisioned once with
`scrape_config_files: /etc/prometheus/scrape.d/*.yml` and a read-only host mount
from `/opt/Mobiup/ops/prometheus/scrape.d`; the Retail deploy validates but
never rewrites the shared Prometheus config or Compose topology. Missing mount,
include, bridge data, `promtool` success or any of the six UP targets is a
fail-closed release gate. Rollback restores the prior units, environment and
fragment together with code and `dist/`.

Run the sandbox without production access:

```bash
ops/test-deploy-retail-artifact.sh
```

## Raport PostgreSQL lunar read-only

Inainte de orice index, partitionare sau rescriere SQL, captureaza topul
workloadului pentru rolul runtime fara resetarea statisticilor:

```bash
cd /opt/Mobiup/unihub-retail
backend/venv/bin/python backend/scripts/report_pg_stat_statements.py \
  --limit 25 --min-calls 5 --output /tmp/retail-pg-stat.json
```

Scriptul deschide o tranzactie `READ ONLY`, refuza lipsa extensiei si nu ruleaza
`pg_stat_statements_reset()`. Pastreaza raportul cu data, SHA-ul runtime si
dovada `EXPLAIN (ANALYZE, BUFFERS)` numai pentru query-urile user-facing care
depasesc bugetul; valorile volatile nu se copiaza in arhitectura fara data.

## Evidență Gate 0 și P0

Acest runbook nu declară manual un „release curent”. Pentru fiecare candidat
certificat, CI emite `RELEASE_MANIFEST.json` pentru exact `head_sha`, împreună cu
`SOURCE_SHA`, `SHA256SUMS`, SBOM/provenance și semnătura Sigstore. Gate 0 rămâne
artifact -> deploy -> reverify -> rollback pe SHA identic; verificarea locală fără
deploy se rulează cu `bash ops/test-deploy-retail-artifact.sh`. Approval-ul și
deployul formal consumă aceeași identitate de candidat și digestul artefactului,
iar recordul de promovare stabilește ce identitate a ajuns efectiv în production.

Pentru P0, migration manifest-ul este verificat înaintea restartului, iar recovery-ul este roll-forward sau rollback numai între manifeste identice. Nu se aplică Finance/TVA și nu se aplică salarii live din această cale: P&L effective-dated rămâne shadow-only, iar salariile rămân NO-GO până la HR.

Dovezile de cod se păstrează împreună cu SHA-ul, manifestul și outputul testelor. Hosted CI, deploy production și mutațiile de date nu sunt revendicate de acest document dacă nu există un run ID și un audit handle.

Pentru release-urile istorice precum `v2.1.0`, tagul și documentația rămân evidence
istoric. Ele nu concurează cu manifestul semnat al candidatului curent sau cu
recordul de promovare production. Deployul de cod nu autorizează promotion
Finance/TVA sau reconcilierea salary live; aceste mutații rămân porți separate.

## Artifactul CI manual

Pentru un release formal, pornește manual workflowul `CI` doar de pe `main`.
Workflowul rulează exclusiv pe runnerul repo-scoped Dell
`dell-retail-build`, cu etichetele `dell-compute`, `unihub-build` și
`unihub-retail-build`; runnerul de producție `unihub-retail-deploy` rămâne
rezervat workflowului de deploy. Serviciul build este
`actions.runner.anervalens-netizen-unihub-retail.dell-retail-build.service`,
iar hardening-ul versionat se instalează din
`ops/systemd/unihub-retail-build-runner.conf`. Runnerul trebuie să fie online,
Dell să rămână nefenced pentru compute și gate-ul `runner-isolation` să treacă
înainte de orice job de test.

După toate verificările, el rulează
`ops/build-retail-release-artifact.sh` pentru exact `GITHUB_SHA` al runului și
publică trei fișiere: `SOURCE_SHA`, `SHA256SUMS` și
`retail-release-<SHA>.tar.gz`. Scriptul refuză un checkout diferit, build lipsă
sau linkuri simbolice în `dist`; deployul re-arhivează independent același SHA
și refuză artefactul dacă sursa nu coincide byte cu byte. Folosește `head_sha`
din acel run atât la approval, cât și la deploy; nu reconstrui artefactul.

Validate an already downloaded CI artifact without deploying it:

```bash
ops/deploy-retail-artifact.sh validate <artifact.tar.gz> <40-char-main-sha>
```

GitHub required reviewers are not available for this private repository without
GitHub Enterprise. When this formal path is selected, the administrative
session creates a root-owned, 30-minute, one-time approval for the exact
successful CI run ID, `main` SHA and artifact SHA-256. The deploy entrypoint
atomically claims that approval before any application mutation and records it
as consumed or failed. A consumed, failed, expired, mismatched or duplicate
approval cannot authorize another attempt.

After the final CI artifact is verified, the operator or execution agent acting
under the active chat authorization runs interactively:

```bash
sudo /opt/Mobiup/ops/scripts/approve-retail-release.sh \
  <ci-run-id> <40-char-main-sha> <64-char-artifact-sha256>
```

The prompt requires the literal `APPROVE_RETAIL_PRODUCTION`. The execution agent
may complete this gate without asking the operator to run the command. Never
place it in Actions, a script run by the deploy identity, or an unattended
scheduler.

Invocation of this artifact entrypoint is allowed only through the workflow
and the dedicated `unihub-deploy` OS identity. ADR-006 elimină calea local-first
pentru runtime. Install `unihub-deploy.sudoers` only
after validating it with `visudo -cf`. Politica permite numai entrypointul de
artefact si operatiile `acquire`/`release` ale lockului global
`/usr/local/sbin/unihub-deploy-lock`; scriptul lock root-owned valideaza strict
tokenul `GITHUB_RUN_ID-GITHUB_RUN_ATTEMPT` si timpii. CI verifica atat sintaxa,
cat si prezenta ambelor operatii, pentru ca workflow-ul sa nu ajunga la un
prompt sudo imposibil pe runner. Do not grant that identity general sudo,
Docker access, interactive login credentials, permission to run the approval
creator, or permission to invoke manual rollback. Set
`PRODUCTION_DEPLOY_APPROVALS_ENFORCED=true` only after the root-owned approval
store, exact sudo policy and dedicated runner are verified.

Manual and post-migration automatic rollback are allowed only when the target
commit has the exact same immutable migration manifest as the deployed commit.
The entrypoint performs this check before stopping either service. A target
with missing, added or changed migrations is refused without touching the live
checkout or frontend. Recover such a release by reviewed roll-forward; restore
the database backup only in a coordinated maintenance operation that also
accounts for every consumer and any writes after the backup.

If a post-migration health check fails and the prior manifest is incompatible,
the audit handle becomes `recovery_required` while the failed approval remains
immutable. A retry needs a fresh one-time approval for the same CI run, source
SHA and artifact digest; it reruns migrations idempotently, verifies health and
archives the first approval link before recording the recovery as deployed.
