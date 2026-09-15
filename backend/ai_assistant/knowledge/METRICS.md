# Retail metric guide

This is the compact sandbox guide. The versioned application catalog in `src/lib/metricCatalog.ts` remains the detailed source of truth and should later be materialized into the sandbox automatically rather than duplicated by hand.

## Vânzări nete

- Metric id: `retail.sales.net_value`
- Unit: RON
- Formula: `SUM(total_sales)`
- Additive across the selected granularity.
- Main modern sources: `reporting_agent_day.total_sales`, `reporting_agent_month.total_sales`.
- Historical/year-history paths can also use `historical_monthly_sales.total_value` and a constrained legacy `historical_annual_sales.total_value` fallback.
- Returns with negative quantity reduce the net values.

## Target

- Metric id: `retail.target.value`
- Unit: RON
- Store/dashboard/RM/ASM: based on `store_targets.target_value`.
- Agent: use `agent_targets.target_value` when present.
- Do not invent an agent-target fallback. The application metric catalog documents a known implementation/business-rule distinction for fallback when an explicit agent target is absent.

## Realizare target

- Metric id: `retail.target.attainment_pct`
- Unit: percent
- Formula: `100 * vânzări_nete / target` when `target > 0`; otherwise null.
- Recalculate from aggregated numerator and denominator. Never sum child percentages and do not use a simple average unless explicitly requested as a different statistic.

## Accesorii nete

- Metric id: `retail.accessories.net_quantity`
- Unit: count
- Formula: `SUM(total_quantity)`
- Main modern sources: `reporting_agent_day.total_quantity`, `reporting_agent_month.total_quantity`.
- Returns reduce net quantity.

## Freshness

Modern reporting read models are rebuilt after a completed sales import. Targets are read independently from target tables and can therefore have different freshness from sales reporting. Multi-month UI calculations may recompute derived KPIs from server totals without changing source freshness.

## Organization semantics

Modern historical reporting can preserve organizational dimensions captured at import time. Some target/history/legacy sources resolve current organization from `stores`; a moved store can therefore create a legitimate current-vs-historical ownership asymmetry. Mention this when it materially affects an analysis.

## Detailed catalog

Before giving a high-stakes or formula-sensitive answer, consult the fully materialized metric catalog for:

- inclusions/exclusions;
- exact source fields;
- visual thresholds;
- freshness;
- current/historical organization semantics;
- limitations;
- implementation and verification references.

The runtime build should generate/copy that catalog into the sandbox knowledge bundle so the agent does not need to rediscover formulas from application code.