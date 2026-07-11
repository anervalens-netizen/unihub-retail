# H-03 return receipt identity — rollout and verification

## Scope

This change corrects the definition of a return receipt used by Dashboard store, agent, regional and historical metrics.

## Canonical identity

The proposed business identity is:

```text
sale_date + site_code + normalized agent + bon_nr
```

`normalized agent` trims surrounding whitespace and maps blank or NULL agent values to the explicit `<unknown>` bucket. A NULL `bon_nr` is never counted as a receipt.

## Pre-deploy verification

1. Run `backend/scripts/reconcile_return_receipt_identity.sql` inside an explicit read-only transaction.
2. Record only aggregate month-level results; do not copy receipt numbers, agent names or raw transaction data.
3. Have the business owner confirm the canonical identity above.
4. Confirm CI passes the collision regression fixture.

## Reconciliation evidence — 2026-07-11

The production reconciliation was executed read-only and rolled back.

- period: `2023-09` through `2026-07`;
- months checked: `35`;
- total legacy receipts: `26,211`;
- total canonical receipts: `26,211`;
- months with a non-zero delta: `0`;
- colliding receipt numbers: `0` for every checked month;
- `absolute_delta = 0` and `relative_delta_pct = 0.00` for every checked month.

Therefore the correction does not change any currently stored monthly KPI value, while the synthetic PostgreSQL regression fixture proves that the legacy key would undercount when receipt numbers are reused across dates, stores or agents.

## CI evidence

- server-side isolated PostgreSQL suite: `637 passed, 7 skipped, 0 failed`;
- GitHub Actions run #255: backend mypy/tests and frontend typecheck/tests/build passed;
- regression fixture: legacy `2`, canonical `5`, with store/agent/regional/history assertions;
- the test does not weaken the production `bon_nr NOT NULL` schema constraint.

## Deployment

The implementation is query-only. It requires no database migration and no frontend rebuild unless unrelated frontend changes are present in the release.

1. Merge after CI, reconciliation and business approval.
2. Deploy backend and restart the backend service.
3. Verify `/health` and the Dashboard endpoints.
4. Compare one agreed month against the reconciliation output.

## Rollback

Revert the H-03 implementation commit and redeploy the backend. No data or schema rollback is required.

## Expected user-visible effect

No historical value changed in the 35 reconciled production months. Future return receipts remain counted correctly if the same `bon_nr` is reused on a different date, store or agent. Other sales values are unchanged.
