# H-03 business approval record

## Approved decision

The canonical return-receipt identity used by UniHub Retail Dashboard metrics is:

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

## Approval

- **Decision:** approved
- **Approver role:** business owner / application owner
- **Approval date:** 2026-07-11
- **Approved wording:** “Aprob cheia canonică a bonului de retur: data vânzării + magazin + agent normalizat + număr bon.”

The approval was provided explicitly during the audit-remediation review. No personal identifier is stored in this record.
