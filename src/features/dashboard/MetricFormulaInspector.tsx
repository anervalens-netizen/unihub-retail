import type { AppFilters } from '../../lib/appFilters';
import {
  getMetricDefinition,
  type MetricDefinition,
  type MetricId,
} from '../../lib/metricCatalog';

export interface MetricFormulaInspectorContext {
  period: string;
  filters: AppFilters;
  statusLabel: string;
  lastSaleDate?: string | null;
  importedDayOfMonth?: number | null;
  daysInMonth?: number | null;
}

const FILTER_SENTINELS = new Set(
  [
    '',
    'Toate',
    'Toti',
    'Toți',
    'ToÈ›I',
    'ToÃˆâ€ºI',
  ].map((value) => value.toLocaleLowerCase('ro-RO')),
);

function normalizeFilterValue(value: string): string | null {
  const cleaned = value.trim();
  return FILTER_SENTINELS.has(cleaned.toLocaleLowerCase('ro-RO')) ? null : cleaned;
}

function normalizeFilterValues(values: readonly string[]): string[] {
  const seen = new Set<string>();
  const normalized: string[] = [];
  for (const rawValue of values) {
    const value = normalizeFilterValue(rawValue);
    if (value === null || seen.has(value)) continue;
    seen.add(value);
    normalized.push(value);
  }
  return normalized;
}

function displayValue(metric: MetricDefinition, value: number | null): string {
  if (value === null || Number.isNaN(value)) return 'Indisponibil';
  if (metric.unit === 'percent') return `${Number(value).toFixed(metric.precision)}%`;
  if (metric.unit === 'RON') {
    return new Intl.NumberFormat('ro-RO', {
      style: 'currency',
      currency: 'RON',
      minimumFractionDigits: metric.precision,
      maximumFractionDigits: metric.precision,
    }).format(value);
  }
  return new Intl.NumberFormat('ro-RO', {
    maximumFractionDigits: metric.precision,
  }).format(value);
}

function filterContext(filters: AppFilters) {
  const storeScope = normalizeFilterValues(filters.magazin);
  const agentScope = normalizeFilterValues(filters.agent);
  const firma = normalizeFilterValue(filters.firma);
  const manager = normalizeFilterValue(filters.rm);
  const hasStoreScope = storeScope.length > 0;
  const overriddenByStore = 'Suprascris de Magazin';
  return [
    ['Firma', hasStoreScope ? overriddenByStore : firma ?? 'Toate firmele'],
    ['Manager', hasStoreScope ? overriddenByStore : manager ?? 'Toți managerii'],
    ['Magazin', hasStoreScope ? storeScope.join(', ') : 'Toate magazinele din scope'],
    ['Agent', agentScope.length > 0 ? agentScope.join(', ') : 'Toți agenții din scope'],
  ] as const;
}

export function MetricFormulaInspector({
  metricId,
  value,
  context,
}: {
  metricId: MetricId;
  value: number | null;
  context: MetricFormulaInspectorContext;
}) {
  const metric = getMetricDefinition(metricId);
  if (!metric) return null;

  const importCutoff = context.importedDayOfMonth == null
    ? 'Indisponibil în răspunsul curent'
    : context.daysInMonth == null
      ? `Ziua ${context.importedDayOfMonth}`
      : `Ziua ${context.importedDayOfMonth} din ${context.daysInMonth}`;

  return (
    <details
      data-testid={`formula-inspector-${metric.id}`}
      className="group mt-2 rounded-2xl border border-slate-200/70 bg-white/70 dark:border-slate-700/70 dark:bg-slate-900/30"
    >
      <summary
        aria-label={`Inspectează formula ${metric.name}`}
        className="cursor-pointer list-none px-3 py-2 text-xs font-bold text-slate-600 marker:hidden dark:text-slate-300"
      >
        <span className="flex items-center justify-between gap-2">
          Formula și context
          <span aria-hidden="true" className="text-slate-400 group-open:rotate-180">⌄</span>
        </span>
      </summary>
      <div className="space-y-3 border-t border-slate-200/70 px-3 py-3 text-xs dark:border-slate-700/70">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="font-bold text-slate-500">Valoare afișată</div>
            <div className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">{displayValue(metric, value)}</div>
          </div>
          <div>
            <div className="font-bold text-slate-500">Perioadă</div>
            <div className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">{context.period}</div>
          </div>
          <div>
            <div className="font-bold text-slate-500">Ultima zi de vânzare disponibilă</div>
            <div className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">{context.lastSaleDate ?? 'Indisponibilă'}</div>
          </div>
          <div>
            <div className="font-bold text-slate-500">Import lunar</div>
            <div className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">{importCutoff}</div>
          </div>
        </div>

        <div>
          <div className="font-bold text-slate-500">Filtre active</div>
          <dl className="mt-1 space-y-1 text-slate-700 dark:text-slate-200">
            {filterContext(context.filters).map(([label, filterValue]) => (
              <div key={label}>
                <dt className="font-bold text-slate-500">{label}</dt>
                <dd>{filterValue}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div>
          <div className="font-bold text-slate-500">Status context</div>
          <p className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">
            {context.statusLabel || 'Indisponibil în răspunsul curent'}
          </p>
        </div>

        <div>
          <div className="font-bold text-slate-500">Formula catalogului</div>
          <div className="mt-1 rounded-2xl bg-slate-950 px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-100">
            {metric.formula}
          </div>
        </div>

        <div>
          <div className="font-bold text-slate-500">Surse</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {metric.sources.map((source) => (
              <span key={source} className="rounded-lg bg-slate-100 px-2 py-1 font-mono text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {source}
              </span>
            ))}
          </div>
        </div>

        <div>
          <div className="font-bold text-slate-500">Freshness</div>
          <p className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">{metric.freshness}</p>
        </div>

        {metric.exclusions.length > 0 && (
          <div>
            <div className="font-bold text-slate-500">Exclude</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-700 dark:text-slate-200">
              {metric.exclusions.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}

        {metric.limitations.length > 0 && (
          <div>
            <div className="font-bold text-slate-500">Limitări cunoscute</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-700 dark:text-slate-200">
              {metric.limitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}

        <div className="text-xs font-semibold text-slate-500">
          Catalog KPI v{metric.version} · read-only · nu execută și nu modifică formula.
        </div>
      </div>
    </details>
  );
}
