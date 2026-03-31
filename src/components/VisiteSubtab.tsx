import React, { useEffect, useState } from 'react';
import { CheckCircle2, MapPin, XCircle } from 'lucide-react';
import { getVisitsReport, type VisitReportResponse, type VisitReportRow } from '../api/visitsReport';
import type { AppFilters } from './MainLayout';
import { cn } from '../lib/utils';

interface VisiteSubtabProps {
  currentMonth: string;
  filters: AppFilters;
}

function ComplianceDot({ pct }: { pct: number }) {
  const ok = pct >= 80;
  const mid = pct >= 50;
  return (
    <span
      className={cn(
        'inline-block h-2 w-2 rounded-full',
        ok ? 'bg-emerald-500' : mid ? 'bg-amber-400' : 'bg-red-400'
      )}
      title={`${pct}%`}
    />
  );
}

function PctBar({ value }: { value: number }) {
  const color = value >= 80 ? 'bg-emerald-500' : value >= 50 ? 'bg-amber-400' : 'bg-red-400';
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
      <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${value}%` }} />
    </div>
  );
}

const COMPLIANCE_KEYS: Array<{ key: keyof VisitReportRow; label: string }> = [
  { key: 'curatenie_pct', label: 'Cur' },
  { key: 'imagine_pct', label: 'Img' },
  { key: 'uniforma_pct', label: 'Unif' },
  { key: 'afise_pct', label: 'Afise' },
  { key: 'produse_promo_pct', label: 'Promo' },
];

export function VisiteSubtab({ currentMonth, filters }: VisiteSubtabProps) {
  const [data, setData] = useState<VisitReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getVisitsReport(currentMonth, filters)
      .then(setData)
      .catch((e: Error) => setError(e.message || 'Eroare la incarcare'))
      .finally(() => setLoading(false));
  }, [currentMonth, filters]);

  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center text-sm font-semibold text-slate-500">
        Se incarca vizitele...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-4 mt-4 rounded-2xl bg-red-50 p-4 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
        {error ?? 'Date indisponibile.'}
      </div>
    );
  }

  if (data.total_vizite === 0) {
    return (
      <div className="flex h-40 flex-col items-center justify-center gap-2 text-slate-400">
        <MapPin size={28} strokeWidth={1.5} />
        <p className="text-sm font-semibold">Nicio vizita inregistrata pentru {currentMonth}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 px-4">
      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-2">
        <div className="glass rounded-2xl p-3 text-center">
          <div className="text-2xl font-black text-indigo-600">{data.total_vizite}</div>
          <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Vizite
          </div>
        </div>
        <div className="glass rounded-2xl p-3 text-center">
          <div className="text-2xl font-black text-indigo-600">{data.magazine_unice}</div>
          <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Magazine
          </div>
        </div>
        <div className="glass rounded-2xl p-3 text-center">
          <div
            className={cn(
              'text-2xl font-black',
              data.avg_completion >= 80
                ? 'text-emerald-600'
                : data.avg_completion >= 50
                  ? 'text-amber-500'
                  : 'text-red-500'
            )}
          >
            {data.avg_completion.toFixed(0)}%
          </div>
          <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Completare
          </div>
        </div>
      </div>

      {/* Compliance summary */}
      <div className="glass rounded-2xl p-4">
        <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-500">
          Conformitate medie — {currentMonth}
        </h3>
        <div className="space-y-2">
          {COMPLIANCE_KEYS.map(({ key, label }) => {
            const allVals = data.rows.map((r) => r[key] as number);
            const avg =
              allVals.length > 0
                ? allVals.reduce((a, b) => a + b, 0) / allVals.length
                : 0;
            return (
              <div key={key} className="flex items-center gap-2">
                <span className="w-14 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                  {label}
                </span>
                <div className="flex-1">
                  <PctBar value={avg} />
                </div>
                <span className="w-10 text-right text-[11px] font-bold text-slate-700 dark:text-slate-200">
                  {avg.toFixed(0)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Per-store table */}
      <div className="glass overflow-hidden rounded-2xl">
        <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-700">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
            Detaliu pe magazin
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-700">
                <th className="px-3 py-2 text-left font-semibold text-slate-500">Magazin</th>
                <th className="px-3 py-2 text-left font-semibold text-slate-500">ASM</th>
                <th className="px-2 py-2 text-center font-semibold text-slate-500">Viz</th>
                <th className="px-2 py-2 text-center font-semibold text-slate-500">Comp%</th>
                {COMPLIANCE_KEYS.map(({ key, label }) => (
                  <th key={key} className="px-2 py-2 text-center font-semibold text-slate-500">
                    {label}
                  </th>
                ))}
                <th className="px-3 py-2 text-left font-semibold text-slate-500">Ultima vizita</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, idx) => (
                <tr
                  key={idx}
                  className="border-b border-slate-50 last:border-0 dark:border-slate-800"
                >
                  <td className="px-3 py-2 font-semibold text-slate-800 dark:text-slate-100">
                    {row.magazin || '—'}
                  </td>
                  <td className="px-3 py-2 text-slate-500">{row.asm || '—'}</td>
                  <td className="px-2 py-2 text-center font-bold text-indigo-600">
                    {row.nr_vizite}
                  </td>
                  <td className="px-2 py-2 text-center">
                    <span
                      className={cn(
                        'font-bold',
                        row.avg_completion >= 80
                          ? 'text-emerald-600'
                          : row.avg_completion >= 50
                            ? 'text-amber-500'
                            : 'text-red-500'
                      )}
                    >
                      {row.avg_completion.toFixed(0)}%
                    </span>
                  </td>
                  {COMPLIANCE_KEYS.map(({ key }) => (
                    <td key={key} className="px-2 py-2 text-center">
                      <ComplianceDot pct={row[key] as number} />
                    </td>
                  ))}
                  <td className="px-3 py-2 text-slate-400">{row.last_visit ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2 text-[10px] text-slate-400">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> ≥80%
          </span>
          <span className="mx-2 inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-amber-400" /> 50–79%
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-red-400" /> &lt;50%
          </span>
        </div>
      </div>
    </div>
  );
}
