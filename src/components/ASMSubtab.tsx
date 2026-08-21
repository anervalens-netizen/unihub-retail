import { useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, RefreshCw, Store, Users } from 'lucide-react';

import { fetchManagerOverview } from '../api/hr';
import { formatMonthLabel, getCurrentYearMonth } from '../lib/dates';
import { cn } from '../lib/utils';
import { ManagerDesktopTable } from './asm/ManagerDesktopTable';
import { ManagerMobileCard } from './asm/ManagerMobileCard';
import { summarizeManagerOverview } from './asm/managerOverviewModel';

const TODAY_MONTH = getCurrentYearMonth();
const NUMBER = new Intl.NumberFormat('ro-RO');

function SummaryCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
        {icon}
        {label}
      </div>
      <div className="mt-2 text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">{value}</div>
      <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{hint}</p>
    </div>
  );
}

export function ASMSubtab({ currentMonth }: { currentMonth?: string }) {
  const [month, setMonth] = useState(currentMonth || TODAY_MONTH);
  const query = useQuery({
    queryKey: ['manager-overview', month],
    queryFn: ({ signal }) => fetchManagerOverview(month, signal),
  });

  const summary = useMemo(() => summarizeManagerOverview(query.data), [query.data]);
  const net = summary.net;

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 pb-24 lg:max-w-none lg:p-0 lg:pb-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">Overview echipe manageri</h2>
          <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-slate-500">
            Structura curentă, acoperirea cu agenți și semnalele operaționale pentru {formatMonthLabel(month)}.
            Intrările și ieșirile compară portofoliul actual cu luna precedentă.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="month"
            aria-label="Luna overview manageri"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          />
          <button
            type="button"
            onClick={() => void query.refetch()}
            aria-label="Reîncarcă overview manageri"
            title="Reîncarcă"
            className="rounded-xl bg-slate-100 p-2.5 text-slate-600 transition-colors hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            <RefreshCw className={cn('h-4 w-4', query.isFetching && 'animate-spin')} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <SummaryCard icon={<Users className="h-4 w-4 text-indigo-500" />} label="Manageri activi" value={NUMBER.format(summary.managers)} hint="portofolii operaționale" />
        <SummaryCard icon={<Store className="h-4 w-4 text-sky-500" />} label="Magazine active" value={NUMBER.format(summary.stores)} hint="exclusiv structura Retail" />
        <SummaryCard icon={<Users className="h-4 w-4 text-emerald-500" />} label="Agenți activi" value={NUMBER.format(summary.agents)} hint="unici în portofoliul managerului" />
        <SummaryCard
          icon={<Activity className="h-4 w-4 text-amber-500" />}
          label="Mișcare echipe"
          value={`${net > 0 ? '+' : ''}${net}`}
          hint={`${summary.added} intrări · ${summary.left} ieșiri · ${summary.attention} de urmărit`}
        />
      </div>

      {query.isLoading && (
        <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
          Se încarcă overview-ul managerilor…
        </div>
      )}
      {query.isError && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center text-sm text-rose-600 dark:border-rose-900/50 dark:bg-rose-900/20 dark:text-rose-300">
          Nu am putut încărca overview-ul. Reîncearcă sau verifică serviciul Retail.
        </div>
      )}
      {!query.isLoading && !query.isError && query.data?.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
          Nu există manageri activi în structura curentă.
        </div>
      )}
      <div className="space-y-3">
        {query.data?.map((row) => <ManagerMobileCard key={row.manager} row={row} month={month} />)}
      </div>
      {query.data && query.data.length > 0 && <ManagerDesktopTable rows={query.data} month={month} />}
    </div>
  );
}
