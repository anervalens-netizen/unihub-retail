# Prompt pentru agentul de pe server — UniHub Retail forensic remediation

Lucrează pe repository-ul `anervalens-netizen/unihub-retail` și tratează PR-ul
care are head branch `agent/forensic-remediation-final-20260807` ca singurul
candidat. Ignoră și nu folosi branchurile/PR-urile vechi cu `bootstrap`,
`verified-code` sau PR #123.

## Obiectiv

Validează independent candidatul, integrează-l numai dacă toate porțile sunt
verzi, generează artifactul pentru SHA-ul exact rezultat și îl livrează prin
workflowul formal. Nu recrea soluția, nu copia fișiere individual și nu modifica
logica doar pentru a face testele verzi.

## Reguli obligatorii

1. Confirmă că PR-ul pornește din `main` curent și notează head SHA.
2. Citește integral:
   - `docs/engineering/forensic-remediation-verification-matrix-2026-08-07.md`;
   - `docs/engineering/forensic-remediation-implementation-2026-08-07.md`;
   - `docs/operations/forensic-remediation-rollout-2026-08-07.md`;
   - `docs/adr/006-verified-runtime-delivery.md`.
3. Rulează pe SHA exact:
   - migration manifest, fresh DB și upgrade DB;
   - OpenAPI drift;
   - mypy, pip/npm audit, detect-secrets și Bandit;
   - backend suite izolată completă;
   - typecheck, complexity Python/TS, lint, unit, build, RUM, bundle;
   - Playwright responsive/accessibility.
4. Nu mări pragurile ratchet și nu actualiza baseline-uri ca să ascunzi o
   regresie. Orice allowance nou cere justificare și review explicit.
5. Dacă găsești defect de cod, repară în același branch, adaugă testul care îl
   reproduce, reia toate gate-urile și raportează noul SHA.
6. Inventariază utilizatorii Unix, ACL-urile și bind/firewall conform runbookului.
   Nu schimba aceste frontiere fără preflight și rollback. Raportează separat:
   `GO`, `NO-GO` sau `ACCEPTED RISK`.
7. Merge fără editări netestate. După merge pornește manual workflowul `CI` pe
   SHA-ul nou din `main`; artifactul trebuie să fie exact
   `retail-release-<SHA>`.
8. Deploy numai prin `Deploy verified Retail artifact`, cu `ci_run_id` și
   `source_sha` exacte. Nu construi pe server.
9. Execută toate probele live din runbook. O probă eșuată înseamnă NO-GO și
   rollback/roll-forward, nu relansare oarbă.

## Raport final obligatoriu

Returnează compact:

- PR și head SHA validat;
- merge SHA;
- run CI și concluzie;
- artifact name + digest;
- backup/rollback handle;
- migrări fresh/upgrade/live;
- număr teste backend/frontend/E2E;
- rezultate Grile, metrics, export, AI Forecast, P&L și HR;
- verdict Unix identities;
- verdict bind/firewall;
- servicii și health după deploy;
- orice abatere, risc acceptat sau lucru rămas.
