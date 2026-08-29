import { useEffect, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, Clock, Loader2, PlayCircle, RefreshCw, XCircle } from 'lucide-react';

import { getApiErrorMessage } from '../../api/client';
import { getGrileOverview, runGrileCheck } from '../../api/grile';
import { cn } from '../../lib/utils';
import { GrileMonthlyPanel } from '../GrileMonthlyPanel';
import { GRILE_STATUS_FILTERS, type StatusFilter } from './grileOverviewFilters';
import { relativeGrileTime } from './grileFormatting';
import { GrileOverviewTree } from './GrileOverviewTree';

const LEGACY_GRILE_MONTH_KEY = 'unihub_grile_month';
const RUN_CHECK_ERROR_FALLBACK = 'Verificarea grilelor nu a putut fi pornită. Încearcă din nou.';

function useCurrentGrile(initialMonth?: string) {
  const [month, setMonth] = useState(initialMonth ?? '');
  const [filter, setFilter] = useState<StatusFilter>('all');
  const queryClient = useQueryClient();
  const overview = useQuery({
    queryKey: ['grile-overview', month],
    queryFn: ({ signal }) => getGrileOverview(month || undefined, signal),
    refetchInterval: (query) => {
      const run = (query.state.data as Awaited<ReturnType<typeof getGrileOverview>> | undefined)?.run;
      return run?.active ? 3000 : false;
    },
  });
  useEffect(() => {
    if (!month && overview.data?.month) setMonth(overview.data.month);
  }, [overview.data?.month, month]);
  useEffect(() => { sessionStorage.removeItem(LEGACY_GRILE_MONTH_KEY); }, []);
  const runCheck = useMutation({
    mutationFn: (submittedMonth: string) => runGrileCheck(submittedMonth),
    onSuccess: (_result, submittedMonth) => queryClient.invalidateQueries({
      queryKey: ['grile-overview', submittedMonth],
    }),
  });
  const run = overview.data?.run ?? null;
  const runCheckMatchesMonth = runCheck.variables === month;
  const running = run?.active === true || (runCheck.isPending && runCheckMatchesMonth);
  const canRunCheck = Boolean(month) && !running && !runCheck.isPending;
  const progressPct = run && run.progress_total > 0 ? Math.round((run.progress_current / run.progress_total) * 100) : 0;
  return { month, setMonth, filter, setFilter, overview, runCheck, run, running, runCheckMatchesMonth, canRunCheck, progressPct };
}

type GrileModel = ReturnType<typeof useCurrentGrile>;

export function CurrentGrileSubtab({ initialMonth }: { initialMonth?: string }) {
  const model = useCurrentGrile(initialMonth);
  const data = model.overview.data;
  return <div className="space-y-4">
    <GrileStatusCard model={model} />
    <GrileFilters filter={model.filter} onChange={model.setFilter} />
    <GrileOverviewTree managers={data?.managers ?? []} month={model.month || data?.month || ''} filter={model.filter} loading={model.overview.isLoading} error={model.overview.isError} />
  </div>;
}

function GrileStatusCard({ model }: { model: GrileModel }) {
  const data = model.overview.data;
  return <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Verificare grile salariale</h3><p className="mt-0.5 text-xs text-slate-500">Grila (K5/L5) vs target + vânzări din DB · cheie <code>site_code</code>. Rulează automat zilnic după importul vânzărilor.</p></div>
      <div className="flex items-center gap-3">
        <input type="month" value={model.month} onChange={(event) => model.setMonth(event.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800" />
        <button onClick={() => model.runCheck.mutate(model.month)} disabled={!model.canRunCheck} className={cn('inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors', !model.canRunCheck ? 'cursor-not-allowed bg-slate-400' : 'bg-indigo-600 hover:bg-indigo-700')}>{model.running ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}{model.running ? 'Rulează…' : 'Rulează verificare'}</button>
      </div>
    </div>
    <div className="mt-4 flex flex-wrap items-center gap-6">
      {data ? <>
        <Stat icon={<CheckCircle2 className="h-5 w-5 text-emerald-500" />} value={data.summary.business_ok} label="business OK" />
        <Stat icon={<AlertTriangle className="h-5 w-5 text-rose-500" />} value={data.summary.business_problems} label="diferențe business" />
        {data.summary.provider_errors > 0 && <Stat icon={<XCircle className="h-5 w-5 text-rose-400" />} value={data.summary.provider_errors} label="erori Google" />}
        {data.summary.provider_stale > 0 && <Stat icon={<Clock className="h-5 w-5 text-amber-500" />} value={data.summary.provider_stale} label="date vechi" />}
        <Stat icon={<RefreshCw className="h-5 w-5 text-slate-400" />} value={data.total_sheets} label="magazine" />
        {model.run && <div className="flex items-center gap-1.5 text-xs text-slate-500"><Clock className="h-3.5 w-3.5" />Ultima rulare {model.run.source === 'auto' ? 'automată' : 'manuală'} · {relativeGrileTime(model.run.finished_at ?? model.run.started_at)}</div>}
      </> : <span className="text-sm text-slate-400">Datele nu sunt încă disponibile.</span>}
    </div>
    {model.running && model.run && <div className="mt-3"><div className="mb-1 flex justify-between text-xs text-slate-500"><span>Verificare în curs…</span><span>{model.run.progress_current}/{model.run.progress_total}</span></div><div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"><div className="h-full bg-indigo-500 transition-all" style={{ width: `${model.progressPct}%` }} /></div></div>}
    {model.run?.status === 'failed' && <p className="mt-2 text-xs text-rose-500">Rulare eșuată: {model.run.error_message}</p>}
    {model.runCheck.isError && model.runCheckMatchesMonth && (
      <div
        role="alert"
        aria-live="polite"
        className="mt-3 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300"
      >
        <XCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
        <span>{getApiErrorMessage(model.runCheck.error, RUN_CHECK_ERROR_FALLBACK)}</span>
      </div>
    )}
    <GrileMonthlyPanel month={model.month || data?.month || ''} />
  </div>;
}

function GrileFilters({ filter, onChange }: { filter: StatusFilter; onChange: (value: StatusFilter) => void }) {
  return <>
    <label className="block lg:hidden"><span className="mb-1 block text-xs font-bold text-slate-500">Stare grilă</span><select value={filter} onChange={(event) => onChange(event.target.value as StatusFilter)} className="min-h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">{GRILE_STATUS_FILTERS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
    <div className="hidden flex-wrap gap-1.5 lg:flex">{GRILE_STATUS_FILTERS.map((item) => <button key={item.id} onClick={() => onChange(item.id)} className={cn('rounded-full px-3 py-1 text-xs font-medium transition-colors', filter === item.id ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300')}>{item.label}</button>)}</div>
  </>;
}

function Stat({ icon, value, label }: { icon: ReactNode; value: number; label: string }) {
  return <div className="flex items-center gap-2">{icon}<div className="leading-none"><div className="text-xl font-bold text-slate-800 dark:text-slate-100">{value}</div><div className="text-[11px] text-slate-400">{label}</div></div></div>;
}
