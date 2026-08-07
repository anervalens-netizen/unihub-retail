# Runbook — remedierea forensic UniHub Retail

## 0. Regula de bază

Nu instala branchul direct, nu copia fișiere individual și nu reconstrui în
producție. Se livrează numai artefactul CI al SHA-ului exact rezultat după merge
în `main`.

## 1. Review și validare branch

Branch candidat:

```text
agent/forensic-remediation-final-20260807
```

Înainte de merge, verifică simultan:

- PR deschis față de `main` curent;
- head SHA neschimbat față de runul CI;
- migration manifest și migrările `062`/`063`;
- OpenAPI drift;
- mypy, pip/npm audit, Bandit și detect-secrets;
- backend suite pe PostgreSQL/Valkey izolate;
- typecheck, lint, unit, build, RUM, bundle și Playwright;
- ratchet de fișiere și funcții;
- nicio urmă `.remediation`, workflow bootstrap sau branch tehnic în diff.

## 2. Inventar server înainte de merge/deploy

### Identități Unix

Nu schimba automat `User=`. Inventariază mai întâi:

```bash
systemctl cat unihub-backend.service unihub-worker.service \
  unihub-import-worker.service unihub-retail-migrate.service
namei -l /opt/Mobiup/unihub-retail /opt/Mobiup/unihub-retail/.env*
find /opt/Mobiup/unihub-retail -xdev -maxdepth 3 -printf '%u:%g %m %p\n' | sort
```

Separarea în utilizatori dedicați este acceptată numai după definirea:

- code/read paths comune;
- env/secrets per proces;
- artifact/spool/output paths per writer;
- deploy owner root;
- rollback ACL.

Orice cutover de identitate se face separat, cu restart individual și probe.

### Bind și rețea

```bash
ss -lntp | grep -E ':(9898|9901|9902)\b'
systemctl cat caddy 2>/dev/null || true
docker ps --format '{{.Names}} {{.Networks}}' 2>/dev/null || true
nft list ruleset 2>/dev/null || iptables-save 2>/dev/null || true
```

Nu schimba `0.0.0.0` în `127.0.0.1` până nu este demonstrat că proxy-ul real
poate ajunge backendul. Cerința invariabilă este că porturile aplicației nu sunt
accesibile neautorizat din LAN/Tailscale/public.

## 3. Merge și artefact exact

1. merge PR fără editări suplimentare netestate;
2. notează SHA-ul rezultat în `main`;
3. pornește manual workflowul `CI` pe acel SHA;
4. verifică `head_sha`, concluzie `success` și artifact
   `retail-release-<head_sha>`;
5. notează `ci_run_id` și digestul artifactului;
6. nu executa build local pentru producție.

## 4. Preflight deploy

- backup verificat și rollback/roll-forward handle;
- checkout live curat;
- PostgreSQL/Valkey/Caddy/Prometheus sănătoase;
- Prometheus este în bridge mode cu exact un gateway/subnet IPv4 privat;
- `/opt/Mobiup/ops/prometheus/scrape.d` este root-owned 0755 și montat
  read-only la `/etc/prometheus/scrape.d`;
- configurația shared are `scrape_config_files` pentru acel director și nu mai
  conține jobul legacy `unihub_retail`;
- porturile `9901`/`9902` sunt libere pe gateway și nu există bind
  `0.0.0.0`/loopback;
- `GRILE_PROVIDER_STALE_AFTER_SECONDS` este între `300` și `604800`;
- schema live este compatibilă cu upgradeul la `062`/`063`.

## 5. Deploy formal

Rulează `Deploy verified Retail artifact` cu:

```text
ci_run_id=<run CI verde de pe main>
source_sha=<SHA exact al acelui run>
```

Workflowul trebuie să verifice `SOURCE_SHA`, `SHA256SUMS`, artifact digest,
migration manifest, lock global și entrypoint root-owned.

## 6. Probe după deploy

### Health și observabilitate

```bash
curl --fail http://127.0.0.1:9898/livez
curl --fail http://127.0.0.1:9898/readyz
test "$(curl --silent --output /dev/null --write-out '%{http_code}' \
  http://127.0.0.1:9898/metrics)" = 404
/opt/Mobiup/unihub-retail/ops/verify-forensic-remediation-runtime.sh \
  /opt/Mobiup/unihub-retail <SHA-exact-deployat>
```

Public, `/metrics`, `/docs`, `/redoc`, `/openapi.json` trebuie să fie 404.
Verificarea runtime cere unitățile versionate pe SHA, bindurile workerilor numai
pe gateway-ul detectat și targeturile Prometheus `unihub-retail-web`,
`unihub-retail-operations`, `unihub-retail-imports` toate UP. Verifică și că
seriile web multiprocess nu sar/resetază la scrape-uri consecutive.

### Funcțional

1. Grile overview pentru luna curentă și una închisă;
2. refresh magazin: răspuns 202, polling până terminal;
3. backend/Valkey indisponibil sau stare necunoscută: UI nu relansează orb;
4. eroare provider controlată: ultima valoare business rămâne, provider `error`;
5. export complex normal, anulare și limită;
6. AI Forecast cu zi zero/retur negativ și zi viitoare;
7. P&L total/reconciliere pe perioadă cunoscută;
8. cerere concediu inversată => 422.

## 7. Rollback

Migrările `062`/`063` sunt aditive. Nu le șterge și nu modifica checksumuri.
Dacă runtime-ul nou eșuează:

- folosește rollbackul entrypointului numai dacă manifestul rămâne compatibil;
- rollbackul trebuie să restaureze atomic și unitățile systemd, env-ul bridge și
  fragmentul scrape din același handle;
- altfel aplică hotfix roll-forward;
- păstrează operațiile Grile/export în DB pentru reconciliere;
- nu relansa operații `unknown`, `running` sau cu publish neconfirmat;
- păstrează artifactul, run ID, SHA, backup handle și probele incidentului.
