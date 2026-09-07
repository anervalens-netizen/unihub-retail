# Retail privileged deployment source

## Ce acoperă acest document

Acest runbook se aplică **numai când o schimbare trebuie promovată/deployată în
producție**. Nu înseamnă că fiecare PR runtime merge-uit în `main` trebuie să
ruleze imediat FULL sau să fie deployat.

Flux normal fără release imediat:

```text
PR -> verificare proporțională -> merge -> post-merge policy -> STOP
```

Flux de release/deploy explicit autorizat:

```text
certified main -> FULL exact-main -> artefact imutabil/provenance -> approval
-> deploy -> health/probe
```

Pentru routing/cost de verificare vezi
`../docs/engineering/verification-efficiency-policy.md`. Pentru contractul de
livrare vezi `../docs/adr/006-verified-runtime-delivery.md`.

## Privileged production boundary

`deploy-retail-artifact.sh` și `approve-retail-release.sh` sunt sursele
versionate/revizuite pentru boundary-ul root-owned. CI nu le instalează.
Provisioning-ul copiază fișierele revizuite în `/opt/Mobiup/ops/scripts/`, le
face root-owned/non-writable de runner și verifică SHA-256 exact.

Același boundary instalează din artefactul exact-main verificat:

- `provision-retail-service-identities.sh`;
- `provision-retail-salary-export-database.sh`.

Prima execuție autorizată pentru provisioning este:

```bash
sudo /opt/Mobiup/ops/scripts/provision-retail-service-identities.sh apply
sudo /opt/Mobiup/ops/scripts/provision-retail-salary-export-database.sh apply
sudo /opt/Mobiup/ops/scripts/provision-retail-service-identities.sh verify
sudo /opt/Mobiup/ops/scripts/provision-retail-salary-export-database.sh verify
```

Provisioning-ul OS creează doar identitățile/grupurile nologin și protejează
`.env*`. Provisioning-ul DB normalizează autoritatea NOLOGIN
`unihub_salary_export`, LOGIN-ul unic, membership fără `SET ROLE`, credentialul
aleator și DSN-ul root-protected fără output secret.

Deploy-ul gestionează asset-urile runtime versionate (systemd, migration
one-shot/tombstone, observability bridge și scrape fragment). Shared Prometheus
este validat, nu rescris. Lipsa mount/include/bridge data, eșecul `promtool` sau
lipsa target-urilor așteptate este fail-closed. Rollback-ul restaurează coerent
unitățile, environment, fragmentul, codul și `dist/`.

## Sandbox local pentru calea de deploy

Rulează numai când scope-ul schimbării sau un risc concret cere validarea căii
de deploy:

```bash
ops/test-deploy-retail-artifact.sh
```

Nu îl rula ceremonial pentru schimbări fără legătură cu release/deploy.

## PostgreSQL workload read-only

Înainte de index/partitionare/rescriere SQL, capturează workload-ul fără reset:

```bash
cd /opt/Mobiup/unihub-retail
backend/venv/bin/python backend/scripts/report_pg_stat_statements.py \
  --limit 25 --min-calls 5 --output /tmp/retail-pg-stat.json
```

Scriptul rulează `READ ONLY`, refuză lipsa extensiei și nu execută
`pg_stat_statements_reset()`. Optimizează doar query-uri user-facing demonstrate
ca problematice, cu `EXPLAIN (ANALYZE, BUFFERS)` și business hash neschimbat.

## Formal release artifact

**Intră în această secțiune numai dacă release/deploy este efectiv în scope.**

Pornește manual workflow-ul `CI` de pe `main`. FULL rulează pe runner-ul
repo-scoped `dell-retail-build`; runner-ul de producție
`unihub-retail-deploy` rămâne rezervat deploy-ului. `runner-isolation` trebuie să
treacă înaintea joburilor de build/test.

Release-ul produce pentru exact `GITHUB_SHA` identitatea/provenance necesară,
inclusiv:

- `SOURCE_SHA`;
- `SHA256SUMS`;
- `retail-release-<SHA>.tar.gz`;
- `RELEASE_MANIFEST.json` și migration identity;
- SBOM/provenance/signing material conform workflow-ului curent.

**Acesta este motivul pentru FULL la release:** construiește și certifică
artefactul care va intra live. Nu rula FULL după fiecare merge doar ca să repeți
evidence-ul PR-ului.

Validează un artefact deja descărcat fără deploy:

```bash
ops/deploy-retail-artifact.sh validate <artifact.tar.gz> <40-char-main-sha>
```

Folosește exact `head_sha` al runului pentru approval și deploy. Nu reconstrui
artefactul pe server și nu substitui alt SHA.

## Approval production

Când calea formală este selectată, sesiunea administrativă creează un approval
root-owned, one-time, 30 minute, legat de exact:

- CI run ID;
- `main` SHA;
- artifact SHA-256.

Deploy entrypoint-ul claim-uiește atomic approval-ul. Consumed/failed/expired/
mismatched/duplicate approvals nu pot autoriza altă încercare.

Approval interactiv:

```bash
sudo /opt/Mobiup/ops/scripts/approve-retail-release.sh \
  <ci-run-id> <40-char-main-sha> <64-char-artifact-sha256>
```

Promptul cere literal `APPROVE_RETAIL_PRODUCTION`. Agentul poate executa acest
gate numai când deploy-ul production este deja autorizat. Nu pune approval
creator-ul în Actions, scheduler sau identitatea de deploy.

`unihub-deploy` nu primește general sudo, Docker access, interactive login,
approval-creator permission sau manual rollback permission. Instalează
`unihub-deploy.sudoers` numai după `visudo -cf`.

## Migration / rollback safety

Rollback automat/manual este permis numai dacă target commit-ul are același
manifest imutabil de migrări ca release-ul deployat. Verificarea se face înainte
de oprirea serviciilor. Un target cu migrări lipsă/adăugate/schimbate este
refuzat și cere reviewed roll-forward sau recovery coordonat.

Dacă post-migration health eșuează și manifestul anterior este incompatibil,
recordul devine `recovery_required`. Retry-ul necesită approval nou pentru
același CI run, source SHA și artifact digest.

Deploy-ul de cod nu autorizează automat promotion Finance/TVA, salary live,
manual Grile refresh, DB mutation sau alte operații de date; acestea rămân
porți separate.

## Regula de oprire

Dacă task-ul cerut a fost doar implementare/merge și nu include release/deploy,
**oprește-te după merge + required post-merge checks**. Nu porni FULL, approval,
deploy, restart sau alte operații production din inerție.