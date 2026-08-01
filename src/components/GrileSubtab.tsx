import { useEffect, useMemo, useState, type ReactNode } from 'react';
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
  refreshGrileStore,
  runGrileCheck,
  type GrileManager,
  type GrileStore,
  type GrileTeamLeader,
} from '../api/grile';
import { FirmaBadge } from './FirmaBadge';
import { GrileMonthlyPanel } from './GrileMonthlyPanel';
import { cn } from '../lib/utils';

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

// Template coloane desktop. Display-ul (hidden/grid) e separat ca sa nu intre in
// conflict cu `hidden` la breakpoint (ordinea claselor nu decide display in Tailwind).
const GRID_COLS = 'grid-cols-[minmax(240px,1.7fr)_96px_76px_1fr_1fr_112px] gap-2';
const DESKTOP_ROW = `hidden lg:grid ${GRID_COLS}`;

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

// ── Badge completare (procent + toggle detalii) — partajat mobil/desktop ───────
function CompletionBadge({
  pct,
  hasDetail,
  open,
  onToggle,
}: {
  pct: number | null;
  hasDetail: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  if (pct === null) return <span className="text-slate-400">—</span>;
  return (
    <button
      onClick={() => hasDetail && onToggle()}
      className={cn(
        'inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[11px] font-semibold',
        hasDetail && 'cursor-pointer hover:ring-1 hover:ring-slate-300',
        pct >= 80
          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
          : pct >= 50
            ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
            : 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
      )}
    >
      {pct}%
      {hasDetail && (open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />)}
    </button>
  );
}

// ── Camp etichetat (layout mobil: label deasupra valorii) ──────────────────────
function MobileField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{label}</span>
      <div>{children}</div>
    </div>
  );
}

// ── Rând magazin: card stivuit pe mobil, grid dens pe desktop (lg+) ───────────
function StoreRow({ s, month }: { s: GrileStore; month: string }) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const refreshMut = useMutation({
    mutationFn: () => refreshGrileStore(month, s.site_code),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['grile-overview', month] }),
  });
  const url = s.sheet_id ? `https://docs.google.com/spreadsheets/d/${s.sheet_id}` : null;
  const st = statusInfo(s);
  const missing = s.missing_days ?? [];
  const hasDetail = missing.length > 0 || !!s.error_message;
  const toggle = () => setOpen((v) => !v);
  const refreshButton = (
    <button
      type="button"
      onClick={() => refreshMut.mutate()}
      disabled={refreshMut.isPending}
      title={`Verifică doar ${s.locatie}`}
      aria-label={`Reîmprospătează grila ${s.locatie}`}
      className="inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-indigo-50 hover:text-indigo-600 disabled:cursor-wait disabled:opacity-60 dark:hover:bg-indigo-950/40 dark:hover:text-indigo-300"
    >
      <RefreshCw className={cn('h-3.5 w-3.5', refreshMut.isPending && 'animate-spin')} />
    </button>
  );

  // Nume = link la grila (partajat mobil/desktop)
  const nameEl = url ? (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      title="Deschide grila"
      className="group inline-flex min-w-0 items-center gap-1 truncate font-medium text-slate-700 hover:text-indigo-600 hover:underline dark:text-slate-200 dark:hover:text-indigo-400"
    >
      <span className="truncate">{s.locatie}</span>
      <ExternalLink className="h-3 w-3 flex-shrink-0 opacity-60 group-hover:opacity-100" />
    </a>
  ) : (
    <span className="truncate font-medium text-slate-700 dark:text-slate-200">{s.locatie}</span>
  );

  const targetCell = (
    <DiffCell status={s.target_status} grila={s.grila_target} db={s.db_target} diff={s.target_diff} />
  );
  const salesCell = (
    <DiffCell status={s.sales_status} grila={s.grila_sales} db={s.db_sales_mtd} diff={s.sales_diff} />
  );
  const statusBadge = (
    <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-semibold', st.cls)}>{st.label}</span>
  );

  return (
    <div className="border-t border-slate-100 dark:border-slate-800">
      {/* ── Mobil: card stivuit ── */}
      <div className="px-3 py-2.5 lg:hidden">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1">
            <FirmaBadge firma={s.firma} />
            {nameEl}
            {refreshButton}
          </div>
          <div className="flex-shrink-0">{statusBadge}</div>
        </div>
        {refreshMut.data && (
          <div className="mt-1 text-[10px] text-slate-400">
            Verificare: {refreshMut.data.changed ? 'grila a fost actualizată' : 'fără modificări'}
          </div>
        )}
        {refreshMut.isError && <div className="mt-1 text-[10px] text-rose-500">Verificarea a eșuat</div>}
        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2">
          <MobileField label="Completare">
            <CompletionBadge pct={s.completion_pct} hasDetail={hasDetail} open={open} onToggle={toggle} />
          </MobileField>
          <MobileField label="Editat">
            <span className="text-xs text-slate-500">{relTime(s.last_edit)}</span>
          </MobileField>
          <MobileField label="Target">{targetCell}</MobileField>
          <MobileField label="Realizat">{salesCell}</MobileField>
        </div>
      </div>

      {/* ── Desktop: grid dens ── */}
      <div
        className={cn(
          DESKTOP_ROW,
          'items-center px-4 py-2 text-sm transition-colors hover:bg-slate-50/80 dark:hover:bg-slate-800/30',
        )}
      >
        <div className="flex items-center gap-1 truncate">
          <FirmaBadge firma={s.firma} />
          {nameEl}
          {refreshButton}
          {refreshMut.data && (
            <span className="flex-shrink-0 text-[10px] text-slate-400">
              {refreshMut.data.changed ? 'actualizată' : 'fără modificări'}
            </span>
          )}
          {refreshMut.isError && <span className="flex-shrink-0 text-[10px] text-rose-500">eroare</span>}
        </div>
        <div className="flex items-center justify-center gap-1">
          <CompletionBadge pct={s.completion_pct} hasDetail={hasDetail} open={open} onToggle={toggle} />
        </div>
        <div className="text-center text-xs text-slate-400">{relTime(s.last_edit)}</div>
        <div>{targetCell}</div>
        <div>{salesCell}</div>
        <div>{statusBadge}</div>
      </div>

      {/* ── Detaliu expandat: zile necompletate + eroare (partajat) ── */}
      {open && hasDetail && (
        <div className="bg-slate-50 px-3 py-2 text-xs text-slate-600 lg:pl-9 dark:bg-slate-800/40 dark:text-slate-300">
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

// ── Antet desktop unic: mai lizibil si aliniat cu toate randurile ─────────────
function DesktopTableHeader() {
  return (
    <div
      className={cn(
        DESKTOP_ROW,
        'sticky top-2 z-10 items-center rounded-xl border border-slate-200 bg-slate-100 px-4 py-2 text-xs font-bold uppercase tracking-[0.04em] text-slate-600 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300',
      )}
    >
      <span>Magazin / structură</span>
      <span className="text-center">Completare</span>
      <span className="text-center">Editat</span>
      <span>Target</span>
      <span>Realizat</span>
      <span>Status</span>
    </div>
  );
}

// ── Grup Team Leader (pliabil ca managerul; fara bara cand nu exista TL) ──────
function TeamLeaderGroup({ tl, month }: { tl: GrileTeamLeader; month: string }) {
  const storageKey = `unihub_grile_tl_${tl.name ?? 'fara-tl'}`;
  const [open, setOpen] = useState(() => localStorage.getItem(storageKey) !== 'closed');
  const toggleOpen = () => setOpen((value) => {
    const next = !value;
    localStorage.setItem(storageKey, next ? 'open' : 'closed');
    return next;
  });

  const stores = tl.firms.flatMap((f) =>
    f.stores.map((s) => <StoreRow key={s.site_code} s={s} month={month} />),
  );

  // Magazine fara Team Leader: apar direct sub manager, fara rand/bara TL
  if (!tl.name) return <>{stores}</>;

  return (
    <div>
      <button
        onClick={toggleOpen}
        className="w-full border-y border-slate-200/70 bg-slate-100/70 px-4 py-1.5 text-left transition-colors hover:bg-slate-200/60 dark:border-slate-700/70 dark:bg-slate-800/50 dark:hover:bg-slate-800"
      >
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300">
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          Team Leader · {tl.name}
        </div>
      </button>
      {open && <div>{stores}</div>}
    </div>
  );
}

// ── Grup manager (ASM) ────────────────────────────────────────────────────────
function ManagerGroup({ m, filter, month }: { m: GrileManager; filter: StatusFilter; month: string }) {
  const storageKey = `unihub_grile_manager_${m.name}`;
  const [open, setOpen] = useState(() => localStorage.getItem(storageKey) !== 'closed');
  const toggleOpen = () => setOpen((value) => {
    const next = !value;
    localStorage.setItem(storageKey, next ? 'open' : 'closed');
    return next;
  });

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
    <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <button
        onClick={toggleOpen}
        className="w-full bg-slate-50 px-3 py-2 text-left transition-colors hover:bg-slate-100 dark:bg-slate-800/60 dark:hover:bg-slate-800"
      >
        {/* Mobil: nume + sumar pe doua capete */}
        <div className="flex items-center justify-between gap-2 lg:hidden">
          <div className="flex min-w-0 items-center gap-2">
            {open ? <ChevronDown className="h-4 w-4 flex-shrink-0" /> : <ChevronRight className="h-4 w-4 flex-shrink-0" />}
            <span className="truncate font-semibold text-slate-800 dark:text-slate-100">{m.name}</span>
            <span className="flex-shrink-0 text-xs text-slate-400">{m.store_count} mag.</span>
          </div>
          <div className="flex flex-shrink-0 items-center gap-2 text-xs">
            <span className="text-emerald-600 dark:text-emerald-400">{m.ok} OK</span>
            <span className="text-rose-600 dark:text-rose-400">{m.problems} probl.</span>
            {m.avg_completion !== null && <span className="text-slate-500">{m.avg_completion}%</span>}
          </div>
        </div>
        {/* Desktop: managerul si sumarul folosesc toata latimea barei de grup. */}
        <div className="hidden items-center justify-between gap-4 lg:flex">
          <div className="flex min-w-0 items-center gap-2">
            {open ? <ChevronDown className="h-4 w-4 flex-shrink-0" /> : <ChevronRight className="h-4 w-4 flex-shrink-0" />}
            <span className="truncate font-semibold text-slate-800 dark:text-slate-100">{m.name}</span>
            <span className="flex-shrink-0 text-xs text-slate-500 dark:text-slate-400">{m.store_count} magazine</span>
          </div>
          <div className="flex flex-shrink-0 items-center gap-2 text-xs font-semibold">
            <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
              {m.ok} OK
            </span>
            <span className="rounded-full bg-rose-100 px-2.5 py-1 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
              {m.problems} probleme
            </span>
            {m.avg_completion !== null && (
              <span className="rounded-full bg-slate-200 px-2.5 py-1 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                Completare {m.avg_completion}%
              </span>
            )}
          </div>
        </div>
      </button>
      {open && (
        <div className="bg-white dark:bg-slate-900">
          {filteredTLs.map((tl, i) => (
            <TeamLeaderGroup key={tl.name ?? `__no_tl_${i}`} tl={tl} month={month} />
          ))}
        </div>
      )}
    </div>
  );
}

const LEGACY_GRILE_MONTH_KEY = 'unihub_grile_month';

export function GrileSubtab() {
  // month gol = lasa backend-ul sa aleaga ultima luna operationala;
  // selectiile vechi nu se persista, ca inchiderea de luna sa nu blocheze UI-ul pe luna anterioara.
  const [month, setMonth] = useState('');
  const [filter, setFilter] = useState<StatusFilter>('all');
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ['grile-overview', month],
    queryFn: ({ signal }) => getGrileOverview(month || undefined, signal),
    refetchInterval: (q) => {
      const run = (q.state.data as Awaited<ReturnType<typeof getGrileOverview>> | undefined)?.run;
      return run && (run.status === 'running' || run.status === 'queued') ? 3000 : false;
    },
  });

  // La prima incarcare, sincronizeaza picker-ul cu luna rezolvata de backend
  useEffect(() => {
    if (!month && data?.month) setMonth(data.month);
  }, [data?.month, month]);

  useEffect(() => {
    localStorage.removeItem(LEGACY_GRILE_MONTH_KEY);
  }, []);

  const runMut = useMutation({
    mutationFn: () => runGrileCheck(month),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['grile-overview', month] }),
  });

  const run = data?.run ?? null;
  const isRunning = run?.status === 'running' || run?.status === 'queued' || runMut.isPending;
  const progressPct =
    run && run.progress_total > 0 ? Math.round((run.progress_current / run.progress_total) * 100) : 0;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-3 pb-24 pt-2">
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

        {/* ── Inchidere luna (vizibil doar pentru admin grile) ── */}
        <GrileMonthlyPanel month={month || data?.month || ''} />
      </div>

      {/* ── Filtre locale (independente de filtrul global) ── */}
      <label className="block lg:hidden">
        <span className="mb-1 block text-xs font-bold text-slate-500">Stare grilă</span>
        <select value={filter} onChange={(event) => setFilter(event.target.value as StatusFilter)} className="min-h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
          {FILTERS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
      </label>
      <div className="hidden flex-wrap gap-1.5 lg:flex">
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

      {/* ── Arbore ── */}
      <div className="space-y-2">
        <DesktopTableHeader />
        {isLoading && <div className="p-8 text-center text-slate-400">Se încarcă…</div>}
        {isError && <div className="p-8 text-center text-rose-500">Eroare la încărcare.</div>}
        {!isLoading && data && data.managers.length === 0 && (
          <div className="p-8 text-center text-slate-400">
            Nicio dată. Rulează o verificare pentru luna selectată.
          </div>
        )}
        {data?.managers.map((m) => (
          <ManagerGroup key={m.name} m={m} filter={filter} month={month || data.month} />
        ))}
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
