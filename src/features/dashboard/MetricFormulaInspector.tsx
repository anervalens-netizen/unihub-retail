import type { AppFilters } from '../../lib/appFilters';
import { ALL_FIRMS, ALL_SCOPE } from '../../lib/filterValues';
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
  const hasStoreScope = filters.magazin.length > 0;
  const overriddenByStore = 'Suprascris de Magazin';
  return [
    ['Firma', hasStoreScope ? overriddenByStore : filters.firma === ALL_FIRMS ? 'Toate firmele' : filters.firma],
    ['Manager', hasStoreScope ? overriddenByStore : filters.rm === ALL_SCOPE ? 'Toți managerii' : filters.rm],
    ['Magazin', hasStoreScope ? filters.magazin.join(', ') : 'Toate magazinele din scope'],
    ['Agent', filters.agent.length > 0 ? filters.agent.join(', ') : 'Toți agenții din scope'],
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
      className="group mt-2 rounded-2xl border border-current/15 bg-white/60 text-slate-700 dark:bg-slate-950/25 dark:text-slate-200"
    >
      <summary
        aria-label={`Inspectează formula ${metric.name}`}
        className="cursor-pointer list-none px-3 py-2 text-[11px] font-bold marker:hidden"
      >
        <span className="flex items-center justify-between gap-2">
          Formula și context
          <span aria-hidden="true" className="text-current/60 group-open:rotate-180">⌄</span>
        </span>
      </summary>
      <div className="space-y-3 border-t border-current/10 px-3 py-3 text-[11px] leading-relaxed">
        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <div className="font-bold text-slate-500 dark:text-slate-400">Valoare afișată</div>
            <div className="mt-0.5 font-black tabular-nums">{displayValue(metric, value)}</div>
          </div>
          <div>
            <div className="font-bold text-slate-500 dark:text-slate-400">Perioadă</div>
            <div className="mt-0.5 font-semibold">{context.period}</div>
          </div>
          <div>
            <div className="font-bold text-slate-500 dark:text-slate-400">Ultima zi de vânzare disponibilă</div>
            <div className="mt-0.5 font-semibold">{context.lastSaleDate ?? 'Indisponibilă'}</div>
          </div>
          <div>
            <div className="font-bold text-slate-500 dark:text-slate-400">Import lunar</div>
            <div className="mt-0.5 font-semibold">{importCutoff}</div>
          </div>
        </div>

        <div>
          <div className="font-bold text-slate-500 dark:text-slate-400">Filtre active</div>
          <dl className="mt-1 grid gap-x-3 gap-y-1 sm:grid-cols-[auto_minmax(0,1fr)]">
            {filterContext(context.filters).map(([label, filterValue]) => (
              <div key={label} className="contents">
                <dt className="font-semibold text-slate-500 dark:text-slate-400">{label}</dt>
                <dd className="min-w-0 break-words">{filterValue}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div>
          <div className="font-bold text-slate-500 dark:text-slate-400">Status context</div>
          <p className="mt-0.5">{context.statusLabel || 'Indisponibil în răspunsul curent'}</p>
        </div>

        <div>
          <div className="font-bold text-slate-500 dark:text-slate-400">Formula catalogului</div>
          <div className="mt-1 rounded-xl bg-slate-950 px-2.5 py-2 font-mono text-[10px] text-slate-100">
            {metric.formula}
          </div>
        </div>

        <div>
          <div className="font-bold text-slate-500 dark:text-slate-400">Surse</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {metric.sources.map((source) => (
              <span key={source} className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[9px] dark:bg-slate-800">
                {source}
              </span>
            ))}
          </div>
        </div>

        <div>
          <div className="font-bold text-slate-500 dark:text-slate-400">Freshness</div>
          <p className="mt-0.5">{metric.freshness}</p>
        </div>

        {metric.exclusions.length > 0 && (
          <div>
            <div className="font-bold text-slate-500 dark:text-slate-400">Exclude</div>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {metric.exclusions.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}

        {metric.limitations.length > 0 && (
          <div>
            <div className="font-bold text-slate-500 dark:text-slate-400">Limitări cunoscute</div>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {metric.limitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}

        <div className="text-[10px] font-semibold text-slate-400">
          Catalog KPI v{metric.version} · read-only · nu execută și nu modifică formula.
        </div>
      </div>
    </details>
  );
}
