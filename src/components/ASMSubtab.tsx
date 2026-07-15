import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  MapPinned,
  RefreshCw,
  Store,
  UserMinus,
  UserPlus,
  Users,
  WalletCards,
} from 'lucide-react';
import { fetchManagerOverview, type ManagerOverview } from '../api/hr';
import { formatMonthLabel } from '../lib/dates';
import { cn } from '../lib/utils';
import { AsmSalaryGrila } from './AsmSalaryGrila';
import { FirmaBadge } from './FirmaBadge';

const TODAY_MONTH = new Date().toISOString().slice(0, 7);
const SALARY_GRILA_MANAGERS = new Set(['Mihai Condorateanu']);
const NUMBER = new Intl.NumberFormat('ro-RO');

type Tone = 'emerald' | 'amber' | 'rose' | 'slate';

const TONE = {
  emerald: {
    badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    bar: 'bg-emerald-500',
  },
  amber: {
    badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    bar: 'bg-amber-500',
  },
  rose: {
    badge: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
    bar: 'bg-rose-500',
  },
  slate: {
    badge: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
    bar: 'bg-slate-400',
  },
} satisfies Record<Tone, { badge: string; bar: string }>;

function metricTone(value: number | null, green: number, amber: number): Tone {
  if (value === null) return 'slate';
  if (value >= green) return 'emerald';
  if (value >= amber) return 'amber';
  return 'rose';
}

function healthInfo(row: ManagerOverview): { label: string; detail: string; tone: Tone } {
  if (!row.reporting_available) {
    return { label: 'Neactualizat', detail: 'Nu există încă raportare pentru luna selectată.', tone: 'slate' };
  }
  if (row.stores_without_agents > 0) {
    return {
      label: 'Necesită atenție',
      detail: `${row.stores_without_agents} magazine fără agent activ în raportare.`,
      tone: 'rose',
    };
  }
  const signals: string[] = [];
  if (row.agents_left > row.agents_added) {
    signals.push(`flux net ${row.agent_delta} agenți`);
  }
  if (row.visits_available && row.visit_coverage_pct !== null && row.visit_coverage_pct < 70) {
    signals.push(`acoperire vizite ${row.visit_coverage_pct}%`);
  }
  if (row.visits_available && row.avg_visit_completion !== null && row.avg_visit_completion < 75) {
    signals.push(`completare vizite ${row.avg_visit_completion}%`);
  }
  if (row.visits_available && row.checklist_score !== null && row.checklist_score < 85) {
    signals.push(`checklist ${row.checklist_score}%`);
  }
  if (signals.length > 0) {
    return {
      label: 'De urmărit',
      detail: `${signals.join(' · ')}.`,
      tone: 'amber',
    };
  }
  return { label: 'Stabilă', detail: 'Portofoliul este acoperit, fără deficit net de agenți.', tone: 'emerald' };
}

function SummaryCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
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

function PortfolioStat({
  icon,
  label,
  value,
  hint,
  valueClassName,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
  valueClassName?: string;
}) {
  return (
    <div className="rounded-xl bg-white/80 px-3 py-2.5 dark:bg-slate-900/50">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
        {icon}
        {label}
      </div>
      <div className={cn('mt-1 text-lg font-bold tabular-nums text-slate-800 dark:text-slate-100', valueClassName)}>
        {value}
      </div>
      {hint && <div className="text-[10px] text-slate-500 dark:text-slate-400">{hint}</div>}
    </div>
  );
}

function HealthMetric({
  icon,
  label,
  value,
  display,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | null;
  display: string;
  tone: Tone;
}) {
  const width = value === null ? 0 : Math.max(0, Math.min(value, 100));
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center justify-between gap-2 text-[11px]">
        <span className="inline-flex min-w-0 items-center gap-1.5 truncate font-medium text-slate-500 dark:text-slate-400">
          {icon}
          {label}
        </span>
        <strong className="flex-shrink-0 tabular-nums text-slate-700 dark:text-slate-200">{display}</strong>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div className={cn('h-full rounded-full', TONE[tone].bar)} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function StorePortfolioTable({ row }: { row: ManagerOverview }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
      <table className="min-w-[680px] w-full text-xs">
        <thead className="bg-slate-100 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          <tr>
            <th className="px-3 py-2.5 text-left">Magazin</th>
            <th className="px-3 py-2.5 text-left">Firmă</th>
            <th className="px-3 py-2.5 text-center">Agenți activi</th>
            <th className="px-3 py-2.5 text-center">Luna precedentă</th>
            <th className="px-3 py-2.5 text-center">Schimbare</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
          {row.stores.map((store) => {
            const deltaTone = store.agent_delta > 0
              ? 'text-emerald-600 dark:text-emerald-400'
              : store.agent_delta < 0
                ? 'text-rose-600 dark:text-rose-400'
                : 'text-slate-500 dark:text-slate-400';
            return (
              <tr key={store.site_code} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <td className="px-3 py-2">
                  <div className="font-semibold text-slate-700 dark:text-slate-200">{store.locatie}</div>
                  <div className="text-[10px] text-slate-500 dark:text-slate-400">{store.site_code}</div>
                </td>
                <td className="px-3 py-2"><FirmaBadge firma={store.firma} /></td>
                <td className="px-3 py-2 text-center font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                  {store.active_agents}
                </td>
                <td className="px-3 py-2 text-center tabular-nums text-slate-500">{store.previous_active_agents}</td>
                <td className={cn('px-3 py-2 text-center font-bold tabular-nums', deltaTone)}>
                  {store.agent_delta > 0 ? '+' : ''}{store.agent_delta}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ManagerCard({ row, month }: { row: ManagerOverview; month: string }) {
  const [open, setOpen] = useState(false);
  const health = healthInfo(row);
  const staffedStores = row.active_stores - row.stores_without_agents;
  const staffingCoverage = row.active_stores > 0 ? staffedStores / row.active_stores * 100 : null;
  const regionalLabel = row.regional && row.regional !== row.manager ? row.regional : null;

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/70 dark:border-slate-700 dark:bg-slate-800/40">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="w-full px-4 py-3 text-left transition-colors hover:bg-slate-100 dark:hover:bg-slate-800"
        aria-expanded={open}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            <div className="mt-0.5 rounded-xl bg-indigo-100 p-2 text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-300">
              <Users className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-base font-bold text-slate-900 dark:text-slate-100">{row.manager}</h3>
                {SALARY_GRILA_MANAGERS.has(row.manager) && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                    <WalletCards className="h-3 w-3" /> Grilă salariu
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                {regionalLabel ? `Regional: ${regionalLabel} · ` : ''}{row.active_stores} magazine · {row.active_agents} agenți
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', TONE[health.tone].badge)}>
              {health.label}
            </span>
            {open ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
          </div>
        </div>
      </button>

      <div className="border-t border-slate-200 px-4 py-3 dark:border-slate-700">
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <PortfolioStat icon={<Store className="h-3.5 w-3.5" />} label="Magazine" value={NUMBER.format(row.active_stores)} hint={`${staffedStores} cu agenți raportați`} />
          <PortfolioStat icon={<Users className="h-3.5 w-3.5" />} label="Agenți activi" value={NUMBER.format(row.active_agents)} hint={`${row.agents_per_store.toLocaleString('ro-RO')} / magazin`} />
          <PortfolioStat
            icon={<UserPlus className="h-3.5 w-3.5" />}
            label="Intrări în portofoliu"
            value={`+${row.agents_added}`}
            hint="față de luna precedentă"
            valueClassName="text-emerald-600 dark:text-emerald-400"
          />
          <PortfolioStat
            icon={<UserMinus className="h-3.5 w-3.5" />}
            label="Ieșiri din portofoliu"
            value={`-${row.agents_left}`}
            hint={`flux net ${row.agent_delta > 0 ? '+' : ''}${row.agent_delta}`}
            valueClassName={row.agents_left > 0 ? 'text-rose-600 dark:text-rose-400' : undefined}
          />
        </div>

        <div className="mt-3 grid gap-x-5 gap-y-3 rounded-xl bg-white px-3 py-3 md:grid-cols-2 xl:grid-cols-4 dark:bg-slate-900/60">
          <HealthMetric
            icon={<Users className="h-3.5 w-3.5" />}
            label="Acoperire cu agenți"
            value={staffingCoverage}
            display={`${staffedStores}/${row.active_stores}`}
            tone={metricTone(staffingCoverage, 100, 90)}
          />
          <HealthMetric
            icon={<MapPinned className="h-3.5 w-3.5" />}
            label="Acoperire vizite"
            value={row.visit_coverage_pct}
            display={row.visits_available ? `${row.visited_stores}/${row.active_stores}` : 'Fără date'}
            tone={metricTone(row.visit_coverage_pct, 90, 70)}
          />
          <HealthMetric
            icon={<Activity className="h-3.5 w-3.5" />}
            label="Completare vizite"
            value={row.avg_visit_completion}
            display={row.avg_visit_completion === null ? 'Fără date' : `${row.avg_visit_completion}%`}
            tone={metricTone(row.avg_visit_completion, 90, 75)}
          />
          <HealthMetric
            icon={<ClipboardCheck className="h-3.5 w-3.5" />}
            label="Checklist"
            value={row.checklist_score}
            display={row.checklist_score === null ? 'Fără date' : `${row.checklist_score}%`}
            tone={metricTone(row.checklist_score, 95, 85)}
          />
        </div>

        <div className="mt-2 flex items-start gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
          {health.tone === 'emerald'
            ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-emerald-500" />
            : <AlertTriangle className={cn('mt-0.5 h-3.5 w-3.5 flex-shrink-0', health.tone === 'rose' ? 'text-rose-500' : 'text-amber-500')} />}
          <span>{health.detail}</span>
        </div>
      </div>

      {open && (
        <div className="space-y-3 border-t border-slate-200 bg-white px-4 py-4 dark:border-slate-700 dark:bg-slate-900">
          {SALARY_GRILA_MANAGERS.has(row.manager) && (
            <AsmSalaryGrila asm={row.manager} defaultMonth={month} />
          )}
          <div>
            <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
              <div>
                <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100">Portofoliu magazine</h4>
                <p className="text-[11px] text-slate-500">Acoperirea cu agenți comparată cu luna precedentă; fără scorare de vânzări.</p>
              </div>
              <span className="text-xs text-slate-500 dark:text-slate-400">{row.stores.length} magazine</span>
            </div>
            <StorePortfolioTable row={row} />
          </div>
        </div>
      )}
    </article>
  );
}

export function ASMSubtab({ currentMonth }: { currentMonth?: string }) {
  const [month, setMonth] = useState(currentMonth || TODAY_MONTH);
  const query = useQuery({
    queryKey: ['manager-overview', month],
    queryFn: () => fetchManagerOverview(month),
  });

  const summary = useMemo(() => {
    const rows = query.data ?? [];
    return {
      managers: rows.length,
      stores: rows.reduce((sum, row) => sum + row.active_stores, 0),
      agents: rows.reduce((sum, row) => sum + row.active_agents, 0),
      added: rows.reduce((sum, row) => sum + row.agents_added, 0),
      left: rows.reduce((sum, row) => sum + row.agents_left, 0),
      attention: rows.filter((row) => healthInfo(row).tone === 'rose' || healthInfo(row).tone === 'amber').length,
    };
  }, [query.data]);
  const net = summary.added - summary.left;

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 pb-24 lg:pb-8">
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
        <div className="rounded-2xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
          Nu există manageri activi în structura curentă.
        </div>
      )}
      <div className="space-y-3">
        {query.data?.map((row) => <ManagerCard key={row.manager} row={row} month={month} />)}
      </div>
    </div>
  );
}
