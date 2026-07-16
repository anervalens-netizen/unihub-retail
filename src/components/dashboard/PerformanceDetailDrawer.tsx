import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchSalaryAgentHistoryByRetailCode } from '../../api/salarii';
import type { SalaryAgentHistory } from '../../api/salarii';
import type { PerformanceDetailLevel, PerformanceDetailResponse } from '../../api/types';
import { formatAmount, formatCurrency, formatInt, formatPercent } from '../../lib/formatters';
import { SalaryAgentBarChart } from '../SalaryAgentBarChart';
import { SideDrawer } from '../common/SideDrawer';
import { TableHeaderCell } from '../common/TableHeader';
import { LoadingCard } from './DashboardWidgets';

export type PerformanceSelection = {
  level: PerformanceDetailLevel;
  key: string;
  site_code?: string;
};

type MonthlyPerformanceMetric = 'sales' | 'bon2acc' | 'focus' | 'returns';

export function PerformanceDetailDrawer({
  open,
  selection,
  detail,
  loading,
  error,
  canViewSalaries,
  onClose,
}: {
  open: boolean;
  selection: PerformanceSelection | null;
  detail: PerformanceDetailResponse | null;
  loading: boolean;
  error: string;
  canViewSalaries: boolean;
  onClose: () => void;
}) {
  const [monthlyMetric, setMonthlyMetric] = useState<MonthlyPerformanceMetric>('sales');
  const [salaryHistory, setSalaryHistory] = useState<SalaryAgentHistory | null>(null);
  const [salaryLoading, setSalaryLoading] = useState(false);
  const [salaryError, setSalaryError] = useState('');
  const historyData = useMemo(
    () => (detail?.history ?? []).map((point) => ({
      month: point.month,
      sales: Number(point.month === detail?.month ? (detail.summary.forecast_sales ?? point.total_sales ?? 0) : (point.total_sales ?? 0)),
      target: Number(point.total_target ?? 0),
      targetPct: point.month === detail?.month
        ? (detail.summary.forecast_target_progress_pct ?? point.target_progress_pct ?? null)
        : (point.target_progress_pct ?? null),
      bon2acc: point.proc_bon2acc ?? null,
      focus: point.prc_focus_acc_qty ?? null,
      returns: Number(point.return_receipt_count ?? 0),
    })),
    [detail],
  );
  const dailyData = useMemo(
    () => {
      if (!detail) return [];
      const valuesByDay = new Map(
        detail.daily.map((point) => [
          Number(point.sale_date.slice(8, 10)),
          {
            sales: Number(point.total_sales ?? 0),
            qty: point.total_quantity ?? 0,
            receipts: point.receipt_count ?? 0,
          },
        ]),
      );
      const daysInMonth = detail.summary.days_in_month ?? daysInMonthFromKey(detail.month);
      return Array.from({ length: daysInMonth }, (_, index) => {
        const day = index + 1;
        const value = valuesByDay.get(day);
        return {
          day,
          sales: value?.sales ?? null,
          qty: value?.qty ?? null,
          receipts: value?.receipts ?? null,
        };
      });
    },
    [detail],
  );
  const selectedPeer = detail?.peer_rows.find((row) => row.is_selected) ?? null;
  const agentStoreShare = detail?.context_summary && detail.context_summary.total_sales > 0
    ? Number(detail.summary.total_sales) * 100 / Number(detail.context_summary.total_sales)
    : null;
  const monthlyMetricLabel = monthlyMetric === 'sales'
    ? 'Vanzare'
    : monthlyMetric === 'bon2acc'
      ? 'ProcBon2Acc'
      : monthlyMetric === 'focus'
        ? 'PrcFocus/AccQtty'
        : 'Retururi';
  const monthlyMetricColor = monthlyMetric === 'sales'
    ? '#4f46e5'
    : monthlyMetric === 'bon2acc'
      ? '#0f766e'
      : monthlyMetric === 'focus'
        ? '#db2777'
        : '#dc2626';
  const showMonthlyTargetLines = detail?.level !== 'agent' && monthlyMetric === 'sales';
  const isReturnsMetric = monthlyMetric === 'returns';

  useEffect(() => {
    if (!open || !canViewSalaries || detail?.level !== 'agent' || !selection?.site_code) {
      setSalaryHistory(null);
      setSalaryLoading(false);
      setSalaryError('');
      return undefined;
    }
    let cancelled = false;
    setSalaryLoading(true);
    setSalaryError('');
    setSalaryHistory(null);
    fetchSalaryAgentHistoryByRetailCode({
      agent_code: detail.key,
      site_code: selection.site_code,
    })
      .then((data) => {
        if (cancelled) return;
        setSalaryHistory(data);
      })
      .catch(() => {
        if (cancelled) return;
        setSalaryError('Salariile nu au putut fi incarcate.');
      })
      .finally(() => {
        if (!cancelled) setSalaryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canViewSalaries, detail?.key, detail?.level, open, selection?.site_code]);

  return (
    <SideDrawer
      open={open}
      onClose={onClose}
      title={detail ? `Performanta · ${detail.title}` : 'Performanta'}
      widthClassName="w-full max-w-5xl"
    >
      <div className="space-y-4 p-4">
        {loading && <LoadingCard label="Incarc detaliile de performanta..." />}
        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">
            {error}
          </div>
        )}
        {detail && (
          <>
            <div className="grid gap-3 lg:grid-cols-[220px_1fr]">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                <div className="text-xs font-bold uppercase text-slate-400">Scor performanta</div>
                <div className="mt-2 flex items-end gap-2">
                  <div className={`text-5xl font-black ${scoreToneClass(detail.score)}`}>{detail.score}</div>
                  <div className="pb-1 text-sm font-bold text-slate-600 dark:text-slate-300">{detail.score_label}</div>
                </div>
                <div className="mt-3 h-2 rounded-full bg-slate-100 dark:bg-slate-800">
                  <div className={`h-2 rounded-full ${scoreBarClass(detail.score)}`} style={{ width: `${detail.score}%` }} />
                </div>
                <div className="mt-3 grid grid-cols-3 gap-1 text-center">
                  <ScorePart label="Target" value={formatScorePoints(detail.score_breakdown.target_points)} />
                  <ScorePart label="Bon2Acc" value={formatScorePoints(detail.score_breakdown.bon2acc_points)} />
                  <ScorePart label="Focus" value={formatScorePoints(detail.score_breakdown.focus_points)} />
                </div>
                {selectedPeer && (
                  <div className="mt-3 text-xs font-semibold text-slate-500">
                    Rank {selectedPeer.rank}
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900 sm:p-4">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">{detail.title}</h3>
                  {detail.subtitle && <p className="text-xs text-slate-500">{detail.subtitle}</p>}
                </div>
                <p className="mt-2 text-xs font-semibold leading-relaxed text-slate-700 dark:text-slate-200 sm:mt-3 sm:text-sm">{detail.note}</p>
                <div className="mt-3 grid grid-cols-2 gap-1.5 sm:gap-2 lg:grid-cols-4">
                  <DetailMetric label="Vanzari" value={formatCurrency(detail.summary.total_sales)} />
                  <DetailMetric label="Target" value={formatPercent(detail.summary.target_progress_pct)} />
                  <DetailMetric label={detail.level === 'agent' ? 'Forecast 15 zile' : 'Forecast'} value={formatPercent(detail.summary.forecast_target_progress_pct)} />
                  <DetailMetric label="Medie zilnica" value={formatCurrency(detail.summary.daily_average ?? 0)} />
                  <DetailMetric label="Bon2Acc" value={formatPercent(detail.summary.proc_bon2acc)} />
                  <DetailMetric label="Focus" value={formatPercent(detail.summary.prc_focus_acc_qty)} />
                  <DetailMetric label="Bonuri" value={formatInt(detail.summary.total_receipts)} />
                  <DetailMetric label={detail.level === 'agent' ? 'Zile lucrate' : 'Zile active'} value={formatInt(detail.summary.working_days)} />
                </div>
                {detail.context_summary && (
                  <div className="mt-3 flex flex-wrap gap-x-1.5 gap-y-0.5 rounded-xl bg-indigo-50 px-3 py-2 text-[11px] font-semibold leading-tight text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-200 sm:text-xs">
                    <span>Magazin: {formatCurrency(detail.context_summary.total_sales)}</span>
                    <span className="hidden sm:inline">·</span>
                    <span>contributie agent {agentStoreShare !== null ? formatPercent(agentStoreShare) : '-'}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-bold">Evolutie lunara</h3>
                  <div className="inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-800">
                    {[
                      { key: 'sales', label: 'Vanzare' },
                      { key: 'bon2acc', label: 'ProcBon2Acc' },
                      { key: 'focus', label: 'PrcFocus/AccQtty' },
                      { key: 'returns', label: 'Retururi' },
                    ].map((option) => (
                      <button
                        key={option.key}
                        type="button"
                        onClick={() => setMonthlyMetric(option.key as MonthlyPerformanceMetric)}
                        className={`rounded-lg px-2 py-1 text-[11px] font-bold transition ${
                          monthlyMetric === option.key
                            ? option.key === 'returns'
                              ? 'bg-white text-rose-600 shadow-sm dark:bg-slate-950 dark:text-rose-400'
                              : 'bg-white text-indigo-700 shadow-sm dark:bg-slate-950 dark:text-indigo-300'
                            : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
                        }`}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={historyData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                      {isReturnsMetric ? (
                        <>
                          <YAxis yAxisId="returns" tick={{ fontSize: 10 }} tickFormatter={(value) => formatInt(Number(value))} width={48} allowDecimals={false} />
                          <Tooltip formatter={(value: number) => [formatInt(value), 'Retururi']} labelFormatter={(label) => `Luna ${label}`} />
                          <Bar yAxisId="returns" dataKey="returns" name="Retururi" fill={monthlyMetricColor} radius={[4, 4, 0, 0]} />
                        </>
                      ) : monthlyMetric === 'sales' ? (
                        <>
                          <YAxis yAxisId="sales" tick={{ fontSize: 10 }} tickFormatter={(value) => formatAmount(Number(value))} width={58} />
                          {showMonthlyTargetLines && (
                            <YAxis yAxisId="percent" orientation="right" tick={{ fontSize: 10 }} tickFormatter={(value) => `${value}%`} width={38} />
                          )}
                          <Tooltip formatter={(value: number, name: string) => [name.includes('%') ? formatPercent(value) : formatCurrency(value), name]} />
                          <Bar yAxisId="sales" dataKey="sales" name="Vanzari" fill={monthlyMetricColor} radius={[4, 4, 0, 0]} />
                          {showMonthlyTargetLines && (
                            <>
                              <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#f59e0b" strokeWidth={2} dot={false} />
                              <Line yAxisId="percent" type="monotone" dataKey="targetPct" name="Target %" stroke="#10b981" strokeWidth={2} dot={false} connectNulls />
                            </>
                          )}
                        </>
                      ) : (
                        <>
                          <YAxis yAxisId="percent" tick={{ fontSize: 10 }} tickFormatter={(value) => `${value}%`} width={48} />
                          <Tooltip formatter={(value: number) => [formatPercent(value), monthlyMetricLabel]} />
                          <Line yAxisId="percent" type="monotone" dataKey={monthlyMetric} name={monthlyMetricLabel} stroke={monthlyMetricColor} strokeWidth={3} dot={{ r: 3 }} connectNulls />
                        </>
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {detail.level === 'agent' && canViewSalaries && (
                <AgentSalarySummaryCard
                  history={salaryHistory}
                  loading={salaryLoading}
                  error={salaryError}
                />
              )}

              <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                <h3 className="mb-3 text-sm font-bold">Evolutie zilnica</h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={dailyData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="day" interval={0} tick={{ fontSize: 9 }} />
                      <YAxis tick={{ fontSize: 10 }} tickFormatter={(value) => formatAmount(Number(value))} width={58} />
                      <Tooltip formatter={(value: number) => formatCurrency(value)} labelFormatter={(label) => `Ziua ${label}`} />
                      <Line type="monotone" dataKey="sales" name="Vanzari" stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 2 }} activeDot={{ r: 4 }} connectNulls={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                <h3 className="mb-3 text-sm font-bold">Semnale</h3>
                <div className="grid gap-2 sm:grid-cols-2">
                  <SignalList title="Puncte bune" items={detail.strengths} empty="Fara semnale pozitive clare." tone="good" />
                  <SignalList title="De urmarit" items={detail.risks} empty="Fara risc major pe KPI." tone="risk" />
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                <h3 className="mb-3 text-sm font-bold">
                  {detail.level === 'agent' ? 'Colegi acelasi magazin' : detail.level === 'store' ? 'Magazine acelasi RM' : 'RM comparabili'}
                </h3>
                <div className="max-h-72 overflow-auto rounded-xl border border-slate-200 dark:border-slate-700">
                  <table className="min-w-full text-xs">
                    <thead className="bg-slate-50 text-[10px] uppercase text-slate-500 dark:bg-slate-800">
                      <tr>
                        <TableHeaderCell>Nume</TableHeaderCell>
                        <TableHeaderCell align="right">Vânzări</TableHeaderCell>
                        <TableHeaderCell align="right">%</TableHeaderCell>
                        <TableHeaderCell align="right">Loc</TableHeaderCell>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.peer_rows.map((row) => (
                        <tr key={`${row.rank}-${row.label}`} className={row.is_selected ? 'bg-indigo-50 font-bold text-indigo-800 dark:bg-indigo-950/30 dark:text-indigo-200' : 'border-t border-slate-100 dark:border-slate-800'}>
                          <td className="px-2 py-2">
                            <div className="max-w-44 truncate">{row.label}</div>
                            {row.sublabel && <div className="max-w-44 truncate text-[10px] text-slate-500">{row.sublabel}</div>}
                          </td>
                          <td className="px-2 py-2 text-right">{formatAmount(row.total_sales)}</td>
                          <td className="px-2 py-2 text-right">{formatPercent(row.target_progress_pct)}</td>
                          <td className="px-2 py-2 text-right">{row.rank}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </SideDrawer>
  );
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-slate-50 px-2.5 py-2 dark:bg-slate-800/70 sm:px-3">
      <div className="truncate text-[9px] font-bold uppercase text-slate-400 sm:text-[10px]">{label}</div>
      <div className="mt-1 truncate text-[13px] font-black text-slate-800 dark:text-slate-100 sm:text-sm">{value}</div>
    </div>
  );
}

function ScorePart({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-1.5 py-1.5 dark:bg-slate-800/70">
      <div className="truncate text-[9px] font-bold uppercase text-slate-400">{label}</div>
      <div className="mt-0.5 text-[11px] font-black tabular-nums text-slate-700 dark:text-slate-200">{value}</div>
    </div>
  );
}

function formatScorePoints(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return `${Number(value).toFixed(1)}p`;
}

function daysInMonthFromKey(monthKey: string) {
  const [year, month] = monthKey.split('-').map(Number);
  if (!year || !month) return 31;
  return new Date(year, month, 0).getDate();
}

function AgentSalarySummaryCard({
  history,
  loading,
  error,
}: {
  history: SalaryAgentHistory | null;
  loading: boolean;
  error: string;
}) {
  const link = history?.link ?? null;
  const hasRecords = !!history && history.records.length > 0;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold">Salarii</h3>
          {link?.salary_full_name ? (
            <p className="text-xs text-slate-500">
              {link.salary_full_name}
              {link.match_source === 'manual' ? ' · confirmat manual' : ' · mapare automata'}
            </p>
          ) : (
            <p className="text-xs text-slate-500">Mapare cod-agent spre nume salarial</p>
          )}
        </div>
      </div>

      {loading && (
        <div className="flex h-40 items-center justify-center text-xs font-semibold text-slate-500">
          Se incarca salariile...
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">
          {error}
        </div>
      )}

      {!loading && !error && !history?.link && (
        <div className="rounded-xl bg-slate-50 px-3 py-4 text-xs font-semibold text-slate-500 dark:bg-slate-800/70">
          Nu exista inca mapare salariala pentru codul acestui agent.
        </div>
      )}

      {!loading && !error && link?.match_status === 'unknown' && (
        <div className="rounded-xl bg-amber-50 px-3 py-4 text-xs font-semibold text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          Agent marcat ca necunoscut. Poate aparea automat dupa urmatorul import de salarii.
          {link.note ? <div className="mt-2 font-medium opacity-80">{link.note}</div> : null}
        </div>
      )}

      {!loading && !error && link?.match_status === 'confirmed' && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2">
            <DetailMetric label="Total" value={formatCurrency(history?.total ?? 0)} />
            <DetailMetric label="Luni" value={formatInt(history?.month_count ?? 0)} />
            <DetailMetric label="Medie" value={formatCurrency(history?.avg ?? 0)} />
          </div>
          {hasRecords ? (
            <SalaryAgentBarChart data={history.records} />
          ) : (
            <div className="rounded-xl bg-slate-50 px-3 py-4 text-xs font-semibold text-slate-500 dark:bg-slate-800/70">
              Numele este confirmat, dar nu exista inca randuri de salarii pentru el.
            </div>
          )}
          {history && history.month_count > 0 && (
            <div className="text-[11px] font-semibold text-slate-500">
              Media foloseste {history.avg_month_count}/{history.month_count} luni cu salariu de cel putin 2.000 RON.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SignalList({
  title,
  items,
  empty,
  tone,
}: {
  title: string;
  items: string[];
  empty: string;
  tone: 'good' | 'risk';
}) {
  return (
    <div>
      <div className="mb-2 text-xs font-bold text-slate-700 dark:text-slate-200">{title}</div>
      <div className="space-y-1">
        {(items.length ? items : [empty]).map((item) => (
          <div
            key={item}
            className={`rounded-lg px-2 py-1.5 text-xs font-semibold ${
              tone === 'good'
                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
                : 'bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300'
            }`}
          >
            {item}
          </div>
        ))}
      </div>
    </div>
  );
}

function scoreToneClass(score: number): string {
  if (score >= 85) return 'text-emerald-600';
  if (score >= 70) return 'text-indigo-600';
  if (score >= 55) return 'text-amber-600';
  return 'text-rose-600';
}

function scoreBarClass(score: number): string {
  if (score >= 85) return 'bg-emerald-500';
  if (score >= 70) return 'bg-indigo-500';
  if (score >= 55) return 'bg-amber-500';
  return 'bg-rose-500';
}
