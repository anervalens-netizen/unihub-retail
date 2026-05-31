import { useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  Loader2,
  PlayCircle,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import {
  getGrileOverview,
  runGrileCheck,
  type GrileManager,
  type GrileStore,
} from '../api/grile';
import { FirmaBadge } from './FirmaBadge';
import { cn } from '../lib/utils';

function currentMonth(): string {
  return new Date().toISOString().slice(0, 7);
}

const NUMBER = new Intl.NumberFormat('ro-RO');

function fmt(n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : NUMBER.format(Math.round(n));
}

type StatusFilter = 'all' | 'NECOMPLETAT' | 'IN_URMA' | 'DIF_TARGET' | 'DIF_SALES' | 'ERROR' | 'OK';

const FILTERS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'Toate' },
  { id: 'OK', label: 'OK' },
  { id: 'NECOMPLETAT', label: 'Necompletat' },
  { id: 'IN_URMA', label: 'În urmă' },
  { id: 'DIF_TARGET', label: 'Dif. target' },
  { id: 'DIF_SALES', label: 'Dif. vânzări' },
  { id: 'ERROR', label: 'Eroare Google' },
];

function matchesFilter(s: GrileStore, f: StatusFilter): boolean {
  switch (f) {
    case 'all':
      return true;
    case 'OK':
      return s.target_status === 'OK' && s.sales_status === 'OK';
    case 'NECOMPLETAT':
      return s.fill_status === 'NECOMPLETAT';
    case 'IN_URMA':
      return s.sales_status === 'IN_URMA';
    case 'DIF_TARGET':
      return s.target_status === 'DIFERENTA';
    case 'DIF_SALES':
      return s.sales_status === 'DIFERENTA';
    case 'ERROR':
      return !!s.error_code;
    default:
      return true;
  }
}

function relTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const h = Math.floor(diff / 3_600_000);
  if (h < 1) return `${Math.max(1, Math.floor(diff / 60_000))}m`;
  if (h < 24) return `acum ${h}h`;
  const days = Math.floor(h / 24);
  return days === 1 ? 'ieri' : `${days}z`;
}

const ROW_GRID = 'grid grid-cols-[minmax(170px,1.5fr)_96px_84px_1.2fr_1.2fr_120px] gap-2';

// ── Celula diferenta (target/vanzari): OK badge sau breakdown ca app veche ─────
function DiffCell({
  status,
  grila,
  db,
  diff,
}: {
  status: string | null;
  grila: number | null;
  db: number | null;
  diff: number | null;
}) {
  if (status === null || status === 'NECOMPLETAT') {
    return <span className="text-xs text-slate-400">—</span>;
  }
  if (status === 'OK') {
    return (
      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
        OK
      </span>
    );
  }
  const r = diff === null ? null : Math.round(diff);
  return (
    <div className="text-xs leading-tight">
      <div className={cn('font-bold', status === 'IN_URMA' ? 'text-amber-600' : 'text-rose-500')}>
        {r === null ? '—' : `${r > 0 ? '+' : ''}${NUMBER.format(r)}`}
      </div>
      <div className="text-[11px] text-slate-400">Raport {fmt(db)}</div>
      <div className="text-[11px] text-slate-400">Grilă {fmt(grila)}</div>
    </div>
  );
}

// ── Status combinat (Target / Realizat / Target + Realizat / OK ...) ──────────
function statusInfo(s: GrileStore): { label: string; cls: string } {
  const rose = 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300';
  const amber = 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
  const slate = 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300';
  const emerald = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300';
  if (s.error_code) return { label: 'Eroare', cls: rose };
  if (s.fill_status === 'NECOMPLETAT') return { label: 'Necompletat', cls: slate };
  const t = s.target_status === 'DIFERENTA';
  const sl = s.sales_status === 'DIFERENTA';
  const inUrma = s.sales_status === 'IN_URMA';
  if (t && (sl || inUrma)) return { label: 'Target + Realizat', cls: rose };
  if (t) return { label: 'Target', cls: rose };
  if (sl) return { label: 'Realizat', cls: rose };
  if (inUrma) return { label: 'În urmă', cls: amber };
  return { label: 'OK', cls: emerald };
}

// ── Rând magazin (nume = link la grila; completare expandabila cu zile lipsa) ──
function StoreRow({ s }: { s: GrileStore }) {
  const [open, setOpen] = useState(false);
  const url = s.sheet_id ? `https://docs.google.com/spreadsheets/d/${s.sheet_id}` : null;
  const st = statusInfo(s);
  const missing = s.missing_days ?? [];
  const hasDetail = missing.length > 0 || !!s.error_message;

  return (
    <div className="border-t border-slate-100 dark:border-slate-800">
      <div className={cn(ROW_GRID, 'items-center px-3 py-1.5 text-sm')}>
        {/* Nume = link grila */}
        <div className="flex items-center gap-1 truncate">
          <FirmaBadge firma={s.firma} />
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              title="Deschide grila"
              className="group inline-flex items-center gap-1 truncate font-medium text-slate-700 hover:text-indigo-600 hover:underline dark:text-slate-200 dark:hover:text-indigo-400"
            >
              <span className="truncate">{s.locatie}</span>
              <ExternalLink className="h-3 w-3 flex-shrink-0 opacity-0 group-hover:opacity-100" />
            </a>
          ) : (
            <span className="truncate font-medium text-slate-700 dark:text-slate-200">{s.locatie}</span>
          )}
        </div>
        {/* Completare + toggle detalii */}
        <div className="flex items-center justify-center gap-1">
          {s.completion_pct === null ? (
            <span className="text-slate-400">—</span>
          ) : (
            <button
              onClick={() => hasDetail && setOpen((v) => !v)}
              className={cn(
                'inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[11px] font-semibold',
                hasDetail && 'cursor-pointer hover:ring-1 hover:ring-slate-300',
                s.completion_pct >= 80
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                  : s.completion_pct >= 50
                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                    : 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
              )}
            >
              {s.completion_pct}%
              {hasDetail && (open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />)}
            </button>
          )}
        </div>
        <div className="text-center text-xs text-slate-400">{relTime(s.last_edit)}</div>
        <div><DiffCell status={s.target_status} grila={s.grila_target} db={s.db_target} diff={s.target_diff} /></div>
        <div><DiffCell status={s.sales_status} grila={s.grila_sales} db={s.db_sales_mtd} diff={s.sales_diff} /></div>
        <div>
          <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-semibold', st.cls)}>{st.label}</span>
        </div>
      </div>
      {/* Detaliu expandat: zile necompletate + eroare */}
      {open && hasDetail && (
        <div className="bg-slate-50 px-3 py-2 pl-9 text-xs text-slate-600 dark:bg-slate-800/40 dark:text-slate-300">
          {missing.length > 0 && (
            <div>
              <span className="font-semibold">Zile necompletate ({missing.length}):</span>{' '}
              {missing.join(', ')}
            </div>
          )}
          {s.error_message && <div className="mt-1 text-rose-500">Eroare Google: {s.error_message}</div>}
        </div>
      )}
    </div>
  );
}

// ── Grup manager (ASM) ────────────────────────────────────────────────────────
function ManagerGroup({ m, filter }: { m: GrileManager; filter: StatusFilter }) {
  const [open, setOpen] = useState(true);

  const filteredTLs = useMemo(() => {
    return m.team_leaders
      .map((tl) => ({
        ...tl,
        firms: tl.firms
          .map((f) => ({ ...f, stores: f.stores.filter((s) => matchesFilter(s, filter)) }))
          .filter((f) => f.stores.length > 0),
      }))
      .filter((tl) => tl.firms.length > 0);
  }, [m, filter]);

  if (filteredTLs.length === 0) return null;

  return (
    <div className="mb-2 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between bg-slate-50 px-3 py-2 text-left dark:bg-slate-800/60"
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <span className="font-semibold text-slate-800 dark:text-slate-100">{m.name}</span>
          <span className="text-xs text-slate-400">{m.store_count} magazine</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-emerald-600 dark:text-emerald-400">{m.ok} OK</span>
          <span className="text-rose-600 dark:text-rose-400">{m.problems} probleme</span>
          {m.avg_completion !== null && (
            <span className="text-slate-500">compl. {m.avg_completion}%</span>
          )}
        </div>
      </button>
      {open && (
        <div className="bg-white dark:bg-slate-900">
          {filteredTLs.map((tl) => (
            <div key={tl.name}>
              <div className="bg-slate-100/60 px-3 py-1 text-xs font-medium text-slate-500 dark:bg-slate-800/40 dark:text-slate-400">
                Team Leader · {tl.name}
              </div>
              {tl.firms.map((f) => (
                <div key={f.name}>
                  <div className="flex items-center gap-1 px-3 py-1 pl-6 text-[11px] font-medium text-slate-400">
                    <FirmaBadge firma={f.name} />
                    {f.name} · {f.stores.length} magazine
                  </div>
                  {f.stores.map((s) => (
                    <StoreRow key={s.site_code} s={s} />
                  ))}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function GrileSubtab() {
  const [month, setMonth] = useState(currentMonth);
  const [filter, setFilter] = useState<StatusFilter>('all');
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ['grile-overview', month],
    queryFn: () => getGrileOverview(month),
    refetchInterval: (q) => {
      const run = (q.state.data as Awaited<ReturnType<typeof getGrileOverview>> | undefined)?.run;
      return run && (run.status === 'running' || run.status === 'queued') ? 3000 : false;
    },
  });

  const runMut = useMutation({
    mutationFn: () => runGrileCheck(month),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['grile-overview', month] }),
  });

  const run = data?.run ?? null;
  const isRunning = run?.status === 'running' || run?.status === 'queued' || runMut.isPending;
  const progressPct =
    run && run.progress_total > 0 ? Math.round((run.progress_current / run.progress_total) * 100) : 0;

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* ── Card status + actiune ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
              Verificare grile salariale
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Grila (K5/L5) vs target + vânzări din DB · cheie <code>site_code</code>. Rulează automat
              zilnic după importul vânzărilor.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800"
            />
            <button
              onClick={() => runMut.mutate()}
              disabled={isRunning}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors',
                isRunning ? 'cursor-not-allowed bg-slate-400' : 'bg-indigo-600 hover:bg-indigo-700',
              )}
            >
              {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              {isRunning ? 'Rulează…' : 'Rulează verificare'}
            </button>
          </div>
        </div>

        {/* Sumar ultima rulare */}
        <div className="mt-4 flex flex-wrap items-center gap-6">
          {run ? (
            <>
              <Stat icon={<CheckCircle2 className="h-5 w-5 text-emerald-500" />} value={run.ok_count} label="OK" />
              <Stat icon={<AlertTriangle className="h-5 w-5 text-rose-500" />} value={run.problem_count} label="probleme" />
              {run.error_count > 0 && (
                <Stat icon={<XCircle className="h-5 w-5 text-rose-400" />} value={run.error_count} label="erori" />
              )}
              <Stat
                icon={<RefreshCw className="h-5 w-5 text-slate-400" />}
                value={data?.total_sheets ?? 0}
                label="magazine"
              />
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <Clock className="h-3.5 w-3.5" />
                {run.source === 'auto' ? 'automat după import' : 'manual'} ·{' '}
                {relTime(run.finished_at ?? run.started_at)}
                {run.triggered_by_email ? ` · ${run.triggered_by_email}` : ''}
              </div>
            </>
          ) : (
            <span className="text-sm text-slate-400">
              Nicio rulare pentru luna selectată. Apasă „Rulează verificare".
            </span>
          )}
        </div>

        {/* Progres */}
        {isRunning && run && (
          <div className="mt-3">
            <div className="mb-1 flex justify-between text-xs text-slate-500">
              <span>Verificare în curs…</span>
              <span>
                {run.progress_current}/{run.progress_total}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
              <div className="h-full bg-indigo-500 transition-all" style={{ width: `${progressPct}%` }} />
            </div>
          </div>
        )}
        {run?.status === 'failed' && (
          <p className="mt-2 text-xs text-rose-500">Rulare eșuată: {run.error_message}</p>
        )}
      </div>

      {/* ── Filtre locale (independente de filtrul global) ── */}
      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={cn(
              'rounded-full px-3 py-1 text-xs font-medium transition-colors',
              filter === f.id
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300',
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* ── Header coloane ── */}
      <div className={cn(ROW_GRID, 'px-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400')}>
        <span>Magazin</span>
        <span className="text-center">Completare</span>
        <span className="text-center">Editat</span>
        <span>Target</span>
        <span>Realizat</span>
        <span>Status</span>
      </div>

      {/* ── Arbore ── */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && <div className="p-8 text-center text-slate-400">Se încarcă…</div>}
        {isError && <div className="p-8 text-center text-rose-500">Eroare la încărcare.</div>}
        {!isLoading && data && data.managers.length === 0 && (
          <div className="p-8 text-center text-slate-400">
            Nicio dată. Rulează o verificare pentru luna selectată.
          </div>
        )}
        {data?.managers.map((m) => <ManagerGroup key={m.name} m={m} filter={filter} />)}
      </div>
    </div>
  );
}

function Stat({ icon, value, label }: { icon: ReactNode; value: number; label: string }) {
  return (
    <div className="flex items-center gap-2">
      {icon}
      <div className="leading-none">
        <div className="text-xl font-bold text-slate-800 dark:text-slate-100">{value}</div>
        <div className="text-[11px] text-slate-400">{label}</div>
      </div>
    </div>
  );
}
