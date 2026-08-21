# UniHub Retail — catalog canonic

Identitatea release-ului curent nu este menținută manual în documentație.
Autoritatea machine-readable a candidatului certificat este `RELEASE_MANIFEST.json`,
generat de CI pentru SHA-ul exact, legat prin digesturi de artefact/SBOM și semnat.
Starea de production este stabilită de recordul de promovare verificat de deploy;
`releases/*.md` rămân note istorice.

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

## Remediere tehnică activă

- trackerul operațional pentru audit/remediere este GitHub issue
  [`#159`](https://github.com/anervalens-netizen/unihub-retail/issues/159); Phase C este
  **COMPLETE + CERTIFIED**, iar programul continuă cu Phase D;
- guardrail-ul de portabilitate pentru refactorizări este GitHub issue
  [`#170`](https://github.com/anervalens-netizen/unihub-retail/issues/170); acesta este
  o regulă de design, nu un task separat și nu justifică abstractions speculative.

## Evidence istoric

- release-uri: [`releases/v2.0.0.md`](releases/v2.0.0.md),
  [`releases/v2.0.1.md`](releases/v2.0.1.md),
  [`releases/v2.1.0.md`](releases/v2.1.0.md);
- ultima livrare exactă documentată înaintea obiectivului curent:
  [`operations/AUDIT_REMEDIATION_5cbaae0_2026-08-11.md`](operations/AUDIT_REMEDIATION_5cbaae0_2026-08-11.md);
- handoff Retail 9.5:
  [`operations/RETAIL_9_5_FINAL_HANDOFF.md`](operations/RETAIL_9_5_FINAL_HANDOFF.md).
