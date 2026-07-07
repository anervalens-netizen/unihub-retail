import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Wallet, TrendingUp } from 'lucide-react';
import { fetchAsmSalary, type AsmSalaryBreakdown } from '../api/hr';
import { formatMonthLabel } from '../lib/dates';

const TODAY_MONTH = new Date().toISOString().slice(0, 7);

function ron(n: number): string {
  return `${n.toLocaleString('ro-RO', { maximumFractionDigits: 0 })} lei`;
}

function pct(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined) return '—';
  return `${n.toFixed(digits)}%`;
}

function pctColor(n: number | null | undefined): string {
  if (n === null || n === undefined) return 'text-slate-400';
  if (n >= 99) return 'text-green-600 dark:text-green-400';
  if (n >= 84) return 'text-amber-600 dark:text-amber-400';
  if (n >= 79) return 'text-orange-600 dark:text-orange-400';
  return 'text-red-600 dark:text-red-400';
}

interface Props {
  asm: string;
  defaultMonth: string;
}

export function AsmSalaryGrila({ asm, defaultMonth }: Props) {
  const [month, setMonth] = useState(defaultMonth || TODAY_MONTH);
  const [data, setData] = useState<AsmSalaryBreakdown | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchAsmSalary(asm, month));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Eroare la încărcarea grilei');
    } finally {
      setLoading(false);
    }
  }, [asm, month]);

  useEffect(() => { void load(); }, [load]);

  const isForecast = data?.is_forecast ?? false;

  return (
    <div className="rounded-2xl border border-indigo-200/70 dark:border-indigo-900/50 bg-white/60 dark:bg-slate-900/40 p-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Wallet size={14} className="text-indigo-500" />
          <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
            Grilă salarizare
          </h4>
          {data && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-medium ${
              isForecast
                ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-300'
                : 'bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-300'
            }`}>
              {isForecast ? 'previziune' : 'final'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="month"
            className="rounded-xl border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <button
            onClick={load}
            className="p-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-500"
            title="Reîncarcă"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {error && (
        <div className="text-xs text-red-500 py-3 text-center">{error}</div>
      )}

      {loading && !data && (
        <div className="text-xs text-slate-400 py-6 text-center">Se încarcă grila…</div>
      )}

      {data && (
        <div className="space-y-3">
          {isForecast && (
            <p className="text-[10px] text-slate-400 leading-snug">
              Previziune la final de lună (factor {data.forecast_factor}×). Comisioanele sunt calculate
              pe procentul prognozat, nu pe realizatul la zi. La încheierea lunii se va folosi valoarea finală.
            </p>
          )}

          {/* Total hero */}
          <div className="rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-600 text-white px-3 py-2.5 flex items-center justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-wide opacity-80">
                {isForecast ? 'Salariu estimat' : 'Salariu final'} · {formatMonthLabel(data.month, { year: 'short' })}
              </div>
              <div className="text-xl font-bold tabular-nums">{ron(data.total_salary)}</div>
            </div>
            <div className="text-right text-[10px] opacity-80 leading-tight">
              <div>Fix {ron(data.fixed_salary)}</div>
              <div>+ comisioane {ron(data.total_salary - data.fixed_salary)}</div>
            </div>
          </div>

          {/* Component breakdown */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            <ComponentCard
              label="Comision zonă"
              hint={pct(data.zone.pct_used)}
              hintClass={pctColor(data.zone.pct_used)}
              value={ron(data.zone.commission)}
            />
            <ComponentCard
              label="Comision insule"
              hint={`${data.islands.length} insule`}
              value={ron(data.islands_commission)}
            />
            <ComponentCard
              label="Comision omogenitate"
              hint={`${data.homogeneity.qualifying_count}/${data.homogeneity.islands_count} ≥99%`}
              hintClass={data.homogeneity.eligible ? 'text-green-600 dark:text-green-400' : 'text-slate-400'}
              value={ron(data.homogeneity.commission)}
              eligible={data.homogeneity.eligible}
            />
            <ComponentCard
              label="Comision Acc Focus"
              hint={pct(data.acc_focus.pct)}
              hintClass={pctColor(data.acc_focus.pct)}
              value={ron(data.acc_focus.commission)}
            />
            <ComponentCard
              label="Salariu fix"
              value={ron(data.fixed_salary)}
            />
            <ComponentCard
              label="Total"
              value={ron(data.total_salary)}
              highlight
            />
          </div>

          {/* Islands table */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <h5 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1">
                <TrendingUp size={11} className="opacity-60" />
                Insule / locații
              </h5>
              <span className="text-[10px] text-slate-400">
                prag omogenitate: ≥{data.homogeneity.min_pct}% la peste 50% din insule
              </span>
            </div>
            <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500">
                  <tr>
                    <th className="text-left font-medium px-2 py-1.5">Locație</th>
                    <th className="text-left font-medium px-2 py-1.5">Firmă</th>
                    <th className="text-right font-medium px-2 py-1.5">Target</th>
                    <th className="text-right font-medium px-2 py-1.5">{isForecast ? 'Vânzări prog.' : 'Vânzări'}</th>
                    <th className="text-right font-medium px-2 py-1.5">% Target</th>
                    <th className="text-right font-medium px-2 py-1.5">Comision</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {data.islands.map((i) => {
                    const qualifies = i.pct_used !== null && i.pct_used >= data.homogeneity.min_pct;
                    return (
                      <tr key={i.site_code} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                        <td className="px-2 py-1.5 text-slate-700 dark:text-slate-200">
                          <div className="font-medium truncate max-w-[180px]">{i.locatie}</div>
                          <div className="text-[10px] text-slate-400">{i.site_code}</div>
                        </td>
                        <td className="px-2 py-1.5 text-slate-500">{i.firma}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums text-slate-500">{ron(i.total_target)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums text-slate-600 dark:text-slate-300">
                          {isForecast ? ron(i.forecast_sales) : ron(i.total_sales)}
                        </td>
                        <td className={`px-2 py-1.5 text-right tabular-nums font-semibold ${pctColor(i.pct_used)}`}>
                          {isForecast ? (
                            <span>
                              {pct(i.pct_used)}
                              <span className="block text-[9px] font-normal text-slate-400">realizat {pct(i.target_pct)}</span>
                            </span>
                          ) : pct(i.pct_used)}
                          {qualifies && (
                            <span className="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-green-500 align-middle" title="Califică omogenitate" />
                          )}
                        </td>
                        <td className="px-2 py-1.5 text-right tabular-nums font-semibold text-slate-700 dark:text-slate-200">
                          {ron(i.commission)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot className="bg-slate-50 dark:bg-slate-800/60">
                  <tr>
                    <td className="px-2 py-1.5 font-semibold text-slate-600 dark:text-slate-300" colSpan={5}>Total comisioane insule</td>
                    <td className="px-2 py-1.5 text-right tabular-nums font-bold text-slate-700 dark:text-slate-100">{ron(data.islands_commission)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ComponentCard({
  label,
  hint,
  hintClass,
  value,
  highlight,
  eligible,
}: {
  label: string;
  hint?: string;
  hintClass?: string;
  value: string;
  highlight?: boolean;
  eligible?: boolean;
}) {
  return (
    <div className={`rounded-xl border px-2.5 py-2 ${
      highlight
        ? 'border-indigo-300 dark:border-indigo-700 bg-indigo-50/60 dark:bg-indigo-950/30'
        : 'border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-900/30'
    }`}>
      <div className="flex items-center justify-between gap-1">
        <span className="text-[10px] uppercase tracking-wide text-slate-500">{label}</span>
        {hint && <span className={`text-[10px] tabular-nums ${hintClass ?? 'text-slate-400'}`}>{hint}</span>}
      </div>
      <div className={`text-sm font-bold tabular-nums ${
        highlight ? 'text-indigo-600 dark:text-indigo-300' : 'text-slate-700 dark:text-slate-200'
      }`}>
        {value}
        {eligible === false && label.includes('omogen') && (
          <span className="ml-1 text-[9px] font-normal text-slate-400">— neeligibil</span>
        )}
      </div>
    </div>
  );
}
