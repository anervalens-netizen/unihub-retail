# UniHub Retail — catalog canonic

Există trei planuri de adevăr separate și nu trebuie amestecate:

1. **Lifecycle/status pentru documentația versionată:** singura autoritate
   machine-readable este [`catalog.json`](catalog.json), câmpul
   `entries[].status`. Valorile admise sunt `active`, `historical` și
   `superseded`. Etichetele `Status:` din Markdown-uri vechi sunt snapshot-uri
   istorice, nu stare curentă.
2. **Readiness/health live:** starea runtime nu este versionată în Git.
   Autoritatea este răspunsul `/readyz` împreună cu semnalele Prometheus
   definite în [`operations/retail-slo-readiness.md`](operations/retail-slo-readiness.md).
3. **Identitatea livrării:** identitatea candidatului certificat rămâne
   `RELEASE_MANIFEST.json`, generat și semnat de CI pentru SHA-ul exact; D2
   păstrează promotion state, iar tag-urile D3
   `production/retail-release-<SHA>` păstrează istoricul promovărilor.

Un view narativ de release se generează numai dintr-un `release.env` D2 exact și
verificat cu `scripts/render_production_release_notes.py`; Markdown-ul rezultat
nu este autoritate. Rendererul nu descoperă și nu selectează un release
`current`/`latest`. `releases/v*.md` sunt exclusiv note istorice și nu pot
redeclara o identitate canonică de production.

GitHub Issue #159 rămâne cronologia/evidence log al programului de remediere
istoric finalizat. GitHub Issue #226 este trackerul activ pentru programul
post-audit v2 (K1-K10); niciun issue nu înlocuiește sursa machine-readable pentru
statusul documentelor, release identity sau live health.

## Autoritate activă

- arhitectură și invariante: [`../APP_ARCHITECTURE.md`](../APP_ARCHITECTURE.md);
- reguli de repository: [`../AGENTS.md`](../AGENTS.md);
- livrare exact-SHA și rollback/DR:
  [`adr/006-verified-runtime-delivery.md`](adr/006-verified-runtime-delivery.md),
  [`../ops/README.md`](../ops/README.md);
- view-ul narativ de release este derivat din D2 promotion state prin
  `scripts/render_production_release_notes.py`; nu este o sursă de stare;
- contracte de date: [`adr/003-receipt-identity.md`](adr/003-receipt-identity.md),
  [`adr/004-sales-row-multiplicity.md`](adr/004-sales-row-multiplicity.md);
- contracte de securitate și identitate:
  [`engineering/h01-salary-identity-privacy.md`](engineering/h01-salary-identity-privacy.md),
  [`engineering/h06-bff-server-session.md`](engineering/h06-bff-server-session.md),
  [`engineering/h08-privileged-access-fail-closed.md`](engineering/h08-privileged-access-fail-closed.md);
- runbook campanii: [`RUNBOOK-campanii-promo-incentive-concursuri.md`](RUNBOOK-campanii-promo-incentive-concursuri.md);
- runbook P&L/TVA: [`RUNBOOK-import-pnl-tva-P0.md`](RUNBOOK-import-pnl-tva-P0.md);
- runbook salarii HR: [`RUNBOOK-import-salarii-HR.md`](RUNBOOK-import-salarii-HR.md);
- Grile: [`grile-integration-plan.md`](grile-integration-plan.md),
  [`engineering/h11-grile-monthly-idempotency.md`](engineering/h11-grile-monthly-idempotency.md);
- contract SLO/readiness:
  [`operations/retail-slo-readiness.md`](operations/retail-slo-readiness.md).

## Tracking și evidence

- **Issue #226:** tracker activ și protocol de reluare pentru audit follow-up v2;
- **Issues #227-#236:** cele zece workstream-uri K1-K10; fiecare deține scope-ul,
  guardrail-urile, Definition of Done și checkpoint evidence pentru obiectivul său;
- Issue #159: cronologia/evidence programului de remediere anterior, finalizat;
- Issue #170: guardrail de portabilitate pentru refactorizări; regulă de design,
  nu task separat și nu justifică abstracții speculative.

Pentru o sesiune ChatGPT nouă: citește mai întâi current `main`, apoi Issue #226
și primul issue K1-K10 deschis/neblocat. SHA-urile și statusurile din issue-uri
sunt snapshot-uri de evidence; GitHub current state rămâne sursa de adevăr.

## Evidence istoric

- planul de closure Release B, acum istoric:
  [`exec-plans/completed/UR-CLOSE-20260812.md`](exec-plans/completed/UR-CLOSE-20260812.md);
- substreamul PR #153/#158 finalizat:
  [`exec-plans/completed/UR-PR153-READY-20260814.md`](exec-plans/completed/UR-PR153-READY-20260814.md);
- release-uri istorice: [`releases/v2.0.0.md`](releases/v2.0.0.md),
  [`releases/v2.0.1.md`](releases/v2.0.1.md),
  [`releases/v2.1.0.md`](releases/v2.1.0.md);
- ultima livrare exactă documentată înaintea obiectivului curent:
  [`operations/AUDIT_REMEDIATION_5cbaae0_2026-08-11.md`](operations/AUDIT_REMEDIATION_5cbaae0_2026-08-11.md);
- handoff Retail 9.5:
  [`operations/RETAIL_9_5_FINAL_HANDOFF.md`](operations/RETAIL_9_5_FINAL_HANDOFF.md).
