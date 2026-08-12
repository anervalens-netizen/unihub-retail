import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

import type { GrileManager, GrileTeamLeader } from '../../api/grile';
import { matchesGrileStatusFilter, type StatusFilter } from './grileOverviewFilters';
import { DesktopTableHeader, StoreRow } from './GrileStoreRow';

function usePersistedGroup(storageKey: string) {
  const [open, setOpen] = useState(() => sessionStorage.getItem(storageKey) !== 'closed');
  const toggle = () => setOpen((value) => {
    const next = !value;
    sessionStorage.setItem(storageKey, next ? 'open' : 'closed');
    return next;
  });
  return { open, toggle };
}

function TeamLeaderGroup({ tl, month }: { tl: GrileTeamLeader; month: string }) {
  const group = usePersistedGroup(`unihub_grile_tl_${tl.name ?? 'fara-tl'}`);
  const stores = tl.firms.flatMap((firm) => firm.stores.map((store) => <StoreRow key={store.site_code} s={store} month={month} />));
  if (!tl.name) return <>{stores}</>;
  return <div>
    <button onClick={group.toggle} className="w-full border-y border-slate-200/70 bg-slate-100/70 px-4 py-1.5 text-left transition-colors hover:bg-slate-200/60 dark:border-slate-700/70 dark:bg-slate-800/50 dark:hover:bg-slate-800">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300">{group.open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}Team Leader · {tl.name}</div>
    </button>
    {group.open && <div>{stores}</div>}
  </div>;
}

function ManagerSummary({ manager, mobile }: { manager: GrileManager; mobile: boolean }) {
  if (mobile) return <div className="flex items-center justify-between gap-2 lg:hidden">
    <div className="flex min-w-0 items-center gap-2"><span className="truncate font-semibold text-slate-800 dark:text-slate-100">{manager.name}</span><span className="flex-shrink-0 text-xs text-slate-400">{manager.store_count} mag.</span></div>
    <div className="flex flex-shrink-0 items-center gap-2 text-xs"><span className="text-emerald-600 dark:text-emerald-400">{manager.ok} OK</span><span className="text-rose-600 dark:text-rose-400">{manager.problems} business</span>{manager.provider_errors > 0 && <span className="text-rose-500">{manager.provider_errors} Google</span>}{manager.provider_stale > 0 && <span className="text-amber-600">{manager.provider_stale} vechi</span>}{manager.avg_completion !== null && <span className="text-slate-500">{manager.avg_completion}%</span>}</div>
  </div>;
  return <div className="hidden items-center justify-between gap-4 lg:flex">
    <div className="flex min-w-0 items-center gap-2"><span className="truncate font-semibold text-slate-800 dark:text-slate-100">{manager.name}</span><span className="flex-shrink-0 text-xs text-slate-500 dark:text-slate-400">{manager.store_count} magazine</span></div>
    <div className="flex flex-shrink-0 items-center gap-2 text-xs font-semibold">
      <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">{manager.ok} OK</span>
      <span className="rounded-full bg-rose-100 px-2.5 py-1 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">{manager.problems} business</span>
      {manager.provider_errors > 0 && <span className="rounded-full bg-rose-100 px-2.5 py-1 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">{manager.provider_errors} erori Google</span>}
      {manager.provider_stale > 0 && <span className="rounded-full bg-amber-100 px-2.5 py-1 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">{manager.provider_stale} date vechi</span>}
      {manager.avg_completion !== null && <span className="rounded-full bg-slate-200 px-2.5 py-1 text-slate-600 dark:bg-slate-700 dark:text-slate-300">Completare {manager.avg_completion}%</span>}
    </div>
  </div>;
}

function ManagerGroup({ manager, filter, month }: { manager: GrileManager; filter: StatusFilter; month: string }) {
  const group = usePersistedGroup(`unihub_grile_manager_${manager.name}`);
  const filteredLeaders = useMemo(() => manager.team_leaders.map((leader) => ({
    ...leader,
    firms: leader.firms.map((firm) => ({
      ...firm, stores: firm.stores.filter((store) => matchesGrileStatusFilter(store, filter)),
    })).filter((firm) => firm.stores.length > 0),
  })).filter((leader) => leader.firms.length > 0), [manager, filter]);
  if (filteredLeaders.length === 0) return null;
  return <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
    <button onClick={group.toggle} className="w-full bg-slate-50 px-3 py-2 text-left transition-colors hover:bg-slate-100 dark:bg-slate-800/60 dark:hover:bg-slate-800">
      <div className="flex items-center gap-2"><span className="shrink-0">{group.open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</span><div className="min-w-0 flex-1"><ManagerSummary manager={manager} mobile /><ManagerSummary manager={manager} mobile={false} /></div></div>
    </button>
    {group.open && <div className="bg-white dark:bg-slate-900">{filteredLeaders.map((leader, index) => <TeamLeaderGroup key={leader.name ?? `__no_tl_${index}`} tl={leader} month={month} />)}</div>}
  </div>;
}

export function GrileOverviewTree({ managers, month, filter, loading, error }: {
  managers: GrileManager[];
  month: string;
  filter: StatusFilter;
  loading: boolean;
  error: boolean;
}) {
  return <div className="space-y-2">
    <DesktopTableHeader />
    {loading && <div className="p-8 text-center text-slate-400">Se încarcă…</div>}
    {error && <div className="p-8 text-center text-rose-500">Eroare la încărcare.</div>}
    {!loading && managers.length === 0 && <div className="p-8 text-center text-slate-400">Nicio dată. Rulează o verificare pentru luna selectată.</div>}
    {managers.map((manager) => <ManagerGroup key={manager.name} manager={manager} filter={filter} month={month} />)}
  </div>;
}
