# Retail business conventions

## Organization

The commercial hierarchy commonly used by UniHub is:

`firmă -> regional/RM -> ASM -> magazin/site_code -> agent`

Use the exact terminology returned by the data. Do not silently reinterpret RM and ASM levels.

## Store identity

`site_code` is the stable technical identity used to join store-level Retail data. Store names/locations are display attributes and can change; do not use a location label as a substitute key when `site_code` is available.

## Current versus historical organization

Current views can resolve organizational ownership from the current `stores` state. Historical reporting can preserve organizational dimensions captured at import/reporting time. Therefore a store that moved between managers can legitimately appear under historical ownership in one source and current ownership in another.

When comparing historical periods, state clearly when the requested metric/source uses current organization versus stored historical organization. Do not “correct” that difference by guessing.

## Retail scope

Retail KPI reporting excludes cartela/card products from accessory KPIs and can report them separately. Distribution locations matching the Retail exclusion convention (`locatie LIKE 'TR %'`) are excluded from modern Retail reporting read models.

Returns are netted into value/quantity where the metric is defined as net sales/net quantity; return-receipt counts are tracked separately.

## Targets

Store targets and agent targets are separate concepts. If an agent has an explicit `agent_targets` value, use it. Some existing application paths have documented fallback semantics when agent targets are absent; consult the metric knowledge before using a fallback in an analysis.

## Analysis behavior

- Prefer exact database evidence over assumptions.
- Recompute percentages from numerators/denominators when aggregating; do not average child percentages unless the metric definition explicitly says to.
- Preserve the selected month/filter cohort unless the owner asks to broaden it.
- If a source is known to be unavailable, say so rather than manufacturing replacement data.
- For ad-hoc analysis, query freely through the dedicated read-only Retail connection and use Python/pandas when it reduces complexity or token use.