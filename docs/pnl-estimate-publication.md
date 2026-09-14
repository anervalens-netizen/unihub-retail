# Controlled P&L estimate publication

The owner approved implementing and activating this estimated-only path on
2026-09-11, after reviewing the HR reconstruction and the period-effective VAT
comparison. This is separate from Finance actual promotion and Target.

Migration 075 introduces immutable estimate generations, append-only events and
a monotonic global revision. The authenticated `unihub_operations_worker` can
invoke three guarded functions through its existing exclusive operations
authority. It receives no direct writes to P&L, generation evidence or revision
state. Web and Finance receive no access to the new functions. The legacy
estimator `--apply --effective-vat` and shadow pointer remain unchanged.

## Scope and model

Each manifest contains explicit company/month pairs, an input cutoff, input and
output SHA-256, source hashes, model hashes, HR coverage and the approval
reference. Only `estimated` rows inside those pairs are replaced. Actual rows,
payroll and Target are never written by this path.

Store-month coverage is independently reconstructed in SQL from the preferred
Retail sales source and the absence of canonical Finance actuals. Every expected
store has exactly 12 unique categories and one consistent source-code mapping.
Missing stores, extra stores, duplicates, ambiguous mapping, Finance overlaps,
nonfinite amounts and fractional cents are rejected.

The initial lot is the reviewed reconstruction through July 2026. HR net pay
plus vouchers remains a model input, not the full employer cost. Exact HR
reconciliation is required before using original HR store allocations for
recorded payroll months; unresolved rows remain unallocated. Four July Mobiup
Team Leader rows totaling 21,311.00 RON remain outside store allocation, as
documented in the owner review. They must not be added twice through an
unverified company-wide cost adjustment.

## Concurrency and recovery

Lock order is control row, sorted Finance-compatible advisory scope locks,
P&L table, then mapping and source tables. The context is rehashed under those
locks at staging and publication. It includes current P&L business rows,
Finance heads, site links, stores, historical/reporting sales and non-CNP
salary/HR model inputs. Input drift or revision drift fails before live DML.

Publication requires the exact sealed manifest hash, current revision and an
operator approval reference. The immutable preimage is captured by PostgreSQL.
Rollback restores only the prior estimated business rows, including original
amounts/provenance/timestamps, and advances the ledger revision. Database IDs
are newly assigned. Rollback requires the latest event to be that generation's
promotion and an unchanged postpublication context. Empty July preimages are
supported. Stale, replayed and concurrent conflicting operations fail closed.

## Operator commands

Run from the authorized repository with the existing protected `.env` read
identity and `.env.worker` operations identity. No credentials are printed or
accepted as command-line arguments. Receipts must be new private files.

```sh
backend/venv/bin/python backend/scripts/publish_store_pnl_estimates.py \
  --review-dir /private/review-directory --receipt /private/verified.json

backend/venv/bin/python backend/scripts/publish_store_pnl_estimates.py \
  --review-dir /private/review-directory --stage \
  --approval-reference 'Owner approval and reviewed lot reference' \
  --receipt /private/staged.json

backend/venv/bin/python backend/scripts/publish_store_pnl_estimates.py \
  --publish GENERATION_UUID --expected-manifest-sha SHA256 \
  --expected-revision REVISION \
  --approval-reference 'Owner approval and reviewed lot reference' \
  --receipt /private/published.json

backend/venv/bin/python backend/scripts/publish_store_pnl_estimates.py \
  --rollback GENERATION_UUID --expected-manifest-sha SHA256 \
  --expected-revision CURRENT_REVISION \
  --approval-reference 'Authorized rollback and incident reference' \
  --receipt /private/rollback.json
```

The verifier checks the saved file hashes, current input equivalence, unchanged
published preimage and selected HR sources. It recomputes the candidate with
the current estimator and requires identical values before staging. Publication
uses the stored generation; it does not reread candidate files. Receipts record
before/after Finance actual and Target business hashes. An unexpected difference
requires inspection for a concurrent protected-data change, not blind replay.

The P&L sales comparator uses period-effective VAT directly. The shared runtime
VAT flag and Target conversion are not changed. The existing Finance promotion
contract and its separate approval requirements continue to apply.
