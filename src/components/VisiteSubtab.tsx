import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MapPin, Search } from 'lucide-react';

import { getFilterOptions } from '../api/filters';
import { getVisitsReport, getVisitsTree, type TeamLeaderGroup, type VisitReportResponse, type VisitReportRow } from '../api/visitsReport';
import type { AppFilters } from '../lib/appFilters';
import { ALL_FIRMS, ALL_SCOPE } from '../lib/filterValues';
import { queryKeys } from '../lib/queryKeys';
import { cn } from '../lib/utils';
import { buildVisitsReportQuery, buildVisitsTreeQuery } from '../lib/visitQueries';
import { VisitDrawer } from '../features/visits/VisitDrawer';
import { MonthPicker, TeamLeaderRow } from '../features/visits/VisitsTree';

interface VisiteSubtabProps { currentMonth: string; months: string[] }

const ALL_FILTERS: AppFilters = { firma: ALL_FIRMS, rm: ALL_SCOPE, magazin: [], agent: [] };
const COMPLIANCE_KEYS: Array<{ key: keyof VisitReportRow; label: string }> = [
  { key: 'curatenie_pct', label: 'Curatenie' }, { key: 'imagine_pct', label: 'Imagine' }, { key: 'uniforma_pct', label: 'Uniforma' }, { key: 'afise_pct', label: 'Afise' }, { key: 'produse_promo_pct', label: 'Promo' },
];

function useVisitsSubtab({ currentMonth, months }: VisiteSubtabProps) {
  const [openVisitId, setOpenVisitId] = useState<string | null>(null);
  const [selectedMonth, setSelectedMonth] = useState(currentMonth);
  const [teamLeaderSearch, setTeamLeaderSearch] = useState('');
  const availableMonths = useMemo(() => Array.from(new Set(months)).sort().reverse(), [months]);
  useEffect(() => {
    if (availableMonths.length > 0 && !availableMonths.includes(selectedMonth)) {
      const latestMonth = availableMonths[0];
      if (latestMonth) setSelectedMonth(latestMonth);
    }
  }, [availableMonths, selectedMonth]);
  const summaryQuery = useQuery({ queryKey: queryKeys.visits.report(selectedMonth), queryFn: ({ signal }) => getVisitsReport(buildVisitsReportQuery(selectedMonth, ALL_FILTERS), signal), enabled: Boolean(selectedMonth), staleTime: 5 * 60 * 1000 });
  const treeQuery = useQuery({ queryKey: queryKeys.visits.tree(selectedMonth), queryFn: ({ signal }) => getVisitsTree(buildVisitsTreeQuery(selectedMonth, ALL_FILTERS), signal), enabled: Boolean(selectedMonth), staleTime: 5 * 60 * 1000 });
  const activeStoresQuery = useQuery({ queryKey: queryKeys.visits.activeStores(selectedMonth), queryFn: ({ signal }) => getFilterOptions(selectedMonth, signal), enabled: Boolean(selectedMonth), staleTime: 5 * 60 * 1000 });
  const groups = useMemo(() => treeQuery.data?.team_leaders ?? [], [treeQuery.data]);
  const filteredGroups = useMemo(() => {
    const needle = teamLeaderSearch.trim().toLocaleLowerCase('ro-RO');
    return groups.map((group) => ({ ...group, months: group.months.filter((month) => month.month === selectedMonth) })).filter((group) => group.months.length > 0).filter((group) => !needle || group.team_leader.toLocaleLowerCase('ro-RO').includes(needle)).map((group) => ({ ...group, nr_vizite: group.months.reduce((total, month) => total + month.nr_vizite, 0) }));
  }, [groups, selectedMonth, teamLeaderSearch]);
  const activeStoreCount = useMemo(() => new Set(activeStoresQuery.data?.magazine.map((store) => store.site_code) ?? []).size, [activeStoresQuery.data]);
  return { openVisitId, setOpenVisitId, selectedMonth, setSelectedMonth, teamLeaderSearch, setTeamLeaderSearch, availableMonths, summary: summaryQuery.data ?? null, filteredGroups, activeStoreCount, loadingSummary: summaryQuery.isPending, loadingTree: treeQuery.isPending, error: summaryQuery.error ?? treeQuery.error };
}

function PctBar({ value }: { value: number }) {
  const color = value >= 80 ? 'bg-emerald-500' : value >= 50 ? 'bg-amber-400' : 'bg-red-400';
  return <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700"><div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${value}%` }} /></div>;
}

function VisitsToolbar({ months, selectedMonth, search, onMonthChange, onSearch }: { months: string[]; selectedMonth: string; search: string; onMonthChange: (month: string) => void; onSearch: (value: string) => void }) {
  return <div className="grid gap-2 md:grid-cols-[220px_1fr]"><MonthPicker months={months} selected={selectedMonth} onChange={onMonthChange} /><label className="glass flex items-center gap-2 rounded-2xl px-3 py-2 text-sm"><Search size={15} className="text-slate-400" /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Caută Team Leader" className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-slate-400" /><span className="text-xs text-slate-400">filtru local</span></label></div>;
}

function VisitKpis({ summary, loading, activeStoreCount }: { summary: VisitReportResponse | null; loading: boolean; activeStoreCount: number }) {
  const missingStores = activeStoreCount > 0 ? Math.max(0, activeStoreCount - (summary?.magazine_unice ?? 0)) : null;
  const visitCoverage = activeStoreCount > 0 ? ((summary?.magazine_unice ?? 0) / activeStoreCount) * 100 : null;
  const completion = summary?.avg_completion ?? 0;
  return <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
    <div className="glass rounded-2xl p-3 text-center"><div className="text-2xl font-black text-indigo-600">{loading ? '—' : (summary?.total_vizite ?? 0)}</div><div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Vizite</div></div>
    <div className="glass rounded-2xl p-3 text-center"><div className="text-2xl font-black text-indigo-600">{loading ? '—' : (summary?.magazine_unice ?? 0)}</div><div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Magazine vizitate</div></div>
    <div className="glass rounded-2xl p-3 text-center"><div className={cn('text-2xl font-black', completion >= 80 ? 'text-emerald-600' : completion >= 50 ? 'text-amber-500' : 'text-red-500')}>{loading ? '—' : `${completion.toFixed(0)}%`}</div><div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Completare</div></div>
    <div className="glass rounded-2xl p-3 text-center"><div className={cn('text-2xl font-black', missingStores === 0 ? 'text-emerald-600' : 'text-amber-600')}>{loading ? '—' : visitCoverage === null ? '—' : `${visitCoverage.toFixed(0)}%`}</div><div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Acoperire rețea</div><div className="mt-1 text-xs text-slate-500">{missingStores === null ? 'univers indisponibil' : `${missingStores} magazine fără vizită`}</div></div>
  </div>;
}

function CompliancePanel({ summary, selectedMonth }: { summary: VisitReportResponse | null; selectedMonth: string }) {
  if (!summary?.rows.length) return null;
  const averages = COMPLIANCE_KEYS.reduce((result, { key }) => { const values = summary.rows.map((row) => row[key] as number); return { ...result, [key]: values.reduce((total, value) => total + value, 0) / values.length }; }, {} as Record<string, number>);
  return <div className="glass rounded-2xl p-4"><h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-500">Conformitate medie — {selectedMonth}</h3><div className="space-y-2">{COMPLIANCE_KEYS.map(({ key, label }) => { const average = averages[key] ?? 0; return <div key={key} className="flex items-center gap-2"><span className="w-20 text-[11px] font-semibold text-slate-600 dark:text-slate-300">{label}</span><div className="flex-1"><PctBar value={average} /></div><span className="w-10 text-right text-[11px] font-bold text-slate-700 dark:text-slate-200">{average.toFixed(0)}%</span></div>; })}</div></div>;
}

function TeamLeadersPanel({ groups, loading, onOpenVisit }: { groups: TeamLeaderGroup[]; loading: boolean; onOpenVisit: (id: string) => void }) {
  return <div className="glass overflow-hidden rounded-2xl"><div className="border-b border-slate-100 px-4 py-3 dark:border-slate-700"><h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">Vizite pe Team Leader</h3></div>{loading ? <div className="flex h-16 items-center justify-center text-xs text-slate-400">Se incarca...</div> : groups.length === 0 ? <div className="flex h-16 items-center justify-center text-xs text-slate-400">Nicio vizita pentru luna selectata</div> : <div>{groups.map((group) => <TeamLeaderRow key={group.team_leader} group={group} onOpenVisit={onOpenVisit} />)}</div>}<div className="px-4 py-2 text-[10px] text-slate-400"><span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" /> ≥80%</span><span className="mx-2 inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-400" /> 50–79%</span><span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-400" /> &lt;50%</span></div></div>;
}

export function VisiteSubtab(props: VisiteSubtabProps) {
  const model = useVisitsSubtab(props);
  if (model.loadingTree && model.loadingSummary) return <div className="flex h-40 items-center justify-center text-sm font-semibold text-slate-500">Se incarca vizitele...</div>;
  if (model.error) return <div className="mx-4 mt-4 rounded-2xl bg-red-50 p-4 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">{model.error.message || 'Eroare la incarcare'}</div>;
  if (!model.loadingTree && model.availableMonths.length === 0) return <div className="flex h-40 flex-col items-center justify-center gap-2 text-slate-400"><MapPin size={28} strokeWidth={1.5} /><p className="text-sm font-semibold">Nicio vizita inregistrata</p></div>;
  return <div className="space-y-4 px-4"><VisitsToolbar months={model.availableMonths} selectedMonth={model.selectedMonth} search={model.teamLeaderSearch} onMonthChange={model.setSelectedMonth} onSearch={model.setTeamLeaderSearch} /><VisitKpis summary={model.summary} loading={model.loadingSummary} activeStoreCount={model.activeStoreCount} /><CompliancePanel summary={model.summary} selectedMonth={model.selectedMonth} /><TeamLeadersPanel groups={model.filteredGroups} loading={model.loadingTree} onOpenVisit={model.setOpenVisitId} />{model.openVisitId && <VisitDrawer visitId={model.openVisitId} onClose={() => model.setOpenVisitId(null)} />}</div>;
}
