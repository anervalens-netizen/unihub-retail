# Hub Filter And Reporting Rules — 2026-05-07

## Context

Hub was adjusted after the migration to keep Retail reporting aligned with the old Platforma Mobiup behavior.

The main issues fixed:
- period comparison used full previous months instead of the same partial period
- cartela quantities could leak into visible KPI expectations
- distribution agents/stores named `TR ...` appeared in Retail totals
- ASM was still visible in Hub although the current management layer is RM-only
- selecting a store together with its current RM made historical months show zero when the store belonged to another RM in the past
- authentik iframe silent renew caused 401 loops because the provider denies framing

## Period Comparison

`Comparatie perioade` now compares:
- current selected month, from day 1 to the latest imported sale day when the month is partial
- the same day range in the previous month
- the same day range in the same month last year
- only the store cohort with Retail sales in the current selected month; a store
  without sales in that reference month is treated as closed for this card

The cohort is anchored to the current selected scope. For example, when the
selected month is `2026-05` and RM `Elena Minca` is selected, first resolve the
stores with sales in `2026-05` in Elena's current scope, then calculate previous
month and previous-year values for those same `site_code` values. Do not
reapply historical RM/firma ownership to the historical columns: stores may
have moved between managers or companies.

Implementation:
- cutoff logic: `backend/services/dashboard/queries.py::_fetch_period_comparison_cutoff_day`
- month/day helpers: `backend/services/dashboard/utils.py`
- response model: `backend/models.py::PeriodComparisonPoint`
- frontend render: `src/components/Dashboard.tsx`

The card shows delta blocks for:
- sales
- daily average
- receipts
- quantity

Each delta includes absolute value and percentage.

## Cartele

Retail KPI totals exclude `is_cartela = true`.

This applies to:
- total sales
- total quantity
- receipts
- daily average
- average receipt value
- focus percentages
- history and period comparison totals

The informational `Cartele` row is calculated separately from `sales_transactions`, with `is_cartela = true`, and must not be mixed back into Retail totals.

Relevant files:
- `backend/services/dashboard/queries.py`
- `backend/repositories/dashboard.py`
- `backend/models.py`
- `src/api/types.ts`
- `src/components/Dashboard.tsx`

## Distribution Stores (`TR ...`)

Distribution agents/stores are excluded from Retail reporting by location prefix:

```sql
stores.locatie NOT ILIKE 'TR %'
```

The central rule is in:
- `backend/services/filters.py::scoped_clauses`

It is also applied to:
- filter option repositories
- campaign clauses
- reporting rebuild logic

Do not remove this rule from dashboard queries. TR agents are analyzed in another application.

## Hub Filters

Hub no longer exposes ASM filtering or the ASM card. Current Hub hierarchy is:

```text
Firma -> RM -> Magazin -> Agent
```

Store and agent filters support multi-select in the frontend. Values are sent comma-separated and interpreted by SQL using:

```sql
= ANY(string_to_array($n::TEXT, ','))
```

Relevant frontend files:
- `src/components/MainLayout.tsx`
- `src/components/DesktopTopBar.tsx`
- `src/lib/filterQueries.ts`
- `src/components/Dashboard.tsx`
- `src/components/Campaigns.tsx`
- `src/components/Agents.tsx`

Relevant backend files:
- `backend/services/filters.py`
- `backend/services/dashboard/utils.py`
- `backend/services/dashboard_service.py`
- `backend/services/dashboard/queries.py`
- `backend/services/dashboard/specials_data.py`
- `backend/services/campaigns.py`

## Store Scope Dominates Parent Scope

When `site_code` is present, backend must ignore parent filters:
- `firma`
- `regional`
- `asm`

Reason: store ownership can change between months. Example:

```text
Current filter:
firma=MobiCell
regional=Elena Minca
site_code=CRELECTROP
```

`CRELECTROP` may have historical rows under a different RM. If the backend applies both `regional` and `site_code`, history and period comparison return zero. The correct behavior is to scope by `site_code` only, plus `agent` if selected.

The same rule applies to the automatically derived current-store cohort in
`Comparatie perioade`: once current RM/firma scope has selected the store codes,
the previous-month and previous-year columns use those store codes instead of
historical parent ownership.

Use `_build_scoped_params` or `base_filter_values`; do not manually append filter parameters unless you also implement the site-scope rule. Leaving skipped parent filters in the parameter list can cause asyncpg errors such as:

```text
IndeterminateDatatypeError: could not determine data type of parameter $n
```

## Auth And Frontend Warnings

OIDC must follow the UniHub persistent-session policy.

Current behavior:
- `automaticSilentRenew: true`
- scope includes `openid profile email offline_access`
- Authentik provider validity is `hours=8` for access tokens and `days=180` for refresh tokens
- app redirects to login only when the OIDC session cannot be renewed

Files:
- `src/auth/AuthContext.tsx`
- `src/api/client.ts`
- `src/App.tsx`

Other warning fixes:
- `index.html` includes `mobile-web-app-capable`
- Recharts `ResponsiveContainer` instances include minimum dimensions to avoid `width(-1)` / `height(-1)` warnings

## Verification

Relevant backend tests:

```bash
backend/venv/bin/python -m pytest \
  backend/tests/test_filters_extended.py \
  backend/tests/test_campaign_clauses.py \
  backend/tests/test_dashboard.py \
  backend/tests/test_dashboard_queries.py \
  backend/tests/test_dashboard_service.py \
  -q
```

Manual store-scope check used during implementation:

```text
month=2026-05
firma=MobiCell
regional=Elena Minca
site_code=CRELECTROP
```

Expected behavior:
- current month has current CRELECTROP totals
- history includes previous-month CRELECTROP totals even if previous rows belonged to another RM
- period comparison uses day range `01-06` for current, previous month and previous year when May 2026 is partial

Manual cohort check for the period-comparison fix:

```text
month=2026-05
regional=Elena Minca
cutoff_day=26
```

Expected behavior:
- the cohort is the `5` stores with Retail sales in `2026-05` under Elena's current scope
- previous month includes `170651.80` RON for those same stores
- previous year includes `173828.81` RON for those same stores, including stores assigned to a different RM in `2025-05`
