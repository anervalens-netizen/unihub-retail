# H-03 return receipt identity — rollout and verification

## Scope

This change corrects the definition of a return receipt used by Dashboard store, agent, regional and historical metrics.

## Pre-deploy verification

1. Run `backend/scripts/reconcile_return_receipt_identity.sql` with a read-only production role.
2. Record only aggregate month-level results in the engineering ledger; do not copy receipt numbers, agent names or raw transaction data.
3. Have the business owner confirm that the canonical identity is:
   `sale_date + site_code + normalized agent + bon_nr`.
4. Confirm CI passes the collision regression fixture.

## Deployment

The implementation is query-only. It requires no database migration and no frontend rebuild unless unrelated frontend changes are present in the release.

1. Merge after CI and reconciliation approval.
2. Deploy backend and restart the backend service.
3. Verify `/health` and the Dashboard endpoints.
4. Compare one agreed month against the reconciliation output.

## Rollback

Revert the H-03 implementation commit and redeploy the backend. No data or schema rollback is required.

## Expected user-visible effect

Return receipt counts may increase for months where the same `bon_nr` was reused on different dates, stores or agents. Other sales values are unchanged.
