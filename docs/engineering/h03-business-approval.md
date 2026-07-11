# H-03 business approval record

## Decision requested

Approve the canonical return-receipt identity used by UniHub Retail Dashboard metrics:

```text
sale_date + site_code + normalized agent + bon_nr
```

A NULL receipt number is not counted. Agent names are trimmed; blank/NULL agent values use an explicit `<unknown>` bucket.

## Engineering evidence

- Production reconciliation covered 35 months (`2023-09` through `2026-07`).
- Legacy and canonical totals were identical in every month.
- Total receipts checked: 26,211.
- No production collision was detected.
- A synthetic PostgreSQL fixture demonstrates the legacy undercount and validates all affected Dashboard query levels.
- No database migration or data rewrite is involved.

## Approval state

**Pending explicit business-owner confirmation.**

When approved, record the approver role, date and decision in this file. Do not include personal identifiers beyond what is required for the engineering audit trail.
