import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  CircleHelp,
  ExternalLink,
  FlaskConical,
  LoaderCircle,
  RefreshCw,
} from 'lucide-react';

import {
  getGrilePilotV2,
  type GrilePilotV2Overview,
} from '../../api/grile';
import { formatIsoDate } from '../../lib/dates';
import { FirmaBadge } from '../FirmaBadge';

type PilotStore = GrilePilotV2Overview['managers'][number]['stores'][number];
type Check = PilotStore['report_check'];

function lei(value: number | null): string {
  if (value === null) return '—';
  return `${new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 0 }).format(value)} lei`;
}

function pct(value: number | null): string {
  if (value === null) return '—';
  return `${new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 1 }).format(value)}%`;
}

function CheckBadge({ check }: { check: Check }) {
  const styles = {
    ok: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
    problem: 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
    unavailable: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  } as const;
  const Icon = check.status === 'ok' ? CheckCircle2 : check.status === 'problem' ? CircleAlert : CircleHelp;
  return (
    <span className={`inline-flex max-w-52 items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-semibold ${styles[check.status]}`}>
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span>{check.message}</span>
    </span>
  );
}

function CheckCell({ check }: { check: Check }) {
  return (
    <div className="space-y-1">
      <CheckBadge check={check} />
      {(check.target !== null || check.realized !== null) && (
        <p className="text-[10px] text-slate-400">
          T {lei(check.target)} · R {lei(check.realized)}
        </p>
      )}
    </div>
  );
}

function forecastTone(value: number | null): string {
  if (value === null || value < 90) return 'text-rose-600 dark:text-rose-300';
  if (value < 100) return 'text-amber-600 dark:text-amber-300';
  return 'text-emerald-600 dark:text-emerald-300';
}

function StoreRow({ store }: { store: PilotStore }) {
  return (
    <tr className="border-t border-slate-200 align-middle dark:border-slate-700">
      <td className="px-3 py-3">
        <div className="flex min-w-48 items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
          <FirmaBadge firma={store.firma} />
          <span>{store.locatie}</span>
        </div>
        <span className="mt-0.5 block text-[10px] text-slate-400">{store.site_code}</span>
      </td>
      <td className="px-3 py-3 text-right font-semibold tabular-nums">{lei(store.target_v2)}</td>
      <td className="px-3 py-3 text-right tabular-nums">
        <strong className="block">{lei(store.realized_v2)}</strong>
        <span className="text-xs text-slate-500">{pct(store.realized_pct_v2)}</span>
      </td>
      <td className="px-3 py-3 text-right tabular-nums">
        <strong className="block">{lei(store.forecast_v2)}</strong>
        <span className={`text-xs font-bold ${forecastTone(store.forecast_pct_v2)}`}>
          {pct(store.forecast_pct_v2)}
        </span>
      </td>
      <td className="px-3 py-3"><CheckCell check={store.report_check} /></td>
      <td className="px-3 py-3"><CheckCell check={store.v1_check} /></td>
      <td className="px-3 py-3 text-right">
        <a
          href={`https://docs.google.com/spreadsheets/d/${store.sheet_id}`}
          target="_blank"
          rel="noreferrer"
          aria-label={`Deschide grila ${store.locatie}`}
          className="inline-flex rounded-lg p-2 text-slate-400 transition hover:bg-violet-50 hover:text-violet-600 dark:hover:bg-violet-950/30"
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      </td>
    </tr>
  );
}

function ManagerTable({ manager }: { manager: GrilePilotV2Overview['managers'][number] }) {
  const ok = manager.stores.filter((store) => store.report_check.status === 'ok').length;
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-center justify-between bg-slate-50 px-4 py-2.5 dark:bg-slate-800/70">
        <div>
          <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100">{manager.name}</h4>
          <p className="text-[11px] text-slate-500">{manager.stores.length} magazine pilot</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${ok === manager.stores.length ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
          {ok}/{manager.stores.length} rapoarte OK
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1050px] text-left text-sm">
          <thead className="text-[10px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Magazin</th>
              <th className="px-3 py-2 text-right">Target V2</th>
              <th className="px-3 py-2 text-right">Realizat V2</th>
              <th className="px-3 py-2 text-right">Forecast V2</th>
              <th className="px-3 py-2">Vs rapoarte</th>
              <th className="px-3 py-2">Vs V1 · temporar</th>
              <th className="w-12 px-3 py-2" />
            </tr>
          </thead>
          <tbody>{manager.stores.map((store) => <StoreRow key={store.site_code} store={store} />)}</tbody>
        </table>
      </div>
    </section>
  );
}

function PilotContent({ data }: { data: GrilePilotV2Overview }) {
  const stores = data.managers.flatMap((manager) => manager.stores);
  const reportOk = stores.filter((store) => store.report_check.status === 'ok').length;
  const v1Ok = stores.filter((store) => store.v1_check.status === 'ok').length;
  const latestCutoff = stores.map((store) => store.report_cutoff).filter(Boolean).sort().at(-1) ?? null;
  return (
    <>
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-emerald-100 px-2.5 py-1 font-semibold text-emerald-700">Rapoarte: {reportOk}/{stores.length} OK</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-600">V1: {v1Ok}/{stores.length} identice</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-500">Vânzări până la {formatIsoDate(latestCutoff)}</span>
      </div>
      <div className="space-y-3">{data.managers.map((manager) => <ManagerTable key={manager.name} manager={manager} />)}</div>
    </>
  );
}

export function PilotV2Panel({ enabled = true }: { enabled?: boolean }) {
  const query = useQuery({
    queryKey: ['grile-pilot-v2', '2026-08'],
    queryFn: ({ signal }) => getGrilePilotV2('2026-08', signal),
    enabled,
    staleTime: 5 * 60_000,
  });

  return (
    <div className="space-y-4">
      <div className="space-y-4 rounded-2xl border border-violet-200 bg-white p-4 dark:border-violet-900/60 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="rounded-xl bg-violet-100 p-2 text-violet-700 dark:bg-violet-950/60 dark:text-violet-300"><FlaskConical className="h-5 w-5" /></span>
            <div>
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Grile V2 · pilot</h3>
              <p className="mt-0.5 text-xs text-slate-500">Date live din cele 5 grile, grupate pe manager. Toleranță verificare: 1 leu.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-60 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${query.isFetching ? 'animate-spin' : ''}`} />
            Actualizează
          </button>
        </div>

        {query.isLoading && <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500"><LoaderCircle className="h-5 w-5 animate-spin" />Citesc grilele pilot…</div>}
        {query.isError && <div role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">Grilele V2 nu pot fi citite momentan. Reîncearcă prin Actualizează.</div>}
        {query.data && <PilotContent data={query.data} />}
      </div>

      <div className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/25 dark:text-amber-200">
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
        <p>Închiderea lunii rămâne pe <strong>Grila actuală</strong>. Verificarea V2 este read-only și nu modifică fluxul oficial.</p>
      </div>
    </div>
  );
}
