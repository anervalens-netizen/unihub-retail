import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { shiftMonth } from '../../lib/dates';
import { formatCurrency } from '../../lib/formatters';
import { formatSignedPercent, monthLabel, percentTone } from './model';
import type { TargetRegionalViewRow, TargetScenarioViewProps, TargetSourceViewRow } from './TargetScenarioView';

function managerTargetStatus(proposed: number, finalValue: number) {
  const difference = finalValue - proposed;
  const increasePct = proposed > 0 ? (difference / proposed) * 100 : 0;
  if (difference < -0.01) return { label: 'Sub calculator', badgeClass: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300', valueClass: 'text-red-600 dark:text-red-400' };
  if (increasePct > 5) return { label: 'Peste +5%', badgeClass: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', valueClass: 'text-amber-600 dark:text-amber-400' };
  return { label: 'In limita', badgeClass: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', valueClass: 'text-emerald-600 dark:text-emerald-400' };
}

function ManagerMobileCard({ manager, targetMonth }: { manager: TargetRegionalViewRow; targetMonth: string }) {
  const difference = manager.final_total - manager.proposed_total;
  const status = managerTargetStatus(manager.proposed_total, manager.final_total);
  const currentMonth = monthLabel(manager.current_month ?? shiftMonth(targetMonth, -1));
  const lastYearLabel = manager.last_year_base_month && manager.last_year_target_month ? `${monthLabel(manager.last_year_target_month)} vs ${monthLabel(manager.last_year_base_month)}` : 'Anul trecut';
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/60">
      <div className="flex items-start justify-between gap-3"><div><p className="font-semibold text-slate-800 dark:text-slate-100">{manager.regional}</p><p className="text-[11px] text-slate-400">{manager.store_count} magazine</p></div><span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${status.badgeClass}`}>{status.label}</span></div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <div className="rounded-lg bg-indigo-50 p-2 dark:bg-indigo-900/20"><p className="uppercase tracking-wide text-indigo-400">Calculator</p><p className="mt-1 font-semibold tabular-nums text-indigo-700 dark:text-indigo-300">{formatCurrency(manager.proposed_total)}</p></div>
        <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800"><p className="uppercase tracking-wide text-slate-400">Final</p><p className={`mt-1 font-semibold tabular-nums ${status.valueClass}`}>{formatCurrency(manager.final_total)}</p></div>
        <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800"><p className="uppercase tracking-wide text-slate-400">Diferenta</p><p className={`mt-1 font-semibold tabular-nums ${status.valueClass}`}>{difference > 0 ? '+' : ''}{formatCurrency(difference)}</p></div>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded-lg bg-emerald-50 p-2 dark:bg-emerald-900/20"><p className="uppercase tracking-wide text-emerald-500">Propus vs {currentMonth}</p><p className={`mt-1 font-semibold tabular-nums ${percentTone(manager.proposed_growth_vs_current_pct)}`}>{formatSignedPercent(manager.proposed_growth_vs_current_pct)}</p><p className="mt-1 text-[10px] text-slate-400">{formatCurrency(manager.current_forecast_total)}</p></div>
        <div className="rounded-lg bg-sky-50 p-2 dark:bg-sky-900/20"><p className="uppercase tracking-wide text-sky-500">{lastYearLabel}</p><p className={`mt-1 font-semibold tabular-nums ${percentTone(manager.last_year_growth_pct)}`}>{formatSignedPercent(manager.last_year_growth_pct)}</p><p className="mt-1 text-[10px] text-slate-400">{formatCurrency(manager.last_year_base_total)} {'->'} {formatCurrency(manager.last_year_target_total)}</p></div>
      </div>
    </div>
  );
}

function ManagerDesktopRow({ manager, targetMonth }: { manager: TargetRegionalViewRow; targetMonth: string }) {
  const difference = manager.final_total - manager.proposed_total;
  const status = managerTargetStatus(manager.proposed_total, manager.final_total);
  const currentMonth = monthLabel(manager.current_month ?? shiftMonth(targetMonth, -1));
  const lastYearLabel = manager.last_year_base_month && manager.last_year_target_month ? `${monthLabel(manager.last_year_target_month)} / ${monthLabel(manager.last_year_base_month)}` : 'LY';
  return (
    <div className="grid grid-cols-[minmax(130px,1fr)_115px_115px_115px_115px_100px_110px] items-center px-3 py-3 text-xs">
      <div><p className="font-semibold text-slate-700 dark:text-slate-200">{manager.regional}</p><p className="text-[10px] text-slate-400">{manager.store_count} magazine</p></div>
      <span className="text-right font-medium tabular-nums text-indigo-600 dark:text-indigo-300">{formatCurrency(manager.proposed_total)}</span>
      <span className="text-right tabular-nums"><span className={`block font-semibold ${percentTone(manager.proposed_growth_vs_current_pct)}`}>{formatSignedPercent(manager.proposed_growth_vs_current_pct)}</span><span className="block text-[10px] text-slate-400">{currentMonth}</span></span>
      <span className="text-right tabular-nums"><span className={`block font-semibold ${percentTone(manager.last_year_growth_pct)}`}>{formatSignedPercent(manager.last_year_growth_pct)}</span><span className="block text-[10px] text-slate-400">{lastYearLabel}</span></span>
      <span className={`text-right font-semibold tabular-nums ${status.valueClass}`}>{formatCurrency(manager.final_total)}</span><span className={`text-right font-semibold tabular-nums ${status.valueClass}`}>{difference > 0 ? '+' : ''}{formatCurrency(difference)}</span><span className={`ml-auto rounded-full px-2 py-1 text-[10px] font-semibold ${status.badgeClass}`}>{status.label}</span>
    </div>
  );
}

function RegionalTargets({ rows, targetMonth }: { rows: TargetRegionalViewRow[]; targetMonth: string }) {
  return (
    <div className="glass rounded-2xl p-4">
      <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Calculator si Final manager</h3><p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">Rosu = sub calculator · Verde = egal sau pana la +5% · Galben = peste +5%</p>
      <div className="mt-3 space-y-2 md:hidden">{rows.map((manager) => <ManagerMobileCard key={manager.regional} manager={manager} targetMonth={targetMonth} />)}</div>
      <div className="mt-3 hidden overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700 md:block"><div className="min-w-[820px]">
        <div className="grid grid-cols-[minmax(130px,1fr)_115px_115px_115px_115px_100px_110px] bg-slate-50 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:bg-slate-800"><span>Manager</span><span className="text-right">Calculator</span><span className="text-right">Vs luna curenta</span><span className="text-right">LY target/baza</span><span className="text-right">Final manager</span><span className="text-right">Diferenta</span><span className="text-right">Status</span></div>
        <div className="divide-y divide-slate-100 dark:divide-slate-800">{rows.map((manager) => <ManagerDesktopRow key={manager.regional} manager={manager} targetMonth={targetMonth} />)}</div>
      </div></div>
    </div>
  );
}

function HistoricalPeriodCard({ period }: { period: TargetSourceViewRow }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/60">
      <div className="flex items-center justify-between gap-2"><p className="font-semibold text-slate-800 dark:text-slate-100">{period.month}</p>{period.isForecast && <span className="rounded-full bg-sky-100 px-2 py-1 text-[10px] font-semibold text-sky-700 dark:bg-sky-900/30 dark:text-sky-300">Forecast</span>}</div>
      <div className={`mt-3 grid gap-2 text-[11px] ${period.showTarget ? 'grid-cols-2' : 'grid-cols-1'}`}>
        {period.showTarget && <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800"><p className="uppercase tracking-wide text-slate-400">Target istoric</p><p className="mt-1 font-semibold tabular-nums text-slate-700 dark:text-slate-200">{formatCurrency(period.target)}</p></div>}
        <div className="rounded-lg bg-sky-50 p-2 dark:bg-sky-900/20"><p className="uppercase tracking-wide text-sky-500">{period.isForecast ? 'Forecast folosit' : 'Realizat'}</p><p className="mt-1 font-semibold tabular-nums text-sky-700 dark:text-sky-300">{formatCurrency(period.realized)}</p>{period.isForecast && <p className="mt-1 text-[10px] text-slate-400">Importat: {formatCurrency(period.actualRealized)}</p>}</div>
      </div>
    </div>
  );
}

function HistoricalBase({ rows, isDesktop, regionalFilter }: { rows: TargetSourceViewRow[]; isDesktop: boolean; regionalFilter: string }) {
  return (
    <div className="glass rounded-2xl p-4">
      <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Baza istorica {regionalFilter === 'all' ? '' : `- ${regionalFilter}`}</h3>
      <div className="mt-3 space-y-2 md:hidden">{rows.map((period) => <HistoricalPeriodCard key={period.month} period={period} />)}</div>
      {isDesktop && <div className="mt-3 h-64"><ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}><BarChart data={rows} margin={{ top: 4, right: 4, left: 4, bottom: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.15)" /><XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 10 }} /><YAxis tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} tick={{ fill: '#94a3b8', fontSize: 10 }} /><Tooltip formatter={(value: unknown) => formatCurrency(Number(value))} /><Legend />{rows.some((period) => period.showTarget) && <Bar dataKey="target" name="Target istoric" fill="#cbd5e1" radius={[4, 4, 0, 0]} />}<Bar dataKey="realized" name="Realizat / Forecast folosit" fill="#0ea5e9" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>}
    </div>
  );
}

export function TargetRegionalOverview({ model }: { model: TargetScenarioViewProps }) {
  const { regionalChart, sourceChart, scenario, isDesktop, regionalFilter } = model;
  if (!scenario) return null;
  return <div className="grid gap-4 xl:grid-cols-2"><RegionalTargets rows={regionalChart} targetMonth={scenario.target_month} /><HistoricalBase rows={sourceChart} isDesktop={isDesktop} regionalFilter={regionalFilter} /></div>;
}
