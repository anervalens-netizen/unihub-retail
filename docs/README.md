# UniHub Retail — catalog canonic

Release-ul semantic curent este **v2.1.0**, rezolvat exclusiv prin pointerul
non-self-referențial [`releases/current.json`](releases/current.json). Documentul
indicat de pointer descrie frontiera exactă `SOURCE_SHA` / artefact / digest;
dovezile concrete de deploy rămân în handoff-urile operaționale post-build.

Catalogul complet și metadatele de stare sunt în [`catalog.json`](catalog.json).
Un document datat ori marcat `historical` este evidence, nu autoritate curentă.

## Autoritate activă

- arhitectură și invariante: [`../APP_ARCHITECTURE.md`](../APP_ARCHITECTURE.md);
- reguli de repository: [`../AGENTS.md`](../AGENTS.md);
- livrare exact-SHA și rollback/DR:
  [`adr/006-verified-runtime-delivery.md`](adr/006-verified-runtime-delivery.md),
  [`../ops/README.md`](../ops/README.md);
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
- SLO/readiness: [`operations/retail-slo-readiness.md`](operations/retail-slo-readiness.md);
- planul Contract-Build-Prove activ:
  [`exec-plans/active/UR-CLOSE-20260812.md`](exec-plans/active/UR-CLOSE-20260812.md).

## Evidence istoric

- release-uri: [`releases/v2.0.0.md`](releases/v2.0.0.md),
  [`releases/v2.0.1.md`](releases/v2.0.1.md),
  [`releases/v2.1.0.md`](releases/v2.1.0.md);
- ultima livrare exactă documentată înaintea obiectivului curent:
  [`operations/AUDIT_REMEDIATION_5cbaae0_2026-08-11.md`](operations/AUDIT_REMEDIATION_5cbaae0_2026-08-11.md);
- handoff Retail 9.5:
  [`operations/RETAIL_9_5_FINAL_HANDOFF.md`](operations/RETAIL_9_5_FINAL_HANDOFF.md).
