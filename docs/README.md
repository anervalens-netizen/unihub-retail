# UniHub Retail — catalog canonic

Acest index separă clar **starea curentă** de evidence-ul istoric.

## Surse de adevăr

1. **Lifecycle documentație:** [`catalog.json`](catalog.json), câmpul
   `entries[].status` (`active`, `historical`, `superseded`). Etichetele vechi
   din Markdown nu pot suprascrie catalogul.
2. **Runtime health/readiness:** `/readyz` + semnalele Prometheus documentate în
   [`operations/retail-slo-readiness.md`](operations/retail-slo-readiness.md).
3. **Release/deploy identity:** `RELEASE_MANIFEST.json`, `SOURCE_SHA` și
   provenance-ul generate pentru exact SHA-ul release-ului; production state
   este dat de mecanismul de promotion, nu de un Markdown „latest”. View-ul
   narativ se generează numai prin `scripts/render_production_release_notes.py`,
   iar tag-urile istorice de promotion folosesc prefixul
   `production/retail-release-`. Nici rendererul, nici release notes nu aleg un
   release „current/latest” în locul autorității machine-readable.
4. **Verification cost/routing:**
   [`engineering/verification-efficiency-policy.md`](engineering/verification-efficiency-policy.md).
   Aceasta este autoritatea pentru întrebarea „ce verificare merită rulată și
   când?”.

## Audituri finalizate

- **Issue #159 is chronology/evidence only** — audit remediation istoric,
  finalizat.
- Issue **#226** — Audit follow-up v2 K1–K10, **finalizat și închis la
  2026-09-07**.
- Issues **#227–#236** — workstream-urile istorice K1–K10.

Aceste issue-uri sunt evidence/cronologie. **Nu sunt planuri active, nu se
reiau automat și nu justifică PR-DEEP/FULL/hardening nou.** Un viitor agent le
citește numai dacă task-ul cere explicit istoria auditului.

## Start pentru o sesiune nouă

Pentru muncă normală:

1. citește current `main` și task-ul/issue-ul concret;
2. citește `../AGENTS.md`;
3. citește documentele de domeniu strict relevante;
4. aplică verificarea proporțională din
   `engineering/verification-efficiency-policy.md`;
5. oprește-te când outcome-ul cerut este demonstrat.

Nu porni de la #159/#226 și nu inventa un „următor audit item” doar pentru că
acele trackere există.

## Autoritate activă

- arhitectură și invariante: [`../APP_ARCHITECTURE.md`](../APP_ARCHITECTURE.md);
- reguli agent/repository: [`../AGENTS.md`](../AGENTS.md);
- verificare eficientă:
  [`engineering/verification-efficiency-policy.md`](engineering/verification-efficiency-policy.md);
- fast/deep CI routing:
  [`engineering/pr-fast-lane.md`](engineering/pr-fast-lane.md);
- livrare production și rollback:
  [`adr/006-verified-runtime-delivery.md`](adr/006-verified-runtime-delivery.md),
  [`../ops/README.md`](../ops/README.md);
- continuitate operator:
  [`operations/successor-operator-continuity.md`](operations/successor-operator-continuity.md);
- handoff operațional Retail 9.5:
  [`operations/RETAIL_9_5_FINAL_HANDOFF.md`](operations/RETAIL_9_5_FINAL_HANDOFF.md);
- contracte date:
  [`adr/003-receipt-identity.md`](adr/003-receipt-identity.md),
  [`adr/004-sales-row-multiplicity.md`](adr/004-sales-row-multiplicity.md);
- securitate/identitate:
  [`engineering/h01-salary-identity-privacy.md`](engineering/h01-salary-identity-privacy.md),
  [`engineering/h06-bff-server-session.md`](engineering/h06-bff-server-session.md),
  [`engineering/h08-privileged-access-fail-closed.md`](engineering/h08-privileged-access-fail-closed.md);
- campanii:
  [`RUNBOOK-campanii-promo-incentive-concursuri.md`](RUNBOOK-campanii-promo-incentive-concursuri.md);
- P&L/TVA: [`RUNBOOK-import-pnl-tva-P0.md`](RUNBOOK-import-pnl-tva-P0.md);
- salarii HR: [`RUNBOOK-import-salarii-HR.md`](RUNBOOK-import-salarii-HR.md);
- Grile: [`grile-integration-plan.md`](grile-integration-plan.md),
  [`grile-v2-product-contract.md`](grile-v2-product-contract.md),
  [`engineering/h11-grile-monthly-idempotency.md`](engineering/h11-grile-monthly-idempotency.md);
- SLO/readiness:
  [`operations/retail-slo-readiness.md`](operations/retail-slo-readiness.md).

## Proveniența evidence-ului tehnic

Pentru afirmații empirice noi/actualizate folosește clasa care descrie exact ce
s-a verificat:

- `VERIFIED_STATIC` — confirmat în sursa/configurația exactă;
- `VERIFIED_CI` — confirmat prin CI legat de SHA/run exact;
- `VERIFIED_RUNTIME` — observat într-un mediu declarat;
- `VERIFIED_REPRODUCED` — reprodus independent;
- `DECLARED` — documentat, dar nereprodus în lucrarea curentă;
- `HISTORICAL` — evidence pentru snapshot trecut.

Nu transforma `DECLARED` în `VERIFIED_*` fără verificare și nu rerula evidence
valid doar pentru a schimba timestamp-ul.

## Documente istorice păstrate pentru navigare

Statusul curent se citește întotdeauna din `catalog.json`:

- [`AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md`](AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md);
- [`PERFORMANCE_REVIEW_2026-07-22.md`](PERFORMANCE_REVIEW_2026-07-22.md);
- [`PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md`](PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md);
- [`PLAN_PERFORMANTA_OPERATIVITATE_2026-07-21.md`](PLAN_PERFORMANTA_OPERATIVITATE_2026-07-21.md);
- [`PLAN_DEZVOLTARE_RETAIL_UNIHUB_10_10_2026-08-02.md`](PLAN_DEZVOLTARE_RETAIL_UNIHUB_10_10_2026-08-02.md);
- [`PLAN_TEHNIC_RETAIL_UNIHUB_2026-08-04.md`](PLAN_TEHNIC_RETAIL_UNIHUB_2026-08-04.md);
- [`PLAN_UNIC_UNIHUB_RETAIL_PESTE_9_2026-08-06.md`](PLAN_UNIC_UNIHUB_RETAIL_PESTE_9_2026-08-06.md);
- completed execution plans under [`exec-plans/completed/`](exec-plans/completed/);
- release notes under [`releases/`](releases/).

Historical documents remain useful evidence, but they never override current
`main`, active contracts or the verification-efficiency policy.
