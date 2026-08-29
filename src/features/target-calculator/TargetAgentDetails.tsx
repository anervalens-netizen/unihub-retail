import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Store, Users, X } from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { fetchTargetStoreDetail, type TargetStoreDetail } from './api';
import { getApiErrorMessage } from '../../api/client';
import { formatCurrency, formatPercent } from '../../lib/formatters';
import { formatOptionalCurrency, monthLabel } from './model';

type StoreChartMode = 'sales' | 'bon2acc' | 'focus';

const STORE_CHART_MODES: Array<{ mode: StoreChartMode; label: string }> = [
  { mode: 'sales', label: 'Vanzari' },
  { mode: 'bon2acc', label: 'Bon2Acc' },
  { mode: 'focus', label: 'Focus/Acc' },
];

function SummaryCard({ label, value, detail, emphasis, grouped = false }: {
  label: string;
  value: string;
  detail?: string;
  emphasis?: 'good' | 'warning' | 'attention';
  grouped?: boolean;
}) {
  const color = emphasis === 'good'
    ? 'text-emerald-600 dark:text-emerald-400'
    : emphasis === 'warning'
      ? 'text-amber-600 dark:text-amber-400'
      : emphasis === 'attention'
        ? 'text-amber-700 dark:text-amber-300'
      : 'text-slate-900 dark:text-slate-100';
  const surface = grouped
    ? 'min-w-0 p-3'
    : emphasis === 'attention'
    ? 'rounded-2xl border border-amber-300 bg-amber-50/80 p-4 min-w-0 dark:border-amber-700 dark:bg-amber-950/20'
    : 'glass rounded-2xl p-4 min-w-0';
  return (
    <div className={surface}>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 break-words font-bold tabular-nums ${grouped ? 'text-base sm:text-lg xl:text-xl' : 'text-xl'} ${color}`}>{value}</p>
      {detail && <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{detail}</p>}
    </div>
  );
}

function TargetStoreChart({ detail, mode, onModeChange }: { detail: TargetStoreDetail; mode: StoreChartMode; onModeChange: (mode: StoreChartMode) => void }) {
  const best = detail.best_month;
  const percentageMetric = mode === 'bon2acc' ? 'bon2acc_pct' : 'focus_pct';
  const percentageLabel = mode === 'bon2acc' ? 'Bon2Acc' : 'Focus/Acc';
  const chartTitle = mode === 'sales' ? 'Vanzari vs target - 16 luni' : `${percentageLabel} - 16 luni`;
  return (
    <div className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div><h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{chartTitle}</h3><p className="text-xs text-slate-500">{mode === 'sales' ? `Media: ${formatCurrency(detail.avg_sales_16m)}${best ? ` · Varf: ${monthLabel(best.month)} (${formatCurrency(best.total_sales)})` : ''}` : 'Evolutie procentuala pe aceleasi 16 luni'}</p></div>
        <div className="flex flex-wrap gap-1.5">{STORE_CHART_MODES.map((item) => <button key={item.mode} type="button" onClick={() => onModeChange(item.mode)} className={`rounded-full px-3 py-1.5 text-[11px] font-semibold transition-colors ${mode === item.mode ? 'bg-indigo-600 text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'}`}>{item.label}</button>)}</div>
      </div>
      <div className="h-64"><ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
        <ComposedChart data={detail.history} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.16)" /><XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={monthLabel} />
          {mode === 'sales' ? <><YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} /><Tooltip formatter={(value: unknown) => formatCurrency(Number(value))} /><Legend /><Bar dataKey="total_sales" name="Vanzari" fill="#4f46e5" radius={[4, 4, 0, 0]} /><Line type="monotone" dataKey="target_value" name="Target" stroke="#f59e0b" strokeWidth={2} dot={false} /></> : <><YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={(value) => `${Number(value).toFixed(0)}%`} /><Tooltip formatter={(value: unknown) => formatPercent(Number(value))} /><Legend /><Line type="monotone" dataKey={percentageMetric} name={percentageLabel} stroke={mode === 'bon2acc' ? '#10b981' : '#8b5cf6'} strokeWidth={2.5} dot={{ r: 3 }} connectNulls /></>}
        </ComposedChart>
      </ResponsiveContainer></div>
    </div>
  );
}

function TargetStoreStats({ detail }: { detail: TargetStoreDetail }) {
  const latest = detail.latest;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800"><h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">KPI ultima luna</h3><div className="mt-3 space-y-2 text-xs">
        <KpiRow label="Cantitate" value={(latest?.total_quantity ?? 0).toLocaleString('ro-RO')} /><KpiRow label="Cartele" value={(latest?.cartele_qty ?? 0).toLocaleString('ro-RO')} /><KpiRow label="Bon2Acc" value={formatPercent(latest?.bon2acc_pct ?? null)} /><KpiRow label="Focus/Acc" value={formatPercent(latest?.focus_pct ?? null)} /><KpiRow label="Zile cu vanzari" value={`${latest?.working_days ?? 0}`} /><KpiRow label="Target calculat" value={formatCurrency(detail.proposed_target)} /><KpiRow label="Final manager" value={formatOptionalCurrency(detail.final_target)} />
      </div></div>
      <div className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800"><h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100"><Users size={15} /> Pondere agenti</h3><div className="mt-3 space-y-3">
        {detail.agents.length === 0 && <p className="text-xs text-slate-500">Nu exista agenti activi in luna cohortei.</p>}
        {detail.agents.slice(0, 8).map((agent) => <div key={agent.agent}><div className="mb-1 flex items-center justify-between gap-2 text-xs"><span className="font-medium text-slate-700 dark:text-slate-200">{agent.agent}</span><span className="font-semibold text-indigo-600 dark:text-indigo-300">{formatPercent(agent.sales_share_pct)}</span></div><progress className="target-agent-share" max={100} value={Math.min(Math.max(agent.sales_share_pct, 0), 100)}>{formatPercent(agent.sales_share_pct)}</progress><div className="mt-1 flex justify-between text-[10px] text-slate-400"><span>{formatCurrency(agent.total_sales)}</span><span>{agent.active_months_16}/16 luni active</span></div></div>)}
      </div></div>
    </div>
  );
}

export function TargetAgentDetails({ scenarioId, siteCode, onClose }: {
  scenarioId: number;
  siteCode: string | null;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<TargetStoreDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chartMode, setChartMode] = useState<StoreChartMode>('sales');
  const overlayRef = useRef<HTMLDivElement>(null);

  // Synchronous request-identity reset. Runs before browser paint so that
  // when scenarioId or siteCode change the previous store's detail /
  // error / loading is cleared in the same commit as the new selection,
  // preventing a frame that paints the old Target data under the new
  // identity.
  useLayoutEffect(() => {
    if (!siteCode) return;

    setChartMode('sales');
    setDetail(null);
    setLoading(true);
    setError(null);
  }, [scenarioId, siteCode]);

  // Async fetch lifecycle with per-request latest-request-wins guard.
  useEffect(() => {
    if (!siteCode) return;

    // `active` is closed-over by each fulfillment handler; the cleanup
    // callback flips it to false whenever scenarioId/siteCode changes or
    // the component unmounts, making any in-flight completion a no-op.
    let active = true;

    void fetchTargetStoreDetail(scenarioId, siteCode)
      .then((nextDetail) => {
        if (!active) return;
        setDetail(nextDetail);
      })
      .catch((err) => {
        if (!active) return;
        console.error(err);
        setError(getApiErrorMessage(err, 'Nu am putut incarca detaliile locatiei.'));
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [scenarioId, siteCode]);

  if (!siteCode) return null;

  const latest = detail?.latest;
  return (
    <div
      ref={overlayRef}
      onClick={(event) => {
        if (event.target === overlayRef.current) onClose();
      }}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"
    >
      <div className="animate-slide-in-right flex h-full w-full flex-col bg-white shadow-2xl dark:bg-slate-950 sm:max-w-2xl">
        <div className="flex items-start justify-between border-b border-slate-200 px-4 py-4 dark:border-slate-800 sm:px-6">
          <div>
            <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-indigo-500">
              <Store size={14} /> Detalii locatie
            </p>
            <h2 className="mt-1 text-lg font-bold text-slate-900 dark:text-slate-100">
              {detail?.locatie ?? siteCode}
            </h2>
            {detail && (
              <p className="text-xs text-slate-500">
                {detail.site_code} · {detail.firma} · {detail.regional}
              </p>
            )}
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {loading && <div className="py-12 text-center text-sm text-slate-500">Se incarca detaliile...</div>}
          {error && <div className="rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
          {!loading && detail && (
            <div className="space-y-4 pb-8">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <SummaryCard label="Vanzari ultima luna" value={formatCurrency(latest?.total_sales ?? 0)} detail={detail.cohort_month} />
                <SummaryCard label="% target" value={formatPercent(latest?.target_pct ?? null)} detail={formatCurrency(latest?.target_value ?? 0)} />
                <SummaryCard label="Bon mediu" value={latest?.avg_receipt == null ? '-' : formatCurrency(latest.avg_receipt)} detail={`${latest?.receipt_count ?? 0} bonuri`} />
                <SummaryCard label="Agenti activi" value={`${latest?.active_agents ?? 0}`} detail={`${detail.agents.length} in lista`} />
              </div>

              <TargetStoreChart detail={detail} mode={chartMode} onModeChange={setChartMode} />
              <TargetStoreStats detail={detail} />
            </div>
          )}
        </div>
      </div>

    </div>
  );
}

function KpiRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-900/60">
      <span className="text-slate-500">{label}</span>
      <span className="font-semibold tabular-nums text-slate-800 dark:text-slate-100">{value}</span>
    </div>
  );
}

