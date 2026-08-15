import { useState } from 'react';
import { Camera, ChevronDown, ChevronRight } from 'lucide-react';

import type { TeamLeaderGroup, VisitSummaryItem } from '../../api/visitsReport';
import { FirmaBadge } from '../../components/FirmaBadge';
import { formatIsoDate, formatIsoMonth } from '../../lib/dates';
import { cn } from '../../lib/utils';
import { CompletionBadge } from './VisitDrawer';

type FlatVisit = VisitSummaryItem & { date: string };

function VisitLeaf({ visit, onOpen }: { visit: FlatVisit; onOpen: (id: string) => void }) {
  const dayLabel = visit.date && visit.date !== '—' ? formatIsoDate(visit.date) : null;
  return <button onClick={() => onOpen(visit.id)} className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left transition-colors hover:bg-indigo-50 dark:hover:bg-indigo-900/20"><span className="flex-1 text-xs text-slate-500 dark:text-slate-400">{dayLabel ?? '—'}{visit.ora ? ` · ${visit.ora.slice(0, 5)}` : ''}</span>{visit.has_photos && <Camera size={12} className="shrink-0 text-slate-400" />}<CompletionBadge pct={visit.completion_pct} /></button>;
}

interface StoreVisits { magazin: string; locatie: string | null; firma: string | null; visits: FlatVisit[] }

function StoreRow({ store, onOpenVisit }: { store: StoreVisits; onOpenVisit: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div><button onClick={() => setOpen((value) => !value)} className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800"><FirmaBadge firma={store.firma || ''} /><span className="min-w-0 flex-1 truncate text-xs font-semibold text-slate-700 dark:text-slate-200">{store.locatie || store.magazin}</span><span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-slate-700">{store.visits.length} viz.</span>{open ? <ChevronDown size={13} className="shrink-0 text-slate-400" /> : <ChevronRight size={13} className="shrink-0 text-slate-400" />}</button>
      {open && <div className="ml-5 space-y-0.5 pb-1">{store.visits.map((visit) => <VisitLeaf key={visit.id} visit={visit} onOpen={onOpenVisit} />)}</div>}
    </div>
  );
}

function storesOfGroup(group: TeamLeaderGroup): StoreVisits[] {
  const flat: FlatVisit[] = group.months.flatMap((month) => month.days.flatMap((day) => day.visits.map((visit) => ({ ...visit, date: day.date }))));
  const stores = new Map<string, StoreVisits>();
  for (const visit of flat) {
    const key = visit.magazin || '—';
    const store = stores.get(key) ?? { magazin: key, locatie: visit.locatie, firma: visit.firma, visits: [] };
    store.visits.push(visit);
    stores.set(key, store);
  }
  for (const store of stores.values()) store.visits.sort((left, right) => right.date.localeCompare(left.date) || (right.ora || '').localeCompare(left.ora || ''));
  return Array.from(stores.values()).sort((left, right) => (left.firma || '').localeCompare(right.firma || '') || (left.locatie || left.magazin).localeCompare(right.locatie || right.magazin));
}

export function TeamLeaderRow({ group, onOpenVisit }: { group: TeamLeaderGroup; onOpenVisit: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-slate-100 last:border-0 dark:border-slate-800">
      <button onClick={() => setOpen((value) => !value)} className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"><div className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-black', open ? 'bg-indigo-600 text-white' : 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300')}>{group.team_leader.charAt(0).toUpperCase()}</div><span className="flex-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{group.team_leader}</span><span className="text-xs text-slate-400">{group.nr_vizite} viz.</span>{open ? <ChevronDown size={15} className="text-slate-400" /> : <ChevronRight size={15} className="text-slate-400" />}</button>
      {open && <div className="space-y-0.5 pb-2 pl-4 pr-2">{storesOfGroup(group).map((store) => <StoreRow key={store.magazin} store={store} onOpenVisit={onOpenVisit} />)}</div>}
    </div>
  );
}

export function MonthPicker({ months, selected, onChange }: { months: string[]; selected: string; onChange: (month: string) => void }) {
  if (months.length === 0) return null;
  return <select value={selected} onChange={(event) => onChange(event.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">{months.map((month) => { const label = formatIsoMonth(month, { month: 'long', year: 'numeric' }); return <option key={month} value={month}>{label.charAt(0).toUpperCase() + label.slice(1)}</option>; })}</select>;
}
