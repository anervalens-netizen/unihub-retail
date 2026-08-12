import type { ReactNode } from 'react';
import { Activity, Award, RefreshCw, TrendingUp, UserCheck, UserMinus, UserPlus, Users } from 'lucide-react';
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, type TooltipContentProps, XAxis, YAxis } from 'recharts';

import type { AgentMovementPoint } from '../../api/agents';
import type { AgentsTeamMovementViewProps } from './agentsOverviewTypes';

function CustomTooltip({ active, payload, label }: TooltipContentProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as AgentMovementPoint | undefined;
  return <div className="rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur-md dark:border-slate-700 dark:bg-slate-900/95">
    <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{label}</p>
    {point?.is_baseline && <p className="mb-2 max-w-56 text-[11px] font-medium leading-snug text-slate-500">Luna de start pentru tracking pe agent. Nu este tratata ca angajare masiva.</p>}
    <div className="space-y-1">{payload.map((entry, index) => <div key={index} className="flex items-center gap-3">
      <div className="h-2 w-2 rounded-full" style={{ backgroundColor: entry.color }} />
      <span className="text-sm font-medium text-slate-600 dark:text-slate-300">{entry.name}:</span>
      <span className="text-sm font-bold text-slate-900 dark:text-white">{entry.dataKey === 'churned_negative' ? Math.abs(Number(entry.value ?? 0)) : String(entry.value ?? '')}</span>
    </div>)}</div>
  </div>;
}

function TeamSnapshot({ props }: { props: AgentsTeamMovementViewProps }) {
  const overview = props.overview;
  return <div ref={props.teamSectionRef} className="glass scroll-mt-20 rounded-3xl p-4">
    <div className="mb-3 flex items-start justify-between gap-3"><div><h3 className="text-sm font-bold">Snapshot — {props.currentMonth}</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">{props.filterLabel}</p></div>{props.loadingOverview && <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800"><RefreshCw size={14} className="animate-spin text-slate-400" /></div>}</div>
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <MetricCard icon={<Users size={16} className="text-indigo-500" />} label="Activi" value={overview?.active_count ?? '-'} className="bg-slate-50/80 dark:bg-slate-800/40" />
      <MetricCard icon={<UserPlus size={16} className="text-emerald-500" />} label="Noi" value={overview?.new_count ?? '-'} className="bg-emerald-50/50 text-emerald-600 dark:bg-emerald-900/10 dark:text-emerald-400" />
      <MetricCard icon={<UserCheck size={16} className="text-amber-500" />} label="Reactivati" value={overview?.reactivated_count ?? '-'} className="bg-amber-50/50 text-amber-600 dark:bg-amber-900/10 dark:text-amber-400" />
      <MetricCard icon={<UserMinus size={16} className="text-rose-500" />} label="Iesiti luna" value={overview?.left_this_month_count ?? '-'} hint="fara vanzari fata de luna trecuta" className="bg-rose-50/50 text-rose-600 dark:bg-rose-900/10 dark:text-rose-400" />
      <MetricCard icon={<TrendingUp size={16} className="text-indigo-500" />} label="Retentie" value={overview?.retention_rate != null ? `${overview.retention_rate}%` : '-'} className="bg-indigo-50/50 text-indigo-600 dark:bg-indigo-900/10 dark:text-indigo-400" />
    </div>
  </div>;
}

function TeamHealth({ overview }: Pick<AgentsTeamMovementViewProps, 'overview'>) {
  return <div className="glass rounded-3xl p-4">
    <div className="mb-3"><h3 className="text-sm font-bold">Sanatate Echipă</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">Indicatori de stabilitate si trend</p></div>
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <MetricCard icon={<Users size={16} className="text-slate-500" />} label="Total Unici" value={overview?.total_unique_agents ?? '-'} hint="in sistem" className="bg-slate-50/80 dark:bg-slate-800/40" />
      <MetricCard icon={<Award size={16} className="text-blue-500" />} label="Vechime Medie" value={overview?.avg_seniority_months != null ? `${overview.avg_seniority_months} luni` : '-'} className="bg-blue-50/50 text-blue-600 dark:bg-blue-900/10 dark:text-blue-400" />
      <MetricCard icon={<Activity size={16} className="text-purple-500" />} label="Stabilitate" value={overview?.stability_rate != null ? `${overview.stability_rate}%` : '-'} hint="> 6 luni vechime" className="bg-purple-50/50 text-purple-600 dark:bg-purple-900/10 dark:text-purple-400" />
      <MetricCard icon={<UserMinus size={16} className="text-rose-500" />} label="Iesiti istoric" value={overview?.churned_total_count ?? '-'} hint="absenti ≥ 2 luni" className="bg-rose-50/50 text-rose-600 dark:bg-rose-900/10 dark:text-rose-400" />
    </div>
  </div>;
}

function ChurnAndFlux({ props }: { props: AgentsTeamMovementViewProps }) {
  const churn = props.churnAnalysis;
  return <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
    <div className="glass rounded-3xl p-4"><div className="mb-3"><h3 className="text-sm font-bold">Analiza Churn</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">Iesiri de personal pentru snapshot {props.currentMonth}</p></div><div className="grid grid-cols-2 gap-3">
      <ChurnCard label="Churn luna" value={churn.currentChurnRate != null ? `${churn.currentChurnRate.toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%` : '-'} hint={`${churn.currentExited} iesiti`} className="bg-rose-50/60 text-rose-600 dark:bg-rose-900/10 dark:text-rose-400" />
      <ChurnCard label="Net luna" value={`${churn.currentNetGrowth > 0 ? '+' : ''}${churn.currentNetGrowth}`} hint="activi vs luna trecuta" className={`bg-indigo-50/60 dark:bg-indigo-900/10 ${churn.currentNetGrowth < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}`} />
      <ChurnCard label="Churn mediu 3 luni" value={churn.avgChurnRate != null ? `${churn.avgChurnRate.toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%` : '-'} className="bg-slate-50/80 dark:bg-slate-800/40" />
      <ChurnCard label="Iesiri in trend" value={churn.totalExited} hint="din 2025-02 incoace" className="bg-slate-50/80 dark:bg-slate-800/40" />
    </div></div>
    <div className="glass rounded-3xl p-4"><div className="mb-3"><h3 className="text-sm font-bold">Top Magazine dupa Flux</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">Magazine cu cele mai multe intrari si iesiri de agenti</p></div><div className="space-y-2">
      {props.topFluxStores.length === 0 && <div className="rounded-2xl bg-slate-50 p-4 text-center text-xs text-slate-500 dark:bg-slate-800/40">Nu exista modificari in selectia curenta.</div>}
      {props.topFluxStores.map((item) => <div key={item.site_code} className="flex items-center justify-between gap-3 rounded-2xl bg-slate-50 px-3 py-2 dark:bg-slate-800/40"><div className="min-w-0"><div className="truncate text-xs font-bold text-slate-700 dark:text-slate-200">{item.locatie || item.site_code}</div><div className="mt-0.5 text-[10px] text-slate-500">{item.asm} · {item.change_reason || 'modificat'}</div></div><div className="flex shrink-0 items-center gap-1">{item.added_agents_count > 0 && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">+{item.added_agents_count}</span>}{item.removed_agents_count > 0 && <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">-{item.removed_agents_count}</span>}</div></div>)}
    </div></div>
  </div>;
}

function MovementChart({ chartData, maxMovement }: Pick<AgentsTeamMovementViewProps, 'chartData' | 'maxMovement'>) {
  return <div className="glass rounded-3xl p-4"><div className="mb-4"><h3 className="text-sm font-bold">Miscare de personal</h3><p className="mt-1 text-[11px] text-slate-500">Intrari, iesiri si efectiv activ. 01.2025 este baseline de tracking.</p></div><div className="h-64 w-full">
    {chartData.length > 0 ? <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}><ComposedChart data={chartData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" opacity={0.5} />
      <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} dy={10} tickFormatter={(value) => value.split('-').reverse().join('.')} />
      <YAxis yAxisId="movement" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} domain={[-maxMovement, maxMovement]} tickFormatter={(value) => `${Math.abs(Number(value))}`} />
      <YAxis yAxisId="active" orientation="right" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} />
      <Tooltip content={CustomTooltip} /><Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} iconType="circle" iconSize={8} />
      <Bar yAxisId="movement" dataKey="new" name="Noi" stackId="in" fill="#10b981" barSize={12} radius={[4, 4, 0, 0]} />
      <Bar yAxisId="movement" dataKey="reactivated" name="Reactivati" stackId="in" fill="#f59e0b" radius={[4, 4, 0, 0]} />
      <Bar yAxisId="movement" dataKey="churned_negative" name="Iesiti" fill="#e11d48" barSize={12} radius={[0, 0, 4, 4]} />
      <Line yAxisId="active" type="monotone" dataKey="active" name="Total Activi" stroke="#6366f1" strokeWidth={3} dot={{ r: 3, strokeWidth: 2 }} />
      <Line yAxisId="movement" type="monotone" dataKey="net_growth" name="Net" stroke="#8b5cf6" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 2 }} />
    </ComposedChart></ResponsiveContainer> : <div className="flex h-full items-center justify-center text-xs text-slate-400">Nu exista date de miscare.</div>}
  </div></div>;
}

export function AgentsTeamMovementView(props: AgentsTeamMovementViewProps) {
  return <>
    <TeamSnapshot props={props} />
    <TeamHealth overview={props.overview} />
    <ChurnAndFlux props={props} />
    <MovementChart chartData={props.chartData} maxMovement={props.maxMovement} />
  </>;
}

function MetricCard({ icon, label, value, hint, className }: { icon: ReactNode; label: string; value: ReactNode; hint?: string; className: string }) {
  return <div className={`rounded-2xl p-3 ${className}`}><div className="mb-2 flex items-center gap-2">{icon}<div className="text-xs font-bold text-slate-600 dark:text-slate-400">{label}</div></div><div className="text-2xl font-black">{value}</div>{hint && <div className="mt-1 text-[10px] text-slate-500">{hint}</div>}</div>;
}

function ChurnCard({ label, value, hint, className }: { label: string; value: ReactNode; hint?: string; className: string }) {
  return <div className={`rounded-2xl p-3 ${className}`}><div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</div><div className="mt-1 text-2xl font-black">{value}</div>{hint && <div className="mt-1 text-[10px] text-slate-500">{hint}</div>}</div>;
}
