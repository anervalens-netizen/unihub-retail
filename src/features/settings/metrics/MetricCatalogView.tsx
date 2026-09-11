import { BookOpen, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import {
  METRIC_CATALOG,
  METRIC_CATALOG_VERSION,
  searchMetricCatalog,
  type MetricDefinition,
  type MetricThreshold,
} from '../../../lib/metricCatalog';

function unitLabel(metric: MetricDefinition): string {
  if (metric.unit === 'percent') return `% · ${metric.precision} zecimale`;
  if (metric.unit === 'count') return 'buc. · număr întreg';
  return `RON · ${metric.precision} zecimale`;
}

function thresholdLabel(threshold: MetricThreshold): string {
  const min = threshold.minInclusive;
  const max = threshold.maxExclusive;
  if (min === undefined && max !== undefined) return `< ${max}%`;
  if (min !== undefined && max === undefined) return `≥ ${min}%`;
  return `${min}% – < ${max}%`;
}

function MetricDetails({ metric }: { metric: MetricDefinition }) {
  return (
    <details className="group rounded-2xl border border-slate-200/70 bg-white/70 dark:border-slate-700/70 dark:bg-slate-900/30">
      <summary className="cursor-pointer list-none px-3 py-2 text-xs font-bold text-slate-600 marker:hidden dark:text-slate-300">
        <span className="flex items-center justify-between gap-2">
          Detalii tehnice
          <span aria-hidden="true" className="text-slate-400 group-open:rotate-180">⌄</span>
        </span>
      </summary>
      <div className="space-y-3 border-t border-slate-200/70 px-3 py-3 text-xs dark:border-slate-700/70">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="font-bold text-slate-500">Agregare</div>
            <p className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">{metric.aggregation}</p>
          </div>
          <div>
            <div className="font-bold text-slate-500">Freshness</div>
            <p className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">{metric.freshness}</p>
          </div>
          <div>
            <div className="font-bold text-slate-500">Organizare curentă</div>
            <p className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">{metric.organizationSemantics.current}</p>
          </div>
          <div>
            <div className="font-bold text-slate-500">Organizare istorică</div>
            <p className="mt-1 leading-relaxed text-slate-700 dark:text-slate-200">{metric.organizationSemantics.historical}</p>
          </div>
        </div>

        <div>
          <div className="font-bold text-slate-500">Include</div>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-700 dark:text-slate-200">
            {metric.inclusions.map((item) => <li key={item}>{item}</li>)}
          </ul>
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
            <div className="font-bold text-slate-500">Limitări</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-700 dark:text-slate-200">
              {metric.limitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}

        <div>
          <div className="font-bold text-slate-500">Implementare</div>
          <div className="mt-1 space-y-1 font-mono text-[11px] text-slate-600 dark:text-slate-300">
            {metric.implementationRefs.map((ref) => <div key={ref} className="break-all">{ref}</div>)}
          </div>
        </div>
        <div>
          <div className="font-bold text-slate-500">Verificare</div>
          <div className="mt-1 space-y-1 font-mono text-[11px] text-slate-600 dark:text-slate-300">
            {metric.verificationRefs.map((ref) => <div key={ref} className="break-all">{ref}</div>)}
          </div>
        </div>
      </div>
    </details>
  );
}

function MetricCard({ metric }: { metric: MetricDefinition }) {
  return (
    <article data-testid="metric-catalog-card" className="glass min-w-0 space-y-3 rounded-3xl p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-black text-slate-800 dark:text-slate-100">{metric.name}</h3>
          <div className="mt-0.5 break-all font-mono text-[10px] text-slate-400">{metric.id}</div>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {unitLabel(metric)}
        </span>
      </div>

      <p className="text-xs leading-relaxed text-slate-600 dark:text-slate-300">{metric.description}</p>

      <div className="rounded-2xl bg-slate-950 px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-100">
        {metric.formula}
      </div>

      <div className="flex flex-wrap gap-1.5" aria-label={`Granularități ${metric.name}`}>
        {metric.granularities.map((granularity) => (
          <span key={granularity} className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
            {granularity}
          </span>
        ))}
      </div>

      <div>
        <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Surse</div>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {metric.sources.map((source) => (
            <span key={source} className="rounded-lg bg-slate-100 px-2 py-1 font-mono text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {source}
            </span>
          ))}
        </div>
      </div>

      {metric.visualThresholds && (
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Praguri vizuale existente</div>
          <div className="mt-1 grid gap-1.5 sm:grid-cols-2 xl:grid-cols-4">
            {metric.visualThresholds.map((threshold) => (
              <div key={threshold.label} className="rounded-xl border border-slate-200/70 px-2.5 py-2 text-[11px] dark:border-slate-700/70">
                <div className="font-bold text-slate-700 dark:text-slate-200">{threshold.label}</div>
                <div className="mt-0.5 text-slate-500">{thresholdLabel(threshold)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <MetricDetails metric={metric} />
    </article>
  );
}

export function MetricCatalogView() {
  const [query, setQuery] = useState('');
  const metrics = useMemo(() => searchMetricCatalog(query), [query]);

  return (
    <section className="space-y-3" aria-labelledby="metric-catalog-title">
      <div className="glass rounded-3xl p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <BookOpen size={18} className="text-indigo-500" aria-hidden="true" />
              <h2 id="metric-catalog-title" className="text-base font-black">Catalog KPI</h2>
            </div>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-500">
              Definițiile read-only ale metricilor Retail critice. Catalogul explică formulele existente; nu le execută și nu le poate modifica.
            </p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-[11px] font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            v{METRIC_CATALOG_VERSION} · {METRIC_CATALOG.length} metrici
          </span>
        </div>
        <label className="relative mt-3 block max-w-xl">
          <span className="sr-only">Caută în Catalog KPI</span>
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Caută metrică, ID, formulă sau sursă"
            className="w-full rounded-2xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-xs text-slate-700 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          />
        </label>
      </div>

      <div aria-live="polite" className="text-xs font-semibold text-slate-500">
        {metrics.length} din {METRIC_CATALOG.length} metrici
      </div>

      {metrics.length > 0 ? (
        <div className="grid gap-3 xl:grid-cols-2">
          {metrics.map((metric) => <MetricCard key={metric.id} metric={metric} />)}
        </div>
      ) : (
        <div className="glass rounded-3xl p-6 text-center text-sm text-slate-500">
          Nicio metrică nu corespunde căutării.
        </div>
      )}
    </section>
  );
}
